"""Automatic whole-district collection.

Pick a district (or all 36) and the job loops, for EVERY keyword:
  1. every taluka of the district (+ the taluka's main town when its name differs)
  2. big-city sub-areas (Pune, Mumbai, Thane, Nagpur, ...)
  3. every village / town known to the database for that district - including the
     towns discovered by steps 1-2, and any village list you imported (POST /import/geo)
  4. optional: a map-grid sweep of the whole district, which also reaches villages
     whose names are not in the database

Runs in a background thread (one job at a time, so Google quota is not burst).
Every search is saved as a normal CollectionRun, so "skip already searched" makes a
stopped or interrupted job resume where it left off.

Statuses
  job:       queued | running | paused (Google quota used up) | completed | failed | cancelled
  district:  Pending | Running | Paused | Failed | Completed
A district is Completed only when every planned search (area x keyword, all pages) succeeded
in this job or an earlier one - never just because it already has rows in the database.
"""
import math
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select

from app.config import get_settings
from app.database import SessionLocal
from app.models import Business, CollectionRun, District, Location, Taluka
from app.services import places_api
from app.services.collector import area_label, keyword_category, search_and_ingest
from app.utils.maharashtra import DISTRICTS
from app.utils.talukas import CITY_AREAS, search_talukas, taluka_hq

PAUSE_BETWEEN_SEARCHES = 0.4   # seconds
MAX_RETRIES = 4
MAX_GRID_CELLS = 3000


@dataclass
class Area:
    district: str
    taluka: str | None = None
    city: str | None = None
    pages: int = 1
    rectangle: dict | None = None
    label: str | None = None

    @property
    def search_area(self) -> str:
        return self.label or area_label(self.district, self.taluka, self.city)


@dataclass
class JobOptions:
    districts: list[str]
    keywords: list[str]
    taluka_pages: int = 3
    village_pages: int = 1
    include_villages: bool = True
    include_city_areas: bool = True
    grid_sweep: bool = False
    grid_km: float = 5.0
    grid_pages: int = 1
    skip_done: bool = True


@dataclass
class Job:
    id: str
    options: JobOptions
    status: str = "queued"          # queued | running | paused | completed | cancelled | failed
    district: str | None = None     # district being worked on now
    district_index: int = 0
    phase: str = ""
    total_steps: int = 0
    done_steps: int = 0
    skipped_steps: int = 0
    failed_steps: int = 0
    api_requests: int = 0
    current: str = ""
    totals: dict = field(default_factory=lambda: {"results": 0, "new": 0, "duplicates": 0,
                                                  "possible_duplicates": 0, "invalid": 0})
    per_district: dict = field(default_factory=dict)
    log: list = field(default_factory=list)
    error: str | None = None
    api_key: dict = field(default_factory=dict)   # which key is in use: {"configured", "usable", "active", "rejected"}
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel: threading.Event = field(default_factory=threading.Event)

    def add_log(self, msg: str) -> None:
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.log.append(f"{stamp}  {msg}")
        del self.log[:-80]

    def to_dict(self) -> dict:
        o = self.options
        return {
            "id": self.id, "status": self.status, "district": self.district,
            "district_index": self.district_index, "district_count": len(o.districts), "districts": o.districts,
            "keywords": o.keywords, "phase": self.phase, "total_steps": self.total_steps,
            "done_steps": self.done_steps, "skipped_steps": self.skipped_steps, "failed_steps": self.failed_steps,
            "api_requests": self.api_requests, "current": self.current, "totals": self.totals,
            "per_district": self.per_district, "log": self.log[-40:], "error": self.error,
            "api_key": self.api_key,
            "started_at": self.started_at, "finished_at": self.finished_at,
            "options": {k: getattr(o, k) for k in ("taluka_pages", "village_pages", "include_villages",
                                                   "include_city_areas", "grid_sweep", "grid_km", "grid_pages",
                                                   "skip_done")},
        }


