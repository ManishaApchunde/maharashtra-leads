"""One Google Places search (area + keyword) -> clean -> dedup -> save, recorded as a CollectionRun.

Shared by the single-search endpoint and the automatic whole-district job.
"""
import httpx
from sqlalchemy.orm import Session

from app.models import CollectionRun
from app.services import places_api
from app.services.ingest import Ingestor, record_run_counts
from app.utils.text import primary_category, standardize_categories


def area_label(district: str, taluka: str | None = None, city: str | None = None) -> str:
    return ", ".join(p for p in (city, taluka and f"{taluka} taluka", f"{district} district", "Maharashtra") if p)


def keyword_category(keyword: str) -> str | None:
    """'cyber cafe' -> 'Cyber Cafe', 'Xerox centre' -> 'Xerox'. None when the keyword is generic."""
    cats = standardize_categories(keyword)
    cat = primary_category(cats)
    return None if cat == "Other" else cat


def search_and_ingest(db: Session, api_key, *, district: str, keyword: str, taluka: str | None = None,
                      city: str | None = None, category: str | None = None, max_pages: int = 1,
                      client: httpx.Client | None = None, rectangle: dict | None = None,
                      search_area: str | None = None) -> tuple[CollectionRun, int]:
    """Returns (finished run, api_requests). Raises places_api.PlacesAPIError.

    api_key: places_api.key_ring() (or a key / list of keys). On an error the pages that did succeed
    are still saved, and the run is marked "failed" (or "paused" for quota) - never "completed" - so
    "skip already searched" repeats it later; dedup by place ID stops those rows being added twice.
    """
    area = search_area or area_label(district, taluka, city)
    query = keyword if rectangle else f"{keyword} in {area}"
    run = CollectionRun(run_type="api", source=places_api.SOURCE_NAME, district=district, taluka=taluka,
                        city=city, category=category, keyword=keyword, search_area=area, status="running")
    db.add(run)
    db.commit()
    try:
        places, requests = places_api.search_text_counted(api_key, query, max_pages, client, rectangle)
    except places_api.PlacesAPIError as exc:
        if exc.partial_places:
            run = _ingest(db, run, exc.partial_places, district, taluka, keyword, category)
        run.status = "paused" if exc.quota_exhausted else "failed"
        run.message = f"[{exc.kind}] {exc}"[:1000]
        db.commit()
        exc.run = run
        raise

    run = _ingest(db, run, places, district, taluka, keyword, category)
    run.status, run.message = "completed", f"Query: {query}"
    db.commit()
    return run, requests


def _ingest(db: Session, run: CollectionRun, places: list[dict], district: str, taluka: str | None,
            keyword: str, category: str | None) -> CollectionRun:
    rows, outside = [], 0
    for p in places:
        state = places_api.place_state(p)
        if state and "maharashtra" not in state.lower():
            outside += 1
            continue
        rows.append(places_api.place_to_row(p, district, taluka, keyword, category))

    summary = Ingestor(db, run).ingest_many(rows, default_source=places_api.SOURCE_NAME, start_row=1)
    summary["total"] += outside
    summary["invalid"] += outside
    if outside:
        summary["errors"].append({"row": None, "shop_name": "", "reason": f"{outside} result(s) outside Maharashtra"})
    run = db.get(CollectionRun, run.id)
    record_run_counts(run, summary)
    return run
