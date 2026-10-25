from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Business, BusinessCategory, Category, DuplicateCandidate
from app.schemas.business import BusinessCreate, BusinessOut, BusinessPage, BusinessUpdate
from app.services import dedup
from app.services.cleaning import clean_row
from app.services.ingest import Ingestor
from app.services.query import BusinessFilters, apply_filters, ordered
from app.services.scoring import apply_score
from app.utils.text import standardize_categories

router = APIRouter(tags=["businesses"])


def _page(db: Session, f: BusinessFilters, page: int, page_size: int) -> BusinessPage:
    stmt = apply_filters(select(Business), f)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(ordered(stmt, f.sort).offset((page - 1) * page_size).limit(page_size)).unique().all()
    return BusinessPage(total=total or 0, page=page, page_size=page_size,
                        items=[BusinessOut.from_model(b) for b in rows])


@router.get("/businesses", response_model=BusinessPage)
def list_businesses(f: BusinessFilters = Depends(), page: int = Query(1, ge=1),
                    page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    return _page(db, f, page, page_size)


@router.get("/leads", response_model=BusinessPage)
def list_leads(f: BusinessFilters = Depends(), page: int = Query(1, ge=1),
               page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    """Call list: same filters as /businesses, but hides Invalid / Do Not Contact / Converted by default."""
    if not f.lead_status:
        f.lead_status = "New,Not Contacted,Contacted,Interested,Follow Up"
    return _page(db, f, page, page_size)


@router.get("/businesses/near-government-offices", response_model=BusinessPage)
def near_government_offices(f: BusinessFilters = Depends(), radius_m: int = Query(1000, ge=50, le=2000),
                            page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                            db: Session = Depends(get_db)):
    f.near_office_m = radius_m
    if f.sort == "score":
        f.sort = "distance"
    return _page(db, f, page, page_size)


@router.get("/businesses/{business_id}", response_model=BusinessOut)
def get_business(business_id: int, db: Session = Depends(get_db)):
    b = db.get(Business, business_id)
    if not b:
        raise HTTPException(404, "Business not found")
    return BusinessOut.from_model(b)


@router.post("/businesses", status_code=201)
def create_business(data: BusinessCreate, db: Session = Depends(get_db)):
    """Manual entry. Returns the outcome so the form can say 'already exists as #123'."""
    ing = Ingestor(db)
    outcome, info = ing.ingest_one(data.model_dump(exclude={"notes"}), default_source="Manual Entry")
    if outcome == "invalid":
        db.rollback()
        raise HTTPException(422, info["reason"])
    bid = info.get("id") or info.get("existing_id")
    if data.notes and outcome != "duplicate":
        db.get(Business, bid).notes = data.notes
    db.commit()
    return {"outcome": outcome, "business": BusinessOut.from_model(db.get(Business, bid)), **info}


@router.put("/businesses/{business_id}", response_model=BusinessOut)
def update_business(business_id: int, data: BusinessUpdate, db: Session = Depends(get_db)):
    b = db.get(Business, business_id)
    if not b:
        raise HTTPException(404, "Business not found")
    changes = data.model_dump(exclude_unset=True)

    contact_fields = {"shop_name", "phone", "alternate_phone", "whatsapp_number", "email", "address", "area",
                      "village", "city", "taluka", "district", "pincode", "latitude", "longitude"}
    if contact_fields & changes.keys():
        # Re-run cleaning on the merged record so normalised columns stay correct.
        merged = {k: getattr(b, k) for k in contact_fields | {"contact_name", "website", "google_maps_url",
                                                             "source", "source_url", "category"}}
        merged.update({k: v for k, v in changes.items() if k in contact_fields})
        cr = clean_row(merged, b.source)
        if cr.record is None:
            raise HTTPException(422, cr.invalid_reason)
        for k in ("shop_name", "phone", "normalized_phone", "phone_valid", "alternate_phone",
                  "normalized_alternate_phone", "whatsapp_number", "email", "address", "area", "village",
                  "city", "taluka", "district", "pincode", "latitude", "longitude", "normalized_name",
                  "core_name", "normalized_address", "quality_flags"):
            setattr(b, k, cr.record[k])
        ing = Ingestor(db)
        ing.link_geo(b)
        ing.refresh_proximity(b)

    for k in ("contact_name", "website", "google_maps_url", "verification_status", "response_status",
              "interested", "demo_given", "converted", "notes", "next_followup_date"):
        if k in changes:
            setattr(b, k, changes[k])
    if changes.get("verification_status") == "verified":
        b.last_verified_at = datetime.now(timezone.utc)

    if "lead_status" in changes:
        b.lead_status = changes["lead_status"]
        if b.lead_status in {"Contacted", "Interested", "Follow Up", "Not Interested", "Converted"} and not b.contacted:
            b.contacted, b.contacted_at = True, datetime.now(timezone.utc)
        if b.lead_status == "Converted":
            b.converted = True
        if b.lead_status == "Interested":
            b.interested = True
    if "contacted" in changes:
        b.contacted = changes["contacted"]
        b.contacted_at = (b.contacted_at or datetime.now(timezone.utc)) if b.contacted else None

    if changes.get("categories") is not None:
        cats = []
        for c in changes["categories"]:
            cats += standardize_categories(c)
        cats = list(dict.fromkeys(cats))
        db.execute(delete(BusinessCategory).where(BusinessCategory.business_id == b.id))
        ids = {c.name: c.id for c in db.scalars(select(Category).where(Category.name.in_(cats)))}
        for name in cats:
            db.add(BusinessCategory(business_id=b.id, category_id=ids[name]))
        from app.utils.text import primary_category
        b.category = primary_category(cats)

    db.flush()
    db.refresh(b)
    apply_score(b)
    db.commit()
    db.refresh(b)
    return BusinessOut.from_model(b)


@router.post("/businesses/{business_id}/check-duplicates")
def check_one(business_id: int, db: Session = Depends(get_db)):
    b = db.get(Business, business_id)
    if not b:
        raise HTTPException(404, "Business not found")
    matches = dedup.find_matches(db, dedup.record_from_business(b), exclude_id=b.id)
    return [{"business_id": m.business.id, "shop_name": m.business.shop_name, "score": m.score,
             "reasons": m.reasons, "exact": m.exact} for m in matches]


@router.delete("/businesses/{business_id}", status_code=204)
def delete_business(business_id: int, db: Session = Depends(get_db)):
    b = db.get(Business, business_id)
    if not b:
        raise HTTPException(404, "Business not found")
    db.execute(delete(DuplicateCandidate).where(
        (DuplicateCandidate.business_id == business_id) | (DuplicateCandidate.matched_business_id == business_id)))
    db.delete(b)
    db.commit()
