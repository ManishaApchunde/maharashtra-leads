from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Business, DuplicateCandidate
from app.schemas.business import BusinessOut
from app.services import dedup
from app.services.scoring import apply_score

router = APIRouter(prefix="/duplicates", tags=["duplicates"])


def _pair(c: DuplicateCandidate) -> dict:
    return {"id": c.id, "match_score": c.match_score, "reasons": c.reasons, "status": c.status,
            "created_at": c.created_at, "resolved_at": c.resolved_at,
            "business": BusinessOut.from_model(c.business),
            "matched_business": BusinessOut.from_model(c.matched_business)}


@router.get("")
def list_candidates(status: str = "pending", district: str | None = None, page: int = Query(1, ge=1),
                    page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    q = select(DuplicateCandidate).where(DuplicateCandidate.status == status)
    if district:
        q = q.join(Business, Business.id == DuplicateCandidate.business_id).where(Business.district == district)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(DuplicateCandidate.match_score.desc(), DuplicateCandidate.id)
                      .offset((page - 1) * page_size).limit(page_size)).unique().all()
    return {"total": total, "page": page, "page_size": page_size, "items": [_pair(c) for c in rows]}


class CheckRequest(BaseModel):
    business_ids: list[int] | None = None   # omit to re-check every unique record (batched)
    limit: int = 5000


@router.post("/check")
def check(req: CheckRequest, db: Session = Depends(get_db)):
    """Re-run duplicate detection, e.g. after editing records or loosening thresholds."""
    q = select(Business).where(Business.duplicate_status != "confirmed_duplicate")
    if req.business_ids:
        q = q.where(Business.id.in_(req.business_ids))
    q = q.order_by(Business.id).limit(req.limit)
    checked = new_pairs = 0
    for b in db.scalars(q).unique().all():
        checked += 1
        for m in dedup.find_matches(db, dedup.record_from_business(b), exclude_id=b.id)[:5]:
            # Store each pair once, newer record -> older record
            newer, older = (b, m.business) if b.id > m.business.id else (m.business, b)
            exists = db.scalar(select(DuplicateCandidate.id).where(
                ((DuplicateCandidate.business_id == newer.id) & (DuplicateCandidate.matched_business_id == older.id))))
            if exists:
                continue
            db.add(DuplicateCandidate(business_id=newer.id, matched_business_id=older.id,
                                      match_score=m.score, reasons=m.reasons))
            if newer.duplicate_status == "unique":
                newer.duplicate_status = "possible_duplicate"
            new_pairs += 1
        db.flush()
    db.commit()
    return {"checked": checked, "new_candidate_pairs": new_pairs}


class ConfirmRequest(BaseModel):
    merge_missing_fields: bool = True   # copy contact details into the kept record (never overwrites)
    keep: str = "matched"               # "matched" keeps the older record; "business" keeps the newer one


@router.post("/{candidate_id}/confirm")
def confirm(candidate_id: int, req: ConfirmRequest | None = None, db: Session = Depends(get_db)):
    req = req or ConfirmRequest()
    c = db.get(DuplicateCandidate, candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found")
    keep, dup = (c.matched_business, c.business) if req.keep == "matched" else (c.business, c.matched_business)
    filled = []
    if req.merge_missing_fields:
        rec = {f: getattr(dup, f) for f in dedup.FILLABLE}
        filled = dedup.fill_missing(keep, rec)
        if not keep.notes and dup.notes:
            keep.notes = dup.notes
    # The duplicate is kept in the database (nothing is deleted), just marked and linked.
    dup.duplicate_status = "confirmed_duplicate"
    dup.duplicate_of_id = keep.id
    c.status, c.resolved_at = "confirmed", datetime.now(timezone.utc)
    # Other open pairs involving the duplicate are now moot
    for other in db.scalars(select(DuplicateCandidate).where(
            DuplicateCandidate.status == "pending", DuplicateCandidate.id != c.id,
            (DuplicateCandidate.business_id == dup.id) | (DuplicateCandidate.matched_business_id == dup.id))):
        other.status, other.resolved_at = "rejected", datetime.now(timezone.utc)
    _settle(db, keep)
    db.flush()
    apply_score(keep)
    db.commit()
    return {"kept_id": keep.id, "duplicate_id": dup.id, "filled_fields": filled}


@router.post("/{candidate_id}/reject")
def reject(candidate_id: int, db: Session = Depends(get_db)):
    c = db.get(DuplicateCandidate, candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found")
    c.status, c.resolved_at = "rejected", datetime.now(timezone.utc)
    db.flush()
    _settle(db, c.business)
    _settle(db, c.matched_business)
    db.commit()
    return {"ok": True, "business_status": c.business.duplicate_status}


def _settle(db: Session, b: Business) -> None:
    """A record with no remaining pending pairs goes back to 'unique'."""
    if b.duplicate_status != "possible_duplicate":
        return
    pending = db.scalar(select(func.count()).select_from(DuplicateCandidate).where(
        DuplicateCandidate.status == "pending",
        (DuplicateCandidate.business_id == b.id) | (DuplicateCandidate.matched_business_id == b.id)))
    if not pending:
        b.duplicate_status = "unique"