# ---------------------------------------------------------------------------------------------
# Area lists
# ---------------------------------------------------------------------------------------------
def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def taluka_areas(district: str, pages: int) -> list[Area]:
    areas = []
    for t in search_talukas(district):
        areas.append(Area(district, taluka=t, pages=pages))
        hq = taluka_hq(district, t)
        if hq:
            areas.append(Area(district, taluka=t, city=hq, pages=pages))
    if not areas and not CITY_AREAS.get(district):
        areas.append(Area(district, pages=pages))
    return areas


def city_areas(district: str, pages: int) -> list[Area]:
    return [Area(district, city=a, pages=pages) for a in CITY_AREAS.get(district, [])]


def village_areas(db, district: str, pages: int, already: set[str]) -> list[Area]:
    """Every village/town the database knows for this district (imported or discovered)."""
    d = db.scalar(select(District).where(District.name == district))
    if not d:
        return []
    found: dict[str, Area] = {}

    def add(name: str | None, taluka: str | None):
        key = _norm(name)
        if not key or key in already or key in found:
            return
        found[key] = Area(district, taluka=taluka, city=name.strip(), pages=pages)

    rows = db.execute(select(Location.name, Taluka.name).outerjoin(Taluka, Taluka.id == Location.taluka_id)
                      .where(Location.district_id == d.id, Location.type != "area")
                      .order_by(Taluka.name, Location.name)).all()
    for name, taluka in rows:
        add(name, taluka)
    for col in (Business.city, Business.village):
        for name, taluka in db.execute(select(col, func.min(Business.taluka)).where(
                Business.district_id == d.id, col.isnot(None)).group_by(col)).all():
            add(name, taluka)
    return list(found.values())


def grid_areas(viewport: dict, district: str, km: float, pages: int) -> list[Area]:
    lo, hi = viewport["low"], viewport["high"]
    lat0, lat1 = lo["latitude"], hi["latitude"]
    lng0, lng1 = lo["longitude"], hi["longitude"]
    dlat = km / 111.0
    dlng = km / (111.0 * max(0.2, math.cos(math.radians((lat0 + lat1) / 2))))
    rows = max(1, math.ceil((lat1 - lat0) / dlat))
    cols = max(1, math.ceil((lng1 - lng0) / dlng))
    while rows * cols > MAX_GRID_CELLS:
        dlat, dlng = dlat * 1.25, dlng * 1.25
        rows, cols = max(1, math.ceil((lat1 - lat0) / dlat)), max(1, math.ceil((lng1 - lng0) / dlng))
    out = []
    for r in range(rows):
        for c in range(cols):
            a_lat, a_lng = lat0 + r * dlat, lng0 + c * dlng
            rect = {"low": {"latitude": a_lat, "longitude": a_lng},
                    "high": {"latitude": min(lat1, a_lat + dlat), "longitude": min(lng1, a_lng + dlng)}}
            label = f"Grid {district} {a_lat + dlat / 2:.4f},{a_lng + dlng / 2:.4f} ({km:g} km)"
            out.append(Area(district, pages=pages, rectangle=rect, label=label))
    return out


def plan(db, options: JobOptions) -> dict:
    """Request estimate shown before starting. Villages/grid are counted as known *now*."""
    out = []
    kw = len(options.keywords)
    for dname in options.districts:
        t = taluka_areas(dname, options.taluka_pages)
        c = city_areas(dname, options.taluka_pages) if options.include_city_areas else []
        searched = {_norm(a.city or a.taluka) for a in t + c}
        v = village_areas(db, dname, options.village_pages, searched) if options.include_villages else []
        searches = (len(t) + len(c) + len(v)) * kw
        max_req = sum(a.pages for a in t + c + v) * kw
        out.append({"district": dname, "talukas": len(search_talukas(dname)), "taluka_searches": len(t),
                    "city_areas": len(c), "known_villages": len(v), "searches": searches,
                    "max_requests": max_req})
    return {"keywords": kw, "districts": out,
            "searches": sum(d["searches"] for d in out), "max_requests": sum(d["max_requests"] for d in out),
            "grid_note": "Grid sweep cells are counted when the job reaches that step." if options.grid_sweep else None}


