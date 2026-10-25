from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Business, BusinessCategory, Category, District, DuplicateCandidate, Taluka
from app.utils.sql import count_if, json_has
from app.utils.text import canonical_district

router = APIRouter(tags=["analytics"])


def _scope(stmt: Select, district: str | None, taluka: str | None, city: str | None,
           include_test_data: bool) -> Select:
    stmt = stmt.where(Business.duplicate_status != "confirmed_duplicate")
    if not include_test_data:
        stmt = stmt.where(Business.is_test_data.is_(False))
    if district:
        stmt = stmt.where(Business.district == canonical_district(district)[0])
    if taluka:
        stmt = stmt.where(Business.taluka == taluka)  # case-insensitive collation
    if city:
        stmt = stmt.where(Business.city == city)
    return stmt


@router.get("/analytics")
def analytics(district: str | None = None, taluka: str | None = None, city: str | None = None,
              include_test_data: bool = False, db: Session = Depends(get_db)):
    s = lambda stmt: _scope(stmt, district, taluka, city, include_test_data)  # noqa: E731
    cnt = count_if

    row = db.execute(s(select(
        func.count().label("total"),
        cnt(Business.normalized_phone.isnot(None)).label("with_phone"),
        cnt(Business.whatsapp_number.isnot(None)).label("with_whatsapp"),
        cnt(Business.verification_status == "verified").label("verified"),
        cnt(Business.verification_status == "unverified").label("unverified"),
        cnt(Business.duplicate_status == "possible_duplicate").label("duplicate_candidates"),
        cnt(Business.lead_status == "New").label("new_leads"),
        cnt(Business.contacted.is_(True)).label("contacted"),
        cnt(Business.lead_status == "Interested").label("interested"),
        cnt(or_(Business.converted.is_(True), Business.lead_status == "Converted")).label("converted"),
        cnt(Business.lead_score >= 60).label("high_score"),
        cnt(Business.nearest_gov_office_m <= 1000).label("near_gov_office_1km"),
        func.count(func.distinct(Business.district)).label("districts_covered"),
        func.count(func.distinct(Business.taluka)).label("talukas_covered"),
        func.coalesce(func.avg(Business.lead_score), 0).label("avg_score"),
    ))).one()

    def group(col, limit=40):
        q = s(select(col.label("k"), func.count().label("n"))).group_by(col).order_by(func.count().desc()).limit(limit)
        return [{"name": r.k or "(blank)", "count": r.n} for r in db.execute(q)]

    by_category = db.execute(
        s(select(Category.name, func.count()).join(BusinessCategory, BusinessCategory.category_id == Category.id)
          .join(Business, Business.id == BusinessCategory.business_id))
        .group_by(Category.name).order_by(func.count().desc())).all()

    score_band = case((Business.lead_score >= 80, "80-100"), (Business.lead_score >= 60, "60-79"),
                      (Business.lead_score >= 40, "40-59"), (Business.lead_score >= 20, "20-39"), else_="0-19")

    return {
        "scope": {"district": district, "taluka": taluka, "city": city},
        "totals": dict(row._mapping) | {
            "avg_score": round(float(row.avg_score), 1),
            "districts_in_master": db.scalar(select(func.count()).select_from(District)),
            "talukas_in_master": db.scalar(select(func.count()).select_from(Taluka)),
        },
        "by_district": group(Business.district),
        "by_taluka": group(Business.taluka) if district else [],
        "by_city": group(Business.city) if taluka or district else [],
        "by_category": [{"name": n, "count": c} for n, c in by_category],
        "by_lead_status": group(Business.lead_status),
        "by_source": group(Business.source),
        "by_score_band": sorted(group(score_band), key=lambda x: x["name"]),
    }


@router.get("/data-quality")
def data_quality(district: str | None = None, taluka: str | None = None, city: str | None = None,
                 include_test_data: bool = False, db: Session = Depends(get_db)):
    old_cutoff = datetime.now(timezone.utc) - timedelta(days=get_settings().OLD_RECORD_DAYS)
    flag = lambda f: json_has(Business.quality_flags, f)  # noqa: E731
    cnt = count_if
    q = _scope(select(
        func.count().label("total"),
        cnt(flag("missing_phone")).label("missing_phone"),
        cnt(flag("invalid_phone")).label("invalid_phone"),
        cnt(flag("missing_address")).label("missing_address"),
        cnt(flag("missing_district")).label("missing_district"),
        cnt(flag("unrecognized_district")).label("unrecognized_district"),
        cnt(flag("missing_pincode")).label("missing_pincode"),
        cnt(flag("invalid_pincode") | flag("pincode_outside_maharashtra")).label("bad_pincode"),
        cnt(Business.taluka.is_(None)).label("missing_taluka"),
        cnt(Business.latitude.is_(None)).label("missing_coordinates"),
        cnt(Business.duplicate_status == "possible_duplicate").label("duplicate_candidates"),
        cnt(Business.verification_status == "unverified").label("unverified"),
        cnt(or_(Business.last_verified_at < old_cutoff,
                (Business.last_verified_at.is_(None)) & (Business.created_at < old_cutoff))).label("old_records"),
    ), district, taluka, city, include_test_data)
    totals = dict(db.execute(q).one()._mapping)
    pending_pairs = db.scalar(_scope(
        select(func.count()).select_from(DuplicateCandidate)
        .join(Business, Business.id == DuplicateCandidate.business_id)
        .where(DuplicateCandidate.status == "pending"), district, taluka, city, include_test_data))
    descriptions = {
        "missing_phone": ("missing_phone", "No phone number in the source"),
        "invalid_phone": ("invalid_phone", "Phone present but not a valid 10-digit Indian number"),
        "missing_address": ("missing_address", "No street address"),
        "missing_district": ("missing_district", "District blank"),
        "unrecognized_district": ("unrecognized_district", "District text not one of the 36 districts"),
        "missing_pincode": ("missing_pincode", "No PIN code"),
        "bad_pincode": ("invalid_pincode", "PIN code malformed or outside Maharashtra (40xxxx-44xxxx)"),
        "missing_taluka": (None, "Taluka blank"),
        "missing_coordinates": (None, "No latitude/longitude - proximity can't be computed"),
        "duplicate_candidates": (None, "Waiting for duplicate review"),
        "unverified": (None, "Never verified by a person"),
        "old_records": (None, f"Not verified in the last {get_settings().OLD_RECORD_DAYS} days"),
    }
    issues = [{"key": k, "count": totals[k], "quality_flag": descriptions[k][0], "description": descriptions[k][1]}
              for k in descriptions]
    return {"total": totals["total"], "pending_duplicate_pairs": pending_pairs, "issues": issues}
