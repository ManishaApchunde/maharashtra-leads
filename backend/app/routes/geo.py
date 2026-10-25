from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, union
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Business, Category, DataSource, District, Location, Taluka
from app.schemas.business import LocationIn, TalukaIn
from app.utils.maharashtra import LEAD_STATUSES, OFFICE_TYPES, SEARCH_KEYWORDS, VERIFICATION_STATUSES
from app.utils.text import canonical_district, canonical_taluka, title_place

router = APIRouter(tags=["geography & reference"])


@router.get("/districts")
def list_districts(db: Session = Depends(get_db)):
    biz = dict(db.execute(select(Business.district_id, func.count()).where(
        Business.is_test_data.is_(False), Business.duplicate_status != "confirmed_duplicate")
        .group_by(Business.district_id)).all())
    tal = dict(db.execute(select(Taluka.district_id, func.count()).group_by(Taluka.district_id)).all())
    return [{"id": d.id, "name": d.name, "state": d.state, "taluka_count": tal.get(d.id, 0),
             "business_count": biz.get(d.id, 0)}
            for d in db.scalars(select(District).order_by(District.name))]


@router.get("/districts/{district_id}")
def get_district(district_id: int, db: Session = Depends(get_db)):
    d = db.get(District, district_id)
    if not d:
        raise HTTPException(404, "District not found")
    return {"id": d.id, "name": d.name, "state": d.state}


@router.get("/districts/{district_id}/talukas")
def list_talukas(district_id: int, db: Session = Depends(get_db)):
    biz = dict(db.execute(select(Business.taluka_id, func.count()).where(Business.district_id == district_id)
                          .group_by(Business.taluka_id)).all())
    return [{"id": t.id, "name": t.name, "district_id": t.district_id, "business_count": biz.get(t.id, 0)}
            for t in db.scalars(select(Taluka).where(Taluka.district_id == district_id).order_by(Taluka.name))]


@router.get("/talukas/{taluka_id}/locations")
def list_locations(taluka_id: int, db: Session = Depends(get_db)):
    return [{"id": loc.id, "name": loc.name, "type": loc.type, "pincode": loc.pincode,
             "latitude": loc.latitude, "longitude": loc.longitude}
            for loc in db.scalars(select(Location).where(Location.taluka_id == taluka_id).order_by(Location.name))]


@router.post("/talukas", status_code=201)
def create_taluka(data: TalukaIn, db: Session = Depends(get_db)):
    if not db.get(District, data.district_id):
        raise HTTPException(404, "District not found")
    t = Taluka(name=canonical_taluka(data.name), district_id=data.district_id)
    db.add(t)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Taluka already exists in this district")
    return {"id": t.id, "name": t.name, "district_id": t.district_id}


@router.post("/locations", status_code=201)
def create_location(data: LocationIn, db: Session = Depends(get_db)):
    loc = Location(**data.model_dump() | {"name": title_place(data.name)})
    db.add(loc)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Location already exists")
    return {"id": loc.id, "name": loc.name}


@router.get("/filters/cities")
def city_options(district: str | None = None, taluka: str | None = None, db: Session = Depends(get_db)):
    """City/town/village names for the cascading filter: from businesses and the locations table."""
    b = select(Business.city.label("name")).where(Business.city.isnot(None))
    v = select(Business.village.label("name")).where(Business.village.isnot(None))
    loc = select(Location.name.label("name")).join(District, District.id == Location.district_id) \
        .outerjoin(Taluka, Taluka.id == Location.taluka_id).where(Location.type != "area")
    if district:
        d, _ = canonical_district(district)
        b, v, loc = b.where(Business.district == d), v.where(Business.district == d), loc.where(District.name == d)
    if taluka:
        b = b.where(Business.taluka == taluka)  # case-insensitive collation
        v = v.where(Business.taluka == taluka)
        loc = loc.where(Taluka.name == taluka)
    names = db.scalars(select(union(b, v, loc).subquery().c.name).distinct().order_by("name").limit(2000)).all()
    return sorted({n for n in names if n})


@router.get("/filters/areas")
def area_options(district: str | None = None, city: str | None = None, db: Session = Depends(get_db)):
    q = select(Business.area).where(Business.area.isnot(None)).distinct()
    if district:
        q = q.where(Business.district == canonical_district(district)[0])
    if city:
        q = q.where(Business.city == city)
    return sorted(a for a in db.scalars(q.limit(2000)) if a)


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    from app.models import BusinessCategory
    counts = dict(db.execute(select(BusinessCategory.category_id, func.count()).group_by(BusinessCategory.category_id)).all())
    return [{"id": c.id, "name": c.name, "business_count": counts.get(c.id, 0)}
            for c in db.scalars(select(Category).order_by(Category.id))]


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Business.data_source_id, func.count()).group_by(Business.data_source_id)).all())
    return [{"id": s.id, "source_name": s.source_name, "source_type": s.source_type, "source_url": s.source_url,
             "collection_method": s.collection_method, "created_at": s.created_at,
             "business_count": counts.get(s.id, 0)}
            for s in db.scalars(select(DataSource).order_by(DataSource.id))]


@router.get("/meta")
def meta():
    return {"lead_statuses": LEAD_STATUSES, "verification_statuses": VERIFICATION_STATUSES,
            "office_types": OFFICE_TYPES, "search_keywords": SEARCH_KEYWORDS,
            "duplicate_statuses": ["unique", "possible_duplicate", "confirmed_duplicate"]}
