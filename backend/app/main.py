from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.database import engine
from app.deps import require_api_key
from app.routes import admin, analytics, businesses, collection, duplicates, exports, geo, gov_offices, imports


def mark_interrupted_runs() -> None:
    """Background imports die with the server; don't leave them showing 'running' forever.
    Rows already committed are kept; re-uploading the file is safe (duplicates are merged)."""
    with engine.begin() as conn:
        conn.execute(text("UPDATE collection_runs SET status = 'interrupted', "
                          "message = 'Server restarted during import. Re-upload the file; existing rows are merged as duplicates.' "
                          "WHERE status = 'running' AND run_type <> 'api'"))
        conn.execute(text("UPDATE collection_runs SET status = 'interrupted', "
                          "message = 'Server restarted during this search. Run the district job again with \"skip already searched\" on.' "
                          "WHERE status = 'running' AND run_type = 'api'"))


def seed_talukas() -> None:
    """Add any of Maharashtra's talukas that are missing, so the Taluka dropdowns and the
    whole-district collector know every taluka. Existing rows are never changed."""
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import District, Taluka
    from app.utils.talukas import MAHARASHTRA_TALUKAS

    with SessionLocal() as db:
        have = {(t.district_id, t.name.lower()) for t in db.scalars(select(Taluka))}
        for d in db.scalars(select(District)):
            for name in MAHARASHTRA_TALUKAS.get(d.name, []):
                if (d.id, name.lower()) not in have:
                    db.add(Taluka(name=name, district_id=d.id))
                    have.add((d.id, name.lower()))
        db.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    mark_interrupted_runs()
    try:
        seed_talukas()
    except Exception as exc:  # noqa: BLE001 - never block startup on reference data
        print(f"WARNING: could not seed talukas: {exc}")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Maharashtra Xerox & Print Shop Lead Database",
    description="Lead database for marketing Land Recorder Bot across Maharashtra.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

protected = [Depends(require_api_key)]
for r in (businesses.router, geo.router, duplicates.router, imports.router, exports.router,
          gov_offices.router, analytics.router, collection.router, admin.router):
    app.include_router(r, dependencies=protected)


@app.get("/health", tags=["health"])
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
