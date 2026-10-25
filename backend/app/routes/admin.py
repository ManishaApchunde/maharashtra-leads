from fastapi import APIRouter, Depends
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Business, DuplicateCandidate
from app.services.proximity import recompute_all
from app.services.scoring import RULES, rescore_all

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/scoring-rules")
def scoring_rules():
    return {"rules": RULES, "note": "Marketing-priority checklist, not a statistical model. Max 100."}


@router.post("/rescore")
def rescore(db: Session = Depends(get_db)):
    return {"distances_updated": recompute_all(db), "scores_recalculated": rescore_all(db)}


@router.delete("/test-data")
def purge_test_data(db: Session = Depends(get_db)):
    """Removes every record whose source is TEST_DATA. Real data is untouched."""
    ids = select(Business.id).where(Business.is_test_data.is_(True))
    n = db.scalar(select(func.count()).select_from(ids.subquery()))
    db.execute(delete(DuplicateCandidate).where(DuplicateCandidate.business_id.in_(ids) |
                                                DuplicateCandidate.matched_business_id.in_(ids)))
    db.execute(delete(Business).where(Business.is_test_data.is_(True)))
    db.commit()
    return {"deleted_test_records": n}
