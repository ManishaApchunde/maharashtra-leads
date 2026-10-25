import csv
import io

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import CollectionRun, District, GovernmentOffice, Location, Taluka
from app.services.filereader import BUSINESS_COLUMNS, REQUIRED_COLUMNS, read_table, validate_headers
from app.services.ingest import Ingestor, record_run_counts
from app.utils.maharashtra import OFFICE_TYPES
from app.utils.phone import normalize_phone
from app.utils.text import canonical_district, canonical_taluka, clean_str, title_place, validate_pincode

router = APIRouter(prefix="/import", tags=["import"])

SYNC_LIMIT = 2000  # files up to this many rows are processed in the request; bigger ones in the background


def _process(run_id: int, rows: list[dict], source: str, keyword: str | None, category: str | None):
    db = SessionLocal()
    try:
        run = db.get(CollectionRun, run_id)
        if keyword or category:
            for r in rows:
                if keyword and not r.get("keyword"):
                    r["discovered_keyword"] = keyword
                if category and not r.get("category"):
                    r["category"] = category
        summary = Ingestor(db, run).ingest_many(rows, default_source=source)
        run = db.get(CollectionRun, run_id)
        record_run_counts(run, summary)
        run.status = "completed"
        db.commit()
        return summary
    except Exception as exc:
        db.rollback()
        run = db.get(CollectionRun, run_id)
        run.status, run.message = "failed", f"{exc.__class__.__name__}: {exc}"[:1000]
        db.commit()
        raise
    finally:
        db.close()


@router.post("/csv")
async def import_csv(background: BackgroundTasks, file: UploadFile = File(...),
                     source: str = Form("CSV Import"), keyword: str | None = Form(None),
                     category: str | None = Form(None), db: Session = Depends(get_db)):
    """Upload a CSV or .xlsx of businesses. Rows without a `source` column use the `source` form field."""
    content = await file.read()
    headers, rows = read_table(content, file.filename or "upload.csv")
    missing, ignored = validate_headers(headers, REQUIRED_COLUMNS)
    if missing:
        raise HTTPException(422, {"message": "Missing required column(s)", "missing": missing,
                                  "expected_columns": BUSINESS_COLUMNS})
    if not rows:
        raise HTTPException(422, "The file has no data rows")

    run = CollectionRun(run_type="csv", source=source, file_name=file.filename, keyword=keyword,
                        category=category, status="running", total_results=len(rows))
    db.add(run)
    db.commit()

    base = {"run_id": run.id, "ignored_columns": ignored,
            "missing_optional_columns": [c for c in BUSINESS_COLUMNS if c not in headers]}
    if len(rows) <= SYNC_LIMIT:
        summary = _process(run.id, rows, source, keyword, category)
        return base | {"status": "completed", **summary}
    background.add_task(_process, run.id, rows, source, keyword, category)
    return base | {"status": "running", "total": len(rows),
                   "message": f"Large file: processing in background. Poll GET /collection/runs/{run.id}"}


@router.get("/template")
def template():
    buf = io.StringIO()
    csv.writer(buf).writerow(BUSINESS_COLUMNS)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=business_import_template.csv"})


@router.post("/government-offices")
async def import_offices(file: UploadFile = File(...), source: str = Form("CSV Import"),
                         db: Session = Depends(get_db)):
    """Columns: name, office_type, address, village, taluka, district, latitude, longitude, phone."""
    headers, rows = read_table(await file.read(), file.filename or "offices.csv", aliases=False)
    if "name" not in headers or "office_type" not in headers:
        raise HTTPException(422, "Columns 'name' and 'office_type' are required")
    type_lookup = {t.lower(): t for t in OFFICE_TYPES}
    added, skipped, errors = 0, 0, []
    for i, r in enumerate(rows, start=2):
        name = clean_str(r.get("name"))
        otype = type_lookup.get((clean_str(r.get("office_type")) or "").lower())
        if not name or not otype:
            errors.append({"row": i, "reason": "missing name or unknown office_type"})
            continue
        try:
            lat = float(r["latitude"]) if clean_str(r.get("latitude")) else None
            lng = float(r["longitude"]) if clean_str(r.get("longitude")) else None
        except ValueError:
            lat = lng = None
        district, _ = canonical_district(r.get("district"))
        dup = db.scalar(select(GovernmentOffice.id).where(GovernmentOffice.name == name,
                                                          GovernmentOffice.office_type == otype,
                                                          GovernmentOffice.district == district))
        if dup:
            skipped += 1
            continue
        ph = normalize_phone(r.get("phone"))
        db.add(GovernmentOffice(name=name, office_type=otype, address=clean_str(r.get("address")),
                                village=title_place(r.get("village")), taluka=canonical_taluka(r.get("taluka")),
                                district=district, latitude=lat, longitude=lng,
                                phone=ph.normalized or clean_str(r.get("phone")),
                                source=clean_str(r.get("source")) or source))
        added += 1
    db.commit()
    return {"total": len(rows), "added": added, "skipped_existing": skipped, "invalid": len(errors),
            "errors": errors[:200],
            "next_step": "POST /government-offices/recompute-proximity to update lead scores"}


@router.post("/geo")
async def import_geo(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Bulk-load talukas and towns/villages.

    Columns: district, taluka, location (optional), type (city|town|village|area), pincode, latitude, longitude
    """
    headers, rows = read_table(await file.read(), file.filename or "geo.csv", aliases=False)
    if "district" not in headers or "taluka" not in headers:
        raise HTTPException(422, "Columns 'district' and 'taluka' are required")
    districts = {d.name: d.id for d in db.scalars(select(District))}
    talukas = {(t.district_id, t.name.lower()): t.id for t in db.scalars(select(Taluka))}
    new_t = new_l = 0
    errors = []
    for i, r in enumerate(rows, start=2):
        dname, ok = canonical_district(r.get("district"))
        tname = canonical_taluka(r.get("taluka"))
        if not ok or not tname:
            errors.append({"row": i, "reason": f"unknown district '{r.get('district')}' or empty taluka"})
            continue
        did = districts[dname]
        key = (did, tname.lower())
        if key not in talukas:
            t = Taluka(name=tname, district_id=did)
            db.add(t)
            db.flush()
            talukas[key] = t.id
            new_t += 1
        lname = title_place(r.get("location"))
        if lname:
            ltype = (clean_str(r.get("type")) or "village").lower()
            if ltype not in {"city", "town", "village", "area"}:
                ltype = "village"
            exists = db.scalar(select(Location.id).where(Location.district_id == did,
                                                         Location.taluka_id == talukas[key],
                                                         Location.name == lname, Location.type == ltype))
            if not exists:
                pin, _ = validate_pincode(r.get("pincode"))
                try:
                    lat = float(r["latitude"]) if clean_str(r.get("latitude")) else None
                    lng = float(r["longitude"]) if clean_str(r.get("longitude")) else None
                except ValueError:
                    lat = lng = None
                db.add(Location(name=lname, type=ltype, district_id=did, taluka_id=talukas[key],
                                pincode=pin, latitude=lat, longitude=lng))
                db.flush()
                new_l += 1
    db.commit()
    return {"rows": len(rows), "new_talukas": new_t, "new_locations": new_l, "errors": errors[:200]}
