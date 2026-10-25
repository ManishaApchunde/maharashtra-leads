"""Duplicate detection.

Signals (as requested): normalised phone, source place ID, normalised name + address,
approximate location, pincode, and name similarity.

Outcome for an incoming record:
  * "exact"    -> same source place ID, or same phone AND very similar name.
                  The incoming row is NOT inserted; missing fields on the existing
                  record are filled in (nothing is overwritten or deleted).
  * "possible" -> inserted with duplicate_status = possible_duplicate and a
                  duplicate_candidates row for a human to confirm or reject.
  * none       -> inserted as unique.
"""
import re
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Business
from app.utils.geo import haversine_m

POSSIBLE_THRESHOLD = 40
_DIGITS = re.compile(r"\d+")
NEAR_BOX = 0.0015  # ~150 m
AREA_SCAN_LIMIT = 5000      # max rows of one pincode / city scored in Python per incoming record
AREA_NAME_MIN_SIM = 45      # same cut-off the old pg_trgm query used (0.45)


@dataclass
class Match:
    business: Business
    score: int
    reasons: list[str]
    exact: bool


def name_similarity(a_norm, a_core, b_norm, b_core) -> int:
    if not a_norm or not b_norm:
        return 0
    # Compare the distinctive part of the name when both have one, so generic words
    # ("xerox centre") don't make "Sai Xerox Centre" look like "Om Sai Xerox Centre".
    if a_core and b_core:
        # "Om Xerox 2" and "Om Xerox 3" are different branches, not typos.
        if _DIGITS.findall(a_core) != _DIGITS.findall(b_core):
            return min(50, int(fuzz.ratio(a_core, b_core)))
        return int(fuzz.ratio(a_core, b_core))
    return int(fuzz.token_sort_ratio(a_norm, b_norm))


def _candidates(db: Session, rec: dict, exclude_id: int | None) -> list[Business]:
    base = select(Business).where(
        Business.duplicate_status != "confirmed_duplicate",
        Business.is_test_data == rec.get("is_test_data", False),
    )
    if exclude_id:
        base = base.where(Business.id != exclude_id)

    conds = []
    if rec.get("source_place_id"):
        conds.append((Business.source_place_id == rec["source_place_id"]) & (Business.source == rec["source"]))

    phones = {p for p in (rec.get("normalized_phone"), rec.get("normalized_alternate_phone"),
                          rec.get("whatsapp_number")) if p}
    if phones:
        conds.append(or_(Business.normalized_phone.in_(phones),
                         Business.normalized_alternate_phone.in_(phones),
                         Business.whatsapp_number.in_(phones)))

    found: dict[int, Business] = {}
    if conds:
        for b in db.scalars(base.where(or_(*conds)).limit(25)):
            found[b.id] = b

    # Similar names in the same pincode or same district+city. MySQL has no trigram similarity,
    # so we pull just (id, names) for that small area through the pincode / city indexes and
    # score them in Python with rapidfuzz, then load the best few rows.
    if rec.get("normalized_name"):
        area_conds = []
        if rec.get("pincode"):
            area_conds.append(Business.pincode == rec["pincode"])
        if rec.get("city") and rec.get("district"):
            area_conds.append((Business.district == rec["district"]) &
                              (Business.city == rec["city"]))  # case-insensitive collation
        if area_conds:
            needle = rec.get("core_name") or rec["normalized_name"]
            light = base.with_only_columns(Business.id, Business.normalized_name, Business.core_name) \
                .where(or_(*area_conds), Business.normalized_name.isnot(None)).limit(AREA_SCAN_LIMIT)
            scored = []
            for bid, b_norm, b_core in db.execute(light):
                hay = (b_core or b_norm) if rec.get("core_name") else b_norm
                sim = fuzz.ratio(needle, hay or "")
                if sim > AREA_NAME_MIN_SIM:
                    scored.append((sim, bid))
            best = [bid for _, bid in sorted(scored, reverse=True)[:10] if bid not in found]
            if best:
                for b in db.scalars(select(Business).where(Business.id.in_(best))):
                    found[b.id] = b

    # Anything within ~150 m
    if rec.get("latitude") is not None and rec.get("longitude") is not None:
        lat, lng = rec["latitude"], rec["longitude"]
        q = base.where(Business.latitude.between(lat - NEAR_BOX, lat + NEAR_BOX),
                       Business.longitude.between(lng - NEAR_BOX, lng + NEAR_BOX)).limit(25)
        for b in db.scalars(q):
            found[b.id] = b

    return list(found.values())


