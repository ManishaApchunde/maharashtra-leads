"""One filter builder shared by /businesses, /leads and /export/csv so they always agree."""
from dataclasses import dataclass

from fastapi import Query
from sqlalchemy import Select, and_, exists, func, or_, select

from app.models import Business, BusinessCategory, Category, GovernmentOffice
from app.utils.phone import normalize_phone
from app.utils.sql import haversine_sql, json_has, nulls_last_asc
from app.utils.text import canonical_district, normalize_name

SORTS = {
    "score": (Business.lead_score.desc(),),
    "newest": (Business.created_at.desc(),),
    "name": (Business.shop_name.asc(),),
    "followup": nulls_last_asc(Business.next_followup_date),
    "distance": nulls_last_asc(Business.nearest_gov_office_m),
}


@dataclass
class BusinessFilters:
    q: str | None = Query(None, description="Search shop name, phone, address, city, taluka, district, pincode")
    district: str | None = None
    taluka: str | None = None
    city: str | None = None
    area: str | None = None
    pincode: str | None = None
    category: str | None = None
    source: str | None = None
    lead_status: str | None = None
    verification_status: str | None = None
    duplicate_status: str | None = Query(None, description="Default hides confirmed duplicates")
    has_phone: bool | None = None
    has_whatsapp: bool | None = None
    contacted: bool | None = None
    min_score: int | None = None
    max_score: int | None = None
    near_office_m: int | None = Query(None, description="Within N metres of any government office")
    office_type: str | None = Query(None, description="Restrict near_office_m to this office type")
    quality_flag: str | None = None
    include_test_data: bool = False
    followup_due: bool | None = None
    sort: str = "score"


def apply_filters(stmt: Select, f: BusinessFilters) -> Select:
    conds = []
    if f.q:
        q = f.q.strip()
        like = f"%{q}%"
        text_conds = [
            Business.shop_name.like(like), Business.address.like(like), Business.city.like(like),
            Business.taluka.like(like), Business.district.like(like), Business.area.like(like),
            Business.village.like(like),
        ]
        nn = normalize_name(q)
        if nn:
            text_conds.append(Business.normalized_name.like(f"%{nn}%"))
        digits = "".join(ch for ch in q if ch.isdigit())
        if len(digits) >= 4:
            ph = normalize_phone(q)
            needle = ph.normalized or digits[-10:]
            text_conds += [Business.normalized_phone.contains(needle),
                           Business.normalized_alternate_phone.contains(needle),
                           Business.whatsapp_number.contains(needle)]
            if len(digits) == 6:
                text_conds.append(Business.pincode == digits)
        conds.append(or_(*text_conds))
    if f.district:
        d, _ = canonical_district(f.district)
        conds.append(Business.district == d)
    if f.taluka:
        conds.append(Business.taluka == f.taluka.strip())  # utf8mb4_unicode_ci: case-insensitive
    if f.city:
        conds.append(Business.city == f.city.strip())
    if f.area:
        conds.append(Business.area.like(f"%{f.area.strip()}%"))
    if f.pincode:
        conds.append(Business.pincode == f.pincode.strip())
    if f.category:
        conds.append(exists().where(
            BusinessCategory.business_id == Business.id,
            BusinessCategory.category_id == select(Category.id).where(Category.name == f.category).scalar_subquery(),
        ))
    if f.source:
        conds.append(Business.source == f.source)
    if f.lead_status:
        conds.append(Business.lead_status.in_([s.strip() for s in f.lead_status.split(",")]))
    if f.verification_status:
        conds.append(Business.verification_status == f.verification_status)
    if f.duplicate_status:
        conds.append(Business.duplicate_status == f.duplicate_status)
    else:
        conds.append(Business.duplicate_status != "confirmed_duplicate")
    if f.has_phone is not None:
        conds.append(Business.normalized_phone.isnot(None) if f.has_phone else Business.normalized_phone.is_(None))
    if f.has_whatsapp is not None:
        conds.append(Business.whatsapp_number.isnot(None) if f.has_whatsapp else Business.whatsapp_number.is_(None))
    if f.contacted is not None:
        conds.append(Business.contacted.is_(f.contacted))
    if f.min_score is not None:
        conds.append(Business.lead_score >= f.min_score)
    if f.max_score is not None:
        conds.append(Business.lead_score <= f.max_score)
    if f.near_office_m:
        if f.office_type:
            box = f.near_office_m / 111000 * 1.1
            conds.append(Business.latitude.isnot(None))
            conds.append(exists().where(
                GovernmentOffice.office_type == f.office_type,
                GovernmentOffice.latitude.between(Business.latitude - box, Business.latitude + box),
                GovernmentOffice.longitude.between(Business.longitude - box, Business.longitude + box),
                haversine_sql(Business.latitude, Business.longitude,
                              GovernmentOffice.latitude, GovernmentOffice.longitude) <= f.near_office_m,
            ))
        else:
            conds.append(Business.nearest_gov_office_m <= f.near_office_m)
    if f.quality_flag:
        conds.append(json_has(Business.quality_flags, f.quality_flag))
    if not f.include_test_data:
        conds.append(Business.is_test_data.is_(False))
    if f.followup_due:
        conds.append(and_(Business.next_followup_date.isnot(None), Business.next_followup_date <= func.current_date()))
    return stmt.where(*conds) if conds else stmt


def ordered(stmt: Select, sort: str) -> Select:
    return stmt.order_by(*SORTS.get(sort, SORTS["score"]), Business.id)
