from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import GovernmentOffice
from app.schemas.business import GovOfficeIn, GovOfficeOut
from app.services.proximity import recompute_all
from app.services.scoring import rescore_all
from app.utils.text import canonical_district, canonical_taluka

router = APIRouter(prefix="/government-offices", tags=["government offices"])


@router.get("", response_model=list[GovOfficeOut])
def list_offices(district: str | None = None, office_type: str | None = None, db: Session = Depends(get_db)):
    q = select(GovernmentOffice)
    if district:
        q = q.where(GovernmentOffice.district == canonical_district(district)[0])
    if office_type:
        q = q.where(GovernmentOffice.office_type == office_type)
    return db.scalars(q.order_by(GovernmentOffice.district, GovernmentOffice.name).limit(5000)).all()


@router.post("", response_model=GovOfficeOut, status_code=201)
def create_office(data: GovOfficeIn, db: Session = Depends(get_db)):
    o = GovernmentOffice(**data.model_dump())
    o.district = canonical_district(o.district)[0]
    o.taluka = canonical_taluka(o.taluka)
    db.add(o)
    db.commit()
    return o


@router.put("/{office_id}", response_model=GovOfficeOut)
def update_office(office_id: int, data: GovOfficeIn, db: Session = Depends(get_db)):
    o = db.get(GovernmentOffice, office_id)
    if not o:
        raise HTTPException(404, "Office not found")
    for k, v in data.model_dump().items():
        setattr(o, k, v)
    o.district = canonical_district(o.district)[0]
    db.commit()
    return o


@router.delete("/{office_id}", status_code=204)
def delete_office(office_id: int, db: Session = Depends(get_db)):
    o = db.get(GovernmentOffice, office_id)
    if not o:
        raise HTTPException(404, "Office not found")
    db.delete(o)
    db.commit()


@router.post("/recompute-proximity")
def recompute(db: Session = Depends(get_db)):
    """Run after adding offices: refreshes distances for all businesses, then lead scores."""
    updated = recompute_all(db)
    rescored = rescore_all(db)
    return {"distances_updated": updated, "scores_recalculated": rescored}
