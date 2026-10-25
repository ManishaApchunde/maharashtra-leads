"""Shared ingest pipeline used by CSV import, the API collector and the manual form.

clean -> dedup -> link geography -> insert -> categories -> proximity -> score
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Business, BusinessCategory, Category, CollectionRun, DataSource, District,
    DuplicateCandidate, Location, Taluka,
)
from app.services import dedup
from app.services.cleaning import clean_row
from app.services.proximity import nearest_office
from app.services.scoring import apply_score, compute_score
from app.utils.maharashtra import TEST_DATA_SOURCE

COMMIT_EVERY = 500


def _source_type(name: str) -> str:
    n = name.lower()
    if name.upper() == TEST_DATA_SOURCE:
        return "test"
    if "api" in n:
        return "api"
    if "csv" in n or "excel" in n:
        return "csv"
    if "manual" in n:
        return "manual"
    if "directory" in n:
        return "directory"
    return "other"


class Ingestor:
    """Holds small caches for one import so 100k-row files don't hit lookup tables per row."""

    def __init__(self, db: Session, run: CollectionRun | None = None):
        self.db = db
        self.run = run
        self._sources: dict[str, int] = {}
        self._districts = {d.name: d.id for d in db.scalars(select(District))}
        self._talukas: dict[tuple[int, str], int] = {}
        self._locations: dict[tuple, int] = {}
        self._categories = {c.name: c.id for c in db.scalars(select(Category))}

    # --- lookups ---------------------------------------------------------------
    def source_id(self, name: str) -> int:
        if name not in self._sources:
            src = self.db.scalar(select(DataSource).where(DataSource.source_name == name))
            if not src:
                src = DataSource(source_name=name, source_type=_source_type(name),
                                 collection_method="Auto-registered on import")
                self.db.add(src)
                self.db.flush()
            self._sources[name] = src.id
        return self._sources[name]

    def taluka_id(self, district_id: int, name: str) -> int:
        key = (district_id, name.lower())
        if key not in self._talukas:
            t = self.db.scalar(select(Taluka).where(Taluka.district_id == district_id, Taluka.name == name))
            if not t:
                t = Taluka(name=name, district_id=district_id)
                self.db.add(t)
                self.db.flush()
            self._talukas[key] = t.id
        return self._talukas[key]

    def location_id(self, district_id: int, taluka_id: int | None, name: str, type_: str, pincode: str | None) -> int:
        key = (district_id, taluka_id, name.lower(), type_)
        if key not in self._locations:
            q = select(Location).where(Location.district_id == district_id, Location.name == name,
                                       Location.type == type_)
            q = q.where(Location.taluka_id == taluka_id) if taluka_id else q.where(Location.taluka_id.is_(None))
            loc = self.db.scalar(q)
            if not loc:
                loc = Location(name=name, type=type_, district_id=district_id, taluka_id=taluka_id, pincode=pincode)
                self.db.add(loc)
                self.db.flush()
            self._locations[key] = loc.id
        return self._locations[key]

    def link_geo(self, b: Business) -> None:
        did = self._districts.get(b.district or "")
        if not did:
            return
        b.district_id = did
        b.taluka_id = self.taluka_id(did, b.taluka) if b.taluka else None
        if b.city:
            b.location_id = self.location_id(did, b.taluka_id, b.city, "city", b.pincode)
        elif b.village:
            b.location_id = self.location_id(did, b.taluka_id, b.village, "village", b.pincode)

    def set_categories(self, b: Business, names: list[str]) -> None:
        existing = {c.name for c in b.categories} if b.id else set()
        for n in names:
            if n in existing or n not in self._categories:
                continue
            self.db.add(BusinessCategory(business_id=b.id, category_id=self._categories[n]))

    def refresh_proximity(self, b: Business) -> str | None:
        near = nearest_office(self.db, b.latitude, b.longitude)
        if near:
            b.nearest_gov_office_id, label, b.nearest_gov_office_m = near
            return label
        b.nearest_gov_office_id = b.nearest_gov_office_m = None
        return None

    # --- main entry ------------------------------------------------------------
    def ingest_one(self, row: dict, default_source: str) -> tuple[str, dict]:
        """Returns (outcome, info). outcome: new | duplicate | possible_duplicate | invalid."""
        cr = clean_row(row, default_source)
        if cr.record is None:
            return "invalid", {"reason": cr.invalid_reason}
        rec = cr.record

        matches = dedup.find_matches(self.db, rec)
        exact = next((m for m in matches if m.exact), None)
        if exact:
            target = exact.business
            filled = dedup.fill_missing(target, rec)
            self.set_categories(target, cr.categories)
            self.db.flush()
            self.db.refresh(target)
            if filled:
                if {"latitude", "longitude"} & set(filled):
                    self.refresh_proximity(target)
                apply_score(target)
            return "duplicate", {"existing_id": target.id, "reasons": exact.reasons, "filled": filled}

        b = Business(**rec)
        b.data_source_id = self.source_id(rec["source"])
        if self.run:
            b.collection_run_id = self.run.id
        self.link_geo(b)
        self.db.add(b)
        self.db.flush()
        self.set_categories(b, cr.categories)

        if matches:
            b.duplicate_status = "possible_duplicate"
            for m in matches[:5]:
                self.db.add(DuplicateCandidate(business_id=b.id, matched_business_id=m.business.id,
                                               match_score=m.score, reasons=m.reasons))

        label = self.refresh_proximity(b)
        b.lead_score, b.score_breakdown = compute_score(b, cr.categories, label)
        if b.lead_status == "New" and "invalid_phone" in cr.flags and not b.address:
            b.lead_status = "Invalid"
        return ("possible_duplicate" if matches else "new"), {"id": b.id}

    def ingest_many(self, rows, default_source: str, start_row: int = 2) -> dict:
        summary = {"total": 0, "new": 0, "duplicates": 0, "possible_duplicates": 0, "invalid": 0, "errors": []}
        for i, row in enumerate(rows, start=start_row):
            summary["total"] += 1
            try:
                with self.db.begin_nested():
                    outcome, info = self.ingest_one(row, default_source)
            except Exception as exc:  # one bad row must not kill a 100k-row import
                self._talukas.clear(); self._locations.clear(); self._sources.clear()
                outcome, info = "invalid", {"reason": f"error: {exc.__class__.__name__}: {str(exc)[:200]}"}
            if outcome == "new":
                summary["new"] += 1
            elif outcome == "duplicate":
                summary["duplicates"] += 1
            elif outcome == "possible_duplicate":
                summary["possible_duplicates"] += 1
            else:
                summary["invalid"] += 1
                if len(summary["errors"]) < 1000:
                    summary["errors"].append({"row": i, "shop_name": (row.get("shop_name") or "")[:100],
                                              "reason": info.get("reason")})
            if summary["total"] % COMMIT_EVERY == 0:
                if self.run:  # live progress for the Import page
                    record_run_counts(self.run, summary)
                    self.run.total_results = max(self.run.total_results or 0, summary["total"])
                self.db.commit()
        self.db.commit()
        return summary


def record_run_counts(run: CollectionRun, summary: dict) -> None:
    run.total_results = summary["total"]
    run.new_count = summary["new"]
    run.duplicate_count = summary["duplicates"]
    run.possible_duplicate_count = summary["possible_duplicates"]
    run.invalid_count = summary["invalid"]
    run.errors = summary["errors"]
