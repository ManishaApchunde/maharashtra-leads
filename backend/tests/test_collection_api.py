"""The /collection endpoints the React app calls keep their shape; keys are never returned."""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services import district_job

SECRET = "test-secret-key-123"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "")
    get_settings.cache_clear()
    yield TestClient(app)  # no "with": skips startup hooks that need MySQL
    get_settings.cache_clear()


def test_status_shape_and_no_key_leak(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEYS", f"{SECRET},{SECRET}-2")
    get_settings.cache_clear()
    r = client.get("/collection/status")
    assert r.status_code == 200
    body = r.json()
    assert body["google_places_configured"] is True
    assert body["google_places_keys"]["configured"] == 2
    assert SECRET not in r.text


def test_status_when_no_keys(client, monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEYS", "")
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "")
    get_settings.cache_clear()
    assert client.get("/collection/status").json()["google_places_configured"] is False
    r = client.post("/collection/district-jobs", json={"district": "Akola"})
    assert r.status_code == 400 and "GOOGLE_PLACES_API_KEYS" in r.json()["detail"]


def test_job_dict_keeps_fields_the_frontend_reads():
    job = district_job.Job(id="x", options=district_job.JobOptions(districts=["Akola"], keywords=["xerox"]))
    d = job.to_dict()
    for key in ("id", "status", "district", "district_index", "district_count", "districts", "keywords", "phase",
                "total_steps", "done_steps", "skipped_steps", "failed_steps", "api_requests", "current", "totals",
                "per_district", "log", "error", "started_at", "finished_at", "options"):
        assert key in d
    assert set(d["totals"]) == {"results", "new", "duplicates", "possible_duplicates", "invalid"}


def test_list_jobs_shape(client):
    body = client.get("/collection/district-jobs").json()
    assert set(body) == {"active", "items"}
