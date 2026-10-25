"""Key parsing, error classification and key rotation in the live request path.

All Google responses are mocked with httpx.MockTransport - no real API quota is used.
"""
import httpx
import pytest

from app.config import Settings, parse_api_keys
from app.services import places_api
from app.services.places_api import KeyRing, PlacesAPIError, search_text_counted

K1, K2, K3 = "test-key-one", "test-key-two", "test-key-three"


def _err(code: int, status: str, message: str, reason: str | None = None) -> httpx.Response:
    details = [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": reason}] if reason else []
    return httpx.Response(code, json={"error": {"code": code, "status": status, "message": message,
                                                "details": details}})


INVALID = lambda: _err(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.", "API_KEY_INVALID")
DISABLED = lambda: _err(403, "PERMISSION_DENIED", "Places API (New) has not been used in project 1 before or it is disabled.",
                        "SERVICE_DISABLED")
BILLING = lambda: _err(403, "PERMISSION_DENIED", "This API method requires billing to be enabled.", "BILLING_DISABLED")
DAILY = lambda: _err(429, "RESOURCE_EXHAUSTED",
                     "Quota exceeded for quota metric 'SearchTextRequest' and limit 'SearchTextRequest per day'.",
                     "RATE_LIMIT_EXCEEDED")
PER_MIN = lambda: _err(429, "RESOURCE_EXHAUSTED",
                       "Quota exceeded for quota metric 'SearchTextRequest' and limit 'SearchTextRequest per minute'.",
                       "RATE_LIMIT_EXCEEDED")
MALFORMED = lambda: _err(400, "INVALID_ARGUMENT", "Invalid JSON payload received. Unknown name \"foo\".")
OK = lambda places=None, token=None: httpx.Response(200, json={"places": places or [{"id": "p1"}],
                                                               **({"nextPageToken": token} if token else {})})


class FakeGoogle:
    """Answers per key; records which key and body each request used."""

    def __init__(self, by_key: dict):
        self.by_key = {k: list(v) if isinstance(v, list) else v for k, v in by_key.items()}
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        import json
        key = request.headers["X-Goog-Api-Key"]
        self.calls.append((key, json.loads(request.content)))
        assert request.headers["X-Goog-FieldMask"]
        r = self.by_key[key]
        return r.pop(0)() if isinstance(r, list) else r()

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    @property
    def keys_used(self) -> list[str]:
        return [k for k, _ in self.calls]


def run(ring, fake, pages=1):
    return search_text_counted(ring, "xerox in Akola", pages, fake.client(), sleep=lambda s: None)


# 1. env parsing ------------------------------------------------------------------------------
def test_env_list_is_parsed_into_keys(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEYS", f" {K1}, {K2} ,,{K3},{K1}")
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)
    s = Settings(_env_file=None)
    assert s.places_api_keys == [K1, K2, K3]


def test_old_single_key_still_works_and_empty_is_empty(monkeypatch):
    monkeypatch.delenv("GOOGLE_PLACES_API_KEYS", raising=False)
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", K1)
    assert Settings(_env_file=None).places_api_keys == [K1]
    assert parse_api_keys("", None, " , ") == []
    with pytest.raises(PlacesAPIError) as e:
        search_text_counted("", "x")
    assert e.value.kind == "no_keys" and e.value.fatal


# 2. invalid key -> next key; 3. success returns result ----------------------------------------
def test_invalid_key_rotates_to_next_key_and_returns_result():
    fake = FakeGoogle({K1: INVALID, K2: OK})
    ring = KeyRing([K1, K2, K3])
    places, reqs = run(ring, fake)
    assert places == [{"id": "p1"}]
    assert fake.keys_used == [K1, K2]
    assert reqs == 2
    # the rejected key is not tried again on the next search
    run(ring, fake)
    assert fake.keys_used == [K1, K2, K2]
    assert ring.status() == {"configured": 3, "usable": 2, "active": 2, "rejected": {"1": "invalid_key"}}


def test_api_disabled_and_billing_are_classified_separately_and_rotate():
    fake = FakeGoogle({K1: DISABLED, K2: BILLING, K3: OK})
    ring = KeyRing([K1, K2, K3])
    places, _ = run(ring, fake)
    assert places and fake.keys_used == [K1, K2, K3]
    assert ring.status()["rejected"] == {"1": "api_disabled", "2": "billing_disabled"}


def test_all_keys_rejected_is_fatal_and_bounded():
    fake = FakeGoogle({K1: INVALID, K2: INVALID})
    with pytest.raises(PlacesAPIError) as e:
        run(KeyRing([K1, K2]), fake)
    assert e.value.kind == "all_keys_rejected" and e.value.fatal
    assert len(fake.calls) == 2


# 4. quota / rate limit: no key switching ------------------------------------------------------
def test_daily_quota_on_one_key_moves_to_next_key():
    fake = FakeGoogle({K1: DAILY, K2: OK})
    ring = KeyRing([K1, K2])
    places, reqs = run(ring, fake)
    assert places == [{"id": "p1"}] and reqs == 2
    assert fake.keys_used == [K1, K2]
    assert ring.status() == {"configured": 2, "usable": 1, "active": 2, "rejected": {"1": "quota_exhausted"}}
    run(ring, fake)                      # key 1 is not tried again in this job
    assert fake.keys_used == [K1, K2, K2]


def test_keys_used_one_after_another_then_stop_when_all_used_up():
    fake = FakeGoogle({K1: [OK, DAILY], K2: [OK, DAILY], K3: [DAILY]})
    ring = KeyRing([K1, K2, K3])
    run(ring, fake)                      # key 1 works
    run(ring, fake)                      # key 1 used up -> key 2 works
    with pytest.raises(PlacesAPIError) as e:
        run(ring, fake)                  # key 2 used up -> key 3 used up -> stop
    assert fake.keys_used == [K1, K1, K2, K2, K3]
    assert e.value.kind == "quota_exhausted" and e.value.quota_exhausted and not e.value.fatal
    assert "used up" in str(e.value)
    ring.reset()                         # next day's job starts from key 1 again
    assert ring.status()["active"] == 1


def test_per_minute_rate_limit_is_retryable_not_rotated():
    fake = FakeGoogle({K1: PER_MIN, K2: OK})
    with pytest.raises(PlacesAPIError) as e:
        run(KeyRing([K1, K2]), fake)
    assert e.value.kind == "rate_limited" and e.value.retryable
    assert fake.keys_used == [K1]


# 5. malformed request: not retried with every key -----------------------------------------------
def test_malformed_request_is_not_retried_with_other_keys():
    fake = FakeGoogle({K1: MALFORMED, K2: OK, K3: OK})
    with pytest.raises(PlacesAPIError) as e:
        run(KeyRing([K1, K2, K3]), fake)
    assert e.value.kind == "bad_request" and not e.value.fatal and not e.value.retryable
    assert fake.keys_used == [K1]


def test_server_error_retried_briefly_on_same_key():
    fake = FakeGoogle({K1: [lambda: httpx.Response(503, text="busy"), lambda: httpx.Response(503, text="busy"),
                            lambda: httpx.Response(503, text="busy")], K2: OK})
    with pytest.raises(PlacesAPIError) as e:
        run(KeyRing([K1, K2]), fake)
    assert e.value.kind == "server"
    assert fake.keys_used == [K1] * (1 + places_api.TRANSIENT_RETRIES)


def test_pagination_body_and_partial_pages_kept():
    fake = FakeGoogle({K1: [lambda: OK([{"id": "a"}], "tok1"), DAILY]})
    with pytest.raises(PlacesAPIError) as e:
        run(KeyRing([K1]), fake, pages=3)
    assert e.value.partial_places == [{"id": "a"}]
    assert e.value.requests == 2
    first, second = fake.calls[0][1], fake.calls[1][1]
    assert "pageToken" not in first and second["pageToken"] == "tok1"
    assert first["textQuery"] == "xerox in Akola" and first["pageSize"] == 20 and first["regionCode"] == "IN"


def test_keys_never_appear_in_error_messages():
    echo = lambda: httpx.Response(403, json={"error": {"code": 403, "status": "PERMISSION_DENIED",
                                                       "message": f"key {K1} denied"}})
    fake = FakeGoogle({K1: echo})
    with pytest.raises(PlacesAPIError) as e:
        run(KeyRing([K1]), fake)
    assert K1 not in str(e.value)


def test_key_ring_reads_settings(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("GOOGLE_PLACES_API_KEYS", f"{K1},{K2}")
    get_settings.cache_clear()
    try:
        assert places_api.key_ring().status()["configured"] == 2
    finally:
        get_settings.cache_clear()