def evaluate(rec: dict, b: Business) -> Match | None:
    reasons: list[str] = []
    score = 0

    if rec.get("source_place_id") and b.source_place_id == rec["source_place_id"] and b.source == rec["source"]:
        return Match(b, 100, ["same source place ID"], True)

    rec_phones = {p for p in (rec.get("normalized_phone"), rec.get("normalized_alternate_phone"),
                              rec.get("whatsapp_number")) if p}
    b_phones = {p for p in (b.normalized_phone, b.normalized_alternate_phone, b.whatsapp_number) if p}
    phone_match = bool(rec_phones & b_phones)
    if phone_match:
        score += 60
        reasons.append("same phone number")

    nsim = name_similarity(rec.get("normalized_name"), rec.get("core_name"), b.normalized_name, b.core_name)
    if nsim >= 90:
        score += 30
        reasons.append(f"very similar name ({nsim}%)")
    elif nsim >= 80:
        score += 20
        reasons.append(f"similar name ({nsim}%)")

    if rec.get("normalized_address") and b.normalized_address:
        asim = fuzz.token_sort_ratio(rec["normalized_address"], b.normalized_address)
        if asim >= 85:
            score += 15
            reasons.append(f"similar address ({int(asim)}%)")

    if None not in (rec.get("latitude"), rec.get("longitude"), b.latitude, b.longitude):
        d = haversine_m(rec["latitude"], rec["longitude"], b.latitude, b.longitude)
        if d <= 50:
            score += 20
            reasons.append(f"{int(d)} m apart")
        elif d <= 150:
            score += 10
            reasons.append(f"{int(d)} m apart")

    if rec.get("pincode") and rec["pincode"] == b.pincode:
        score += 5
        reasons.append("same pincode")

    if phone_match and nsim >= 85:
        return Match(b, min(score, 100), reasons, True)
    if score >= POSSIBLE_THRESHOLD and (phone_match or nsim >= 80):
        return Match(b, min(score, 100), reasons, False)
    return None


def find_matches(db: Session, rec: dict, exclude_id: int | None = None) -> list[Match]:
    matches = [m for b in _candidates(db, rec, exclude_id) if (m := evaluate(rec, b))]
    matches.sort(key=lambda m: (m.exact, m.score), reverse=True)
    return matches


def record_from_business(b: Business) -> dict:
    keys = ["normalized_phone", "normalized_alternate_phone", "whatsapp_number", "normalized_name",
            "core_name", "normalized_address", "latitude", "longitude", "pincode", "city",
            "district", "source", "source_place_id", "is_test_data"]
    return {k: getattr(b, k) for k in keys}


FILLABLE = ["contact_name", "phone", "normalized_phone", "alternate_phone", "normalized_alternate_phone",
            "whatsapp_number", "email", "website", "address", "area", "village", "city", "taluka",
            "district", "pincode", "latitude", "longitude", "google_maps_url", "rating", "review_count",
            "normalized_address"]


def fill_missing(target: Business, rec: dict) -> list[str]:
    """Copy values only into EMPTY fields of the existing record. Returns filled field names."""
    filled = []
    for f in FILLABLE:
        if getattr(target, f) in (None, "") and rec.get(f) not in (None, ""):
            setattr(target, f, rec[f])
            filled.append(f)
    if "normalized_phone" in filled:
        target.phone_valid = True
    return filled
