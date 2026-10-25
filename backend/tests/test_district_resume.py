"""Whole-district job against a mocked Google and a throwaway SQLite database (stands in for MySQL).

Covers: district Completed only when every search succeeded, quota pause, and a resumed job that
neither repeats finished searches nor duplicates saved businesses.
"""
import json
import types

import httpx
import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - register tables
from app.database import Base
from app.models import Business, CollectionRun
from app.services import district_job, places_api
from app.services.district_job import JobManager, JobOptions, taluka_areas

DISTRICT = "Akola"
KW = "xerox"


@pytest.fixture()
def db_session(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=__import__("sqlalchemy.pool", fromlist=["StaticPool"]).StaticPool)

    @event.listens_for(engine, "connect")
    def _fn(conn, _):
        conn.create_function("JSON_ARRAY", 0, lambda: "[]")

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(district_job, "SessionLocal", Session)
    monkeypatch.setattr(district_job, "PAUSE_BETWEEN_SEARCHES", 0)
    return Session


class Google:
    """One place per searched area (id derived from the query). `fail` maps a query substring to a response."""

    def __init__(self, fail=None):
        self.fail = fail or {}
        self.queries: list[str] = []

    def __call__(self, request):
        q = json.loads(request.content)["textQuery"]
        self.queries.append(q)
        for part, resp in self.fail.items():
            if part in q:
                return resp() if callable(resp) else resp
        pid = "pid-" + q.split(" in ")[1].split(",")[0].replace(" ", "-")
        return httpx.Response(200, json={"places": [{
            "id": pid, "displayName": {"text": f"Shop {pid}"}, "formattedAddress": f"{pid}, Akola, Maharashtra",
            "nationalPhoneNumber": f"98{abs(hash(pid)) % 10**8:08d}",
            "addressComponents": [{"longText": "Maharashtra", "types": ["administrative_area_level_1"]}],
        }]})


def run_job(monkeypatch, google: Google, skip_done=True):
    real_client = httpx.Client
    monkeypatch.setattr(district_job, "httpx", types.SimpleNamespace(
        Client=lambda **kw: real_client(transport=httpx.MockTransport(google))))
    monkeypatch.setattr(places_api, "key_ring", lambda: places_api.KeyRing(["test-key-a", "test-key-b"]))
    job = district_job.Job(id="t", options=JobOptions(districts=[DISTRICT], keywords=[KW], taluka_pages=1,
                                                      include_villages=False, include_city_areas=False,
                                                      skip_done=skip_done))
    job.cancel.wait = lambda t: False  # no real back-off waits in tests
    JobManager()._run(job)
    return job


def n_areas():
    return len(taluka_areas(DISTRICT, 1))


def test_all_searches_ok_marks_district_completed(db_session, monkeypatch):
    g = Google()
    job = run_job(monkeypatch, g)
    assert job.status == "completed"
    assert job.per_district[DISTRICT]["status"] == "Completed"
    assert len(g.queries) == n_areas()


def test_district_with_a_failed_search_is_not_completed(db_session, monkeypatch):
    bad = httpx.Response(400, json={"error": {"code": 400, "status": "INVALID_ARGUMENT", "message": "Invalid request"}})
    first_area = taluka_areas(DISTRICT, 1)[0].search_area.split(",")[0]
    g = Google(fail={f"in {first_area},": bad})
    job = run_job(monkeypatch, g)
    st = job.per_district[DISTRICT]
    assert st["status"] == "Failed" and st["failed"] == 1 and st["last_error"]
    assert job.status == "failed"
    # malformed request: tried once with one key, not with every key
    assert sum(first_area in q for q in g.queries) == 1
    with db_session() as db:  # the district still has rows, but that does not make it Completed
        assert db.scalar(select(func.count(Business.id))) == n_areas() - 1


def test_quota_pauses_then_resume_skips_done_work_without_duplicates(db_session, monkeypatch):
    areas = taluka_areas(DISTRICT, 1)
    stop_at = areas[3].search_area.split(",")[0]
    daily = lambda: httpx.Response(429, json={"error": {
        "code": 429, "status": "RESOURCE_EXHAUSTED",
        "message": "Quota exceeded for quota metric 'SearchTextRequest' and limit 'SearchTextRequest per day'."}})
    g1 = Google(fail={f"in {stop_at},": daily})
    job1 = run_job(monkeypatch, g1)
    assert job1.status == "paused"
    assert job1.per_district[DISTRICT]["status"] == "Paused"
    assert "quota" in job1.error.lower()
    assert len(g1.queries) == 5  # 3 good + the quota hit on key a, then on key b -> all used up
    assert job1.api_key["active"] is None
    assert any("API key #1: daily quota used up" in l for l in job1.log)
    assert any("API key #2: daily quota used up" in l for l in job1.log)
    with db_session() as db:
        assert db.scalar(select(func.count(Business.id))) == 3
        assert db.scalar(select(CollectionRun.status).where(CollectionRun.search_area.like(f"{stop_at},%"))) == "paused"

    # next day: quota is back
    g2 = Google()
    job2 = run_job(monkeypatch, g2)
    assert job2.status == "completed" and job2.per_district[DISTRICT]["status"] == "Completed"
    assert job2.skipped_steps == 3
    assert len(g2.queries) == len(areas) - 3
    with db_session() as db:
        assert db.scalar(select(func.count(Business.id))) == len(areas)

    # even re-searching everything (skip off) adds no duplicate businesses
    g3 = Google()
    job3 = run_job(monkeypatch, g3, skip_done=False)
    assert job3.totals["new"] == 0 and len(g3.queries) == len(areas)
    with db_session() as db:
        assert db.scalar(select(func.count(Business.id))) == len(areas)


def test_all_keys_invalid_stops_job_as_failed(db_session, monkeypatch):
    invalid = lambda: httpx.Response(400, json={"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                                          "message": "API key not valid. Please pass a valid API key.",
                                                          "details": [{"reason": "API_KEY_INVALID"}]}})
    g = Google(fail={"xerox": invalid})
    job = run_job(monkeypatch, g)
    assert job.status == "failed" and job.per_district[DISTRICT]["status"] == "Failed"
    assert len(g.queries) == 2  # each of the 2 keys tried once, then stop
    assert "test-key" not in job.error
