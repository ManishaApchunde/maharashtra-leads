from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import CollectionRun
from app.schemas.business import CollectionRequest
from app.services import district_job, places_api
from app.services.collector import search_and_ingest
from app.utils.maharashtra import SEARCH_KEYWORDS
from app.utils.talukas import MAHARASHTRA_TALUKAS
from app.utils.text import canonical_district

router = APIRouter(prefix="/collection", tags=["data collection"])


def _run_out(r: CollectionRun, with_errors: bool = False) -> dict:
    out = {k: getattr(r, k) for k in ("id", "run_type", "source", "district", "taluka", "city", "category",
                                      "keyword", "search_area", "file_name", "total_results", "new_count",
                                      "duplicate_count", "possible_duplicate_count", "invalid_count",
                                      "status", "message", "created_at")}
    if with_errors:
        out["errors"] = r.errors
    return out


@router.get("/runs")
def list_runs(district: str | None = None, run_type: str | None = None, page: int = Query(1, ge=1),
              page_size: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    q = select(CollectionRun)
    if district:
        q = q.where(CollectionRun.district == canonical_district(district)[0])
    if run_type:
        q = q.where(CollectionRun.run_type == run_type)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(CollectionRun.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "items": [_run_out(r) for r in rows]}


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    r = db.get(CollectionRun, run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return _run_out(r, with_errors=True)


@router.get("/keywords")
def keywords():
    return SEARCH_KEYWORDS


@router.get("/status")
def status():
    """Key counts only - the keys themselves are never returned."""
    keys = places_api.key_ring().status() if get_settings().places_api_keys else None
    return {"google_places_configured": bool(keys), "google_places_keys": keys}


@router.post("/run")
def run_collection(req: CollectionRequest, db: Session = Depends(get_db)):
    """Search one area + keyword with the official Google Places API and ingest the results."""
    district, ok = canonical_district(req.district)
    if not ok:
        raise HTTPException(422, f"Unknown district '{req.district}'")
    try:
        run, _ = search_and_ingest(db, places_api.key_ring(), district=district, keyword=req.keyword,
                                   taluka=req.taluka, city=req.city, category=req.category, max_pages=req.max_pages)
    except places_api.PlacesAPIError as exc:
        raise HTTPException(400, str(exc))
    return _run_out(run, with_errors=True)


# --- automatic whole-district collection ------------------------------------------------------
class DistrictJobRequest(BaseModel):
    district: str | None = Field(None, description="One district, or leave empty with all_districts=true")
    all_districts: bool = False
    keywords: list[str] | None = Field(None, description="Default: every keyword in /collection/keywords")
    taluka_pages: int = Field(3, ge=1, le=3)
    village_pages: int = Field(1, ge=1, le=3)
    include_villages: bool = True
    include_city_areas: bool = True
    grid_sweep: bool = False
    grid_km: float = Field(5.0, ge=1.0, le=30.0)
    grid_pages: int = Field(1, ge=1, le=3)
    skip_done: bool = True


def _job_options(req: DistrictJobRequest) -> district_job.JobOptions:
    if req.all_districts:
        districts = district_job.all_districts()
    else:
        d, ok = canonical_district(req.district)
        if not ok:
            raise HTTPException(422, f"Unknown district '{req.district}'")
        districts = [d]
    keywords = [k.strip() for k in (req.keywords or SEARCH_KEYWORDS) if k and k.strip()]
    keywords = list(dict.fromkeys(keywords))
    if not keywords:
        raise HTTPException(422, "Pick at least one keyword")
    return district_job.JobOptions(districts=districts, keywords=keywords, taluka_pages=req.taluka_pages,
                                   village_pages=req.village_pages, include_villages=req.include_villages,
                                   include_city_areas=req.include_city_areas, grid_sweep=req.grid_sweep,
                                   grid_km=req.grid_km, grid_pages=req.grid_pages, skip_done=req.skip_done)


@router.post("/district-plan")
def district_plan(req: DistrictJobRequest, db: Session = Depends(get_db)):
    """How many searches / API requests a whole-district job will make (before starting it)."""
    return district_job.plan(db, _job_options(req))


@router.post("/district-jobs", status_code=201)
def start_district_job(req: DistrictJobRequest):
    """Loop every taluka, village/town and keyword of the district(s) in the background."""
    if not get_settings().places_api_keys:
        raise HTTPException(400, "GOOGLE_PLACES_API_KEYS is not set in backend/.env")
    try:
        job = district_job.manager.start(_job_options(req))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))
    return job.to_dict()


@router.get("/district-jobs")
def list_district_jobs():
    active = district_job.manager.active()
    return {"active": active.to_dict() if active else None,
            "items": [j.to_dict() for j in district_job.manager.all()[:20]]}


@router.get("/district-jobs/{job_id}")
def get_district_job(job_id: str):
    job = district_job.manager.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found (jobs are kept in memory until the server restarts)")
    return job.to_dict()


@router.post("/district-jobs/{job_id}/cancel")
def cancel_district_job(job_id: str):
    job = district_job.manager.cancel(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.to_dict()


@router.get("/talukas-reference")
def talukas_reference():
    """Built-in list of all Maharashtra talukas, by district."""
    return MAHARASHTRA_TALUKAS