# ---------------------------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------------------------
class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def active(self) -> Job | None:
        with self._lock:
            return next((j for j in self._jobs.values() if j.status in ("queued", "running")), None)

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.started_at or datetime.min.replace(tzinfo=timezone.utc),
                      reverse=True)

    def start(self, options: JobOptions) -> Job:
        with self._lock:
            if any(j.status in ("queued", "running") for j in self._jobs.values()):
                raise RuntimeError("A district collection job is already running. Stop it first.")
            job = Job(id=uuid.uuid4().hex[:10], options=options, started_at=datetime.now(timezone.utc))
            self._jobs[job.id] = job
        self._thread = threading.Thread(target=self._run, args=(job,), daemon=True, name=f"district-job-{job.id}")
        self._thread.start()
        return job

    def cancel(self, job_id: str) -> Job | None:
        job = self._jobs.get(job_id)
        if job and job.status in ("queued", "running"):
            job.cancel.set()
            job.add_log("Stop requested - finishing the current search…")
        return job

    # --- the loop --------------------------------------------------------------------------
    def _run(self, job: Job) -> None:
        job.status = "running"
        ring = places_api.key_ring()
        ring.reset()  # a new job starts again from key #1 (yesterday's used-up keys have a fresh quota)
        job.api_key = ring.status()
        job.add_log(f"{len(ring)} API key(s) configured; starting with key #1")
        o = job.options
        for dname in o.districts:
            job.per_district[dname] = _district_stats()
        try:
            with httpx.Client(timeout=places_api.TIMEOUT) as client:
                for i, dname in enumerate(o.districts):
                    if job.cancel.is_set() or job.status != "running":
                        break
                    job.district, job.district_index = dname, i
                    stats = job.per_district[dname]
                    stats["status"] = "Running"
                    job.add_log(f"▶ District {dname} ({i + 1}/{len(o.districts)})")
                    outcome = self._run_district(job, dname, ring, client)
                    stats["status"] = _district_status(outcome, stats)
                    job.add_log(f"District {dname}: {stats['status']}"
                                + (f" ({stats['failed']} searches failed)" if stats["failed"] else ""))
            if job.status == "paused":
                job.add_log("⏸ Paused: Google quota is used up. Start the same job again after the quota "
                            "resets (with 'skip already searched' on) to continue from here.")
            elif job.cancel.is_set():
                job.status = "cancelled"
                job.add_log("Stopped. Start again with 'skip already searched' on to continue from here.")
            elif job.status == "running":
                unfinished = [d for d, st in job.per_district.items() if st["status"] != "Completed"]
                if unfinished:
                    job.status = "failed"
                    job.error = (f"Not every search succeeded in {', '.join(unfinished[:5])}"
                                 f"{'…' if len(unfinished) > 5 else ''}. Start again with 'skip already searched' "
                                 "on to repeat only the failed searches.")
                    job.add_log(f"✖ {job.error}")
                else:
                    job.status = "completed"
                    job.add_log(f"✔ Done. {job.totals['new']} new businesses, {job.api_requests} API requests.")
        except Exception as exc:  # noqa: BLE001 - keep the error visible in the UI
            job.status, job.error = "failed", f"{exc.__class__.__name__}: {exc}"
            job.add_log(f"✖ {job.error}")
            if job.district and job.per_district.get(job.district, {}).get("status") == "Running":
                job.per_district[job.district]["status"] = "Failed"
                job.per_district[job.district]["last_error"] = job.error[:300]
        finally:
            job.current = ""
            job.finished_at = datetime.now(timezone.utc)

    def _run_district(self, job: Job, district: str, api_key, client: httpx.Client) -> str:
        """Returns 'done' (every step attempted), 'stopped' (cancel / pause / fatal) or 'incomplete'."""
        o = job.options
        stats = job.per_district[district]
        with SessionLocal() as db:
            done = self._done_set(db, district) if o.skip_done else set()

            t_areas = taluka_areas(district, o.taluka_pages)
            c_areas = city_areas(district, o.taluka_pages) if o.include_city_areas else []
            n = (len(t_areas) + len(c_areas)) * len(o.keywords)
            job.total_steps += n
            stats["planned"] += n
            job.phase = f"{district}: talukas"
            job.add_log(f"{len(search_talukas(district))} talukas, {len(c_areas)} city areas × {len(o.keywords)} keywords")
            if not self._loop(job, db, t_areas + c_areas, done, api_key, client, stats):
                return "stopped"

            searched = {_norm(a.city or a.taluka) for a in t_areas + c_areas}
            if o.include_villages and not job.cancel.is_set():
                # Re-read now: phase 1 has just discovered new towns/villages in this district.
                v_areas = village_areas(db, district, o.village_pages, searched)
                n = len(v_areas) * len(o.keywords)
                job.total_steps += n
                stats["planned"] += n
                job.phase = f"{district}: villages & towns"
                job.add_log(f"{len(v_areas)} villages/towns known for {district}")
                if not self._loop(job, db, v_areas, done, api_key, client, stats):
                    return "stopped"

            if o.grid_sweep and not job.cancel.is_set():
                try:
                    vp = places_api.district_viewport(api_key, district, client)
                    job.api_requests += 1
                except places_api.PlacesAPIError as exc:
                    job.api_requests += exc.requests
                    if self._handle_stop_error(job, exc, stats):
                        return "stopped"
                    stats["last_error"] = f"Map boundary: {str(exc)[:250]}"
                    job.add_log(f"✖ Could not get the map boundary for {district}: {str(exc)[:160]}")
                    return "incomplete"
                if not vp:
                    stats["last_error"] = "Google returned no map boundary; grid sweep not done"
                    job.add_log(f"Could not get the map boundary for {district}; grid sweep skipped")
                    return "incomplete"
                g_areas = grid_areas(vp, district, o.grid_km, o.grid_pages)
                n = len(g_areas) * len(o.keywords)
                job.total_steps += n
                stats["planned"] += n
                job.phase = f"{district}: map grid"
                job.add_log(f"Grid sweep: {len(g_areas)} cells of ~{o.grid_km:g} km")
                if not self._loop(job, db, g_areas, done, api_key, client, stats):
                    return "stopped"
        return "done"

    @staticmethod
    def _done_set(db, district: str) -> set[tuple[str, str]]:
        rows = db.execute(select(CollectionRun.search_area, CollectionRun.keyword).where(
            CollectionRun.run_type == "api", CollectionRun.status == "completed",
            CollectionRun.district == district)).all()
        return {(_norm(a), _norm(k)) for a, k in rows}

    def _loop(self, job: Job, db, areas: list[Area], done: set, api_key, client: httpx.Client,
              stats: dict) -> bool:
        """Returns False when the job must stop (cancel, quota pause or no usable API key)."""
        o = job.options
        for area in areas:
            for kw in o.keywords:
                if job.cancel.is_set():
                    return False
                job.current = f"{kw} — {area.search_area}"
                if (_norm(area.search_area), _norm(kw)) in done:
                    job.skipped_steps += 1
                    job.done_steps += 1
                    stats["skipped"] += 1
                    continue
                result = self._search_with_retry(job, db, area, kw, api_key, client, stats)
                self._note_key(job, api_key)
                if result == "stop":
                    return False
                job.done_steps += 1
                if result == "ok":
                    done.add((_norm(area.search_area), _norm(kw)))
                time.sleep(PAUSE_BETWEEN_SEARCHES)
        return True

    @staticmethod
    def _note_key(job: Job, ring) -> None:
        """Log when the job moves from one API key to the next."""
        if not isinstance(ring, places_api.KeyRing):
            return
        now = ring.status()
        before = job.api_key or {}
        for i, kind in now["rejected"].items():
            if i not in (before.get("rejected") or {}):
                why = "daily quota used up" if kind == "quota_exhausted" else f"rejected by Google ({kind})"
                job.add_log(f"🔑 API key #{i}: {why}")
        if now["active"] and now["active"] != before.get("active"):
            job.add_log(f"🔑 Switched to API key #{now['active']} of {now['configured']}")
        job.api_key = now

    def _handle_stop_error(self, job: Job, exc: places_api.PlacesAPIError, stats: dict) -> bool:
        """Quota used up -> pause; no usable key -> fail. Returns True when the job must stop."""
        if exc.quota_exhausted or exc.kind == "rate_limited":
            job.status = "paused"
            what = ("Google Places daily quota used up on every API key" if exc.quota_exhausted
                    else "Google kept rate-limiting requests after several waits")
            job.error = f"{what}. Progress is saved; start again later. Detail: {str(exc)[:300]}"
            stats["status"], stats["last_error"] = "Paused", str(exc)[:300]
            job.add_log(f"⏸ Google quota exhausted: {str(exc)[:200]}")
            return True
        if exc.fatal:
            job.status, job.error = "failed", str(exc)[:500]
            stats["status"], stats["last_error"] = "Failed", str(exc)[:300]
            job.add_log(f"✖ No usable Google API key - check the keys / API enabled / billing: {str(exc)[:200]}")
            return True
        return False

    def _search_with_retry(self, job, db, area: Area, kw: str, api_key, client, stats) -> str:
        """'ok' | 'failed' (this search only; the job goes on) | 'stop' (pause / fatal / cancel)."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                run, reqs = search_and_ingest(db, api_key, district=area.district, keyword=kw, taluka=area.taluka,
                                              city=area.city, category=keyword_category(kw), max_pages=area.pages,
                                              client=client, rectangle=area.rectangle, search_area=area.search_area)
            except places_api.PlacesAPIError as exc:
                job.api_requests += exc.requests
                if exc.run is not None:          # pages saved before the error
                    self._count(job, stats, exc.run, kw, area, searches=0)
                if exc.retryable and attempt < MAX_RETRIES:
                    wait = 15 * (2 ** attempt)
                    job.add_log(f"Google busy/rate-limited ({exc.status_code or exc.kind}); waiting {wait}s then retrying")
                    if job.cancel.wait(wait):
                        return "stop"
                    continue
                # Rate limit that outlasted every retry is treated like a used-up quota: pause.
                if self._handle_stop_error(job, exc, stats):
                    return "stop"
                job.failed_steps += 1
                stats["failed"] += 1
                stats["last_error"] = f"{kw} — {area.search_area}: {str(exc)[:250]}"
                job.add_log(f"✖ {kw} — {area.search_area}: {str(exc)[:160]}")
                return "failed"
            except Exception as exc:  # noqa: BLE001 - one bad search must not kill a 2,000-search job
                db.rollback()
                job.failed_steps += 1
                stats["failed"] += 1
                stats["last_error"] = f"{kw} — {area.search_area}: {exc.__class__.__name__}: {str(exc)[:200]}"
                job.add_log(f"✖ {kw} — {area.search_area}: {exc.__class__.__name__}: {str(exc)[:160]}")
                return "failed"

            job.api_requests += reqs
            self._count(job, stats, run, kw, area)
            return "ok"
        return "failed"

    @staticmethod
    def _count(job: Job, stats: dict, run, kw: str, area: Area, searches: int = 1) -> None:
        t = job.totals
        t["results"] += run.total_results
        t["new"] += run.new_count
        t["duplicates"] += run.duplicate_count
        t["possible_duplicates"] += run.possible_duplicate_count
        t["invalid"] += run.invalid_count
        stats["searches"] += searches
        stats["results"] += run.total_results
        stats["new"] += run.new_count
        if run.new_count:
            job.add_log(f"+{run.new_count} new · {kw} — {area.search_area}")


def _district_stats() -> dict:
    return {"status": "Pending", "searches": 0, "results": 0, "new": 0, "planned": 0, "skipped": 0,
            "failed": 0, "last_error": None}


def _district_status(outcome: str, stats: dict) -> str:
    """Completed only when every planned step ran and none failed."""
    if stats["status"] in ("Paused", "Failed"):
        return stats["status"]
    if outcome == "stopped":
        return "Pending"          # cancelled part-way: not finished, nothing wrong
    if outcome == "done" and stats["failed"] == 0:
        return "Completed"
    return "Failed"


manager = JobManager()


def all_districts() -> list[str]:
    return list(DISTRICTS)
