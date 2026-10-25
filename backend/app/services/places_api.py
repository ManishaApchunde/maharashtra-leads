"""Google Places API (New) - Text Search. Official, key-authenticated API only.

No page scraping, no CAPTCHA/rate-limit workarounds. Pages are fetched slowly
and capped (max 3 pages x 20 results per run).

IMPORTANT: Google Maps Platform terms restrict how long most Places content may
be stored (place IDs may be kept; most other fields may not be cached long-term).
Read the current terms before keeping API results in a permanent marketing list.
Each row is stored with source="Google Places API" and its place ID, so you can
find, refresh or remove these rows later.
"""
import logging
import threading
import time
from collections.abc import Sequence

import httpx

from app.config import get_settings, parse_api_keys

log = logging.getLogger(__name__)

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.formattedAddress", "places.location",
    "places.nationalPhoneNumber", "places.internationalPhoneNumber", "places.websiteUri",
    "places.rating", "places.userRatingCount", "places.googleMapsUri", "places.addressComponents",
    "nextPageToken",
])
SOURCE_NAME = "Google Places API"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
TRANSIENT_RETRIES = 2          # extra attempts for 5xx / network errors inside one request
TRANSIENT_BACKOFF = 2.0        # seconds, doubled each attempt

# Error kinds. KEY_KINDS and a used-up DAILY quota move on to the next key: each key is used until it
# is rejected or its daily quota is gone, then the next one, and so on. When every key is used up the
# job pauses. A per-minute rate limit does not switch keys - it is waited out on the same key.
KEY_KINDS = {"invalid_key", "key_restricted", "api_disabled", "billing_disabled", "permission_denied"}
_INVALID = {"API_KEY_INVALID", "API_KEY_EXPIRED"}
_RESTRICTED = {"API_KEY_SERVICE_BLOCKED", "API_KEY_HTTP_REFERRER_BLOCKED", "API_KEY_IP_ADDRESS_BLOCKED",
               "API_KEY_ANDROID_APP_BLOCKED", "API_KEY_IOS_APP_BLOCKED"}


class PlacesAPIError(Exception):
    """kind: invalid_key | key_restricted | api_disabled | billing_disabled | permission_denied |
    all_keys_rejected | no_keys | quota_exhausted | rate_limited | bad_request | server | network | http"""

    def __init__(self, message: str, status_code: int | None = None, kind: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.kind = kind or _kind_from_status(status_code)
        self.requests = 0                    # API requests made before the failure
        self.partial_places: list[dict] = []  # pages that succeeded before a later page failed
        self.run = None                      # CollectionRun, set by collector.search_and_ingest

    @property
    def retryable(self) -> bool:
        """Short-term problems worth waiting for: per-minute rate limit, Google 5xx, network."""
        return self.kind in ("rate_limited", "server", "network")

    @property
    def quota_exhausted(self) -> bool:
        """Daily quota used up (on every key, once raised from a search): pause and resume later."""
        return self.kind == "quota_exhausted"

    @property
    def fatal(self) -> bool:
        """No usable key left: every later request would fail the same way."""
        return self.kind in KEY_KINDS or self.kind in ("all_keys_rejected", "no_keys")


def _kind_from_status(code: int | None) -> str:
    if code is None:
        return "network"
    if code in (401, 403):
        return "permission_denied"
    if code == 429:
        return "rate_limited"
    if code >= 500:
        return "server"
    if code == 400:
        return "bad_request"
    return "http"


def classify_error(status_code: int, payload: dict | None, text: str = "") -> tuple[str, str]:
    """(kind, reason) from a Google error response: {"error": {"code", "message", "status", "details"}}."""
    err = (payload or {}).get("error") or {}
    message = str(err.get("message") or text or "")
    reasons, meta = set(), ""
    for d in err.get("details") or []:
        if isinstance(d, dict):
            if d.get("reason"):
                reasons.add(str(d["reason"]))
            meta += " " + " ".join(str(v) for v in (d.get("metadata") or {}).values())
            for v in d.get("violations") or []:
                meta += " " + " ".join(str(x) for x in v.values()) if isinstance(v, dict) else ""
    low = f"{message} {meta}".lower()
    reason = next(iter(sorted(reasons)), "") or str(err.get("status") or "")

    if reasons & _INVALID or ("api key" in low and ("not valid" in low or "expired" in low or "invalid" in low)):
        return "invalid_key", reason or "API_KEY_INVALID"
    if reasons & _RESTRICTED or (status_code in (401, 403) and "are blocked" in low):
        return "key_restricted", reason
    # Quota before the text checks below: a 429 message can mention billing without billing being off.
    if status_code == 429 or err.get("status") == "RESOURCE_EXHAUSTED":
        daily = "per day" in low or "perday" in low.replace(" ", "") or "daily" in low
        return ("quota_exhausted" if daily else "rate_limited"), reason or "RESOURCE_EXHAUSTED"
    if "SERVICE_DISABLED" in reasons or "has not been used in project" in low or "it is disabled" in low:
        return "api_disabled", reason or "SERVICE_DISABLED"
    if "BILLING_DISABLED" in reasons or (status_code in (401, 403) and "billing" in low):
        return "billing_disabled", reason or "BILLING_DISABLED"
    if status_code in (401, 403):
        return "permission_denied", reason or "PERMISSION_DENIED"
    return _kind_from_status(status_code), reason


class KeyRing:
    """The configured keys, tried in order. A key that Google rejects is skipped until reset()."""

    def __init__(self, keys: Sequence[str]):
        self._keys = list(keys)
        self._rejected: dict[int, str] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._keys)

    def active(self) -> tuple[int, str] | None:
        with self._lock:
            for i, k in enumerate(self._keys):
                if i not in self._rejected:
                    return i, k
            return None

    def reject(self, index: int, kind: str) -> None:
        with self._lock:
            self._rejected[index] = kind

    def reset(self) -> None:
        with self._lock:
            self._rejected.clear()

    def redact(self, text: str) -> str:
        for k in self._keys:
            if k:
                text = text.replace(k, "***")
        return text

    def status(self) -> dict:
        with self._lock:
            active = next((i for i in range(len(self._keys)) if i not in self._rejected), None)
            return {"configured": len(self._keys), "usable": len(self._keys) - len(self._rejected),
                    "active": None if active is None else active + 1,
                    "rejected": {str(i + 1): kind for i, kind in sorted(self._rejected.items())}}


_ring: KeyRing | None = None
_ring_keys: tuple[str, ...] = ()
_ring_lock = threading.Lock()


def key_ring() -> KeyRing:
    """Shared KeyRing built from backend/.env (rebuilt if the configured keys change)."""
    global _ring, _ring_keys
    keys = tuple(get_settings().places_api_keys)
    with _ring_lock:
        if _ring is None or keys != _ring_keys:
            _ring, _ring_keys = KeyRing(keys), keys
        return _ring


def _as_ring(api_key) -> KeyRing:
    if isinstance(api_key, KeyRing):
        ring = api_key
    elif isinstance(api_key, str) or api_key is None:
        ring = KeyRing(parse_api_keys(api_key))
    else:
        ring = KeyRing(parse_api_keys(*api_key))
    if not len(ring):
        raise PlacesAPIError("GOOGLE_PLACES_API_KEYS is not set in backend/.env", 401, "no_keys")
    return ring


def _post(client: httpx.Client, body: dict, field_mask: str, ring: KeyRing, sleep=time.sleep) -> tuple[dict, int]:
    """One Places request. Returns (json, requests_made).

    * key rejected (invalid / restricted / API disabled / billing off / permission) -> next key
    * Google 5xx or network error -> up to TRANSIENT_RETRIES short retries on the same key
    * quota, rate limit, malformed request -> raised immediately, no key switching
    """
    requests = 0
    transient = 0
    while True:
        picked = ring.active()
        if picked is None:
            st = ring.status()
            detail = ", ".join(f"key #{i}: {k}" for i, k in st["rejected"].items())
            if "quota_exhausted" in st["rejected"].values():
                err = PlacesAPIError(f"All {st['configured']} Google Places API key(s) are used up for today "
                                     f"({detail}). Start the job again after the daily quota resets.",
                                     429, "quota_exhausted")
            else:
                err = PlacesAPIError(f"All {st['configured']} Google Places API key(s) were rejected ({detail}). "
                                     "Check the keys, that Places API (New) is enabled and billing is on.",
                                     403, "all_keys_rejected")
            err.requests = requests
            raise err
        idx, key = picked
        try:
            r = client.post(ENDPOINT, json=body, headers={
                "X-Goog-Api-Key": key, "X-Goog-FieldMask": field_mask, "Content-Type": "application/json"})
        except httpx.HTTPError as exc:
            requests += 1
            err = PlacesAPIError(f"Network error talking to Google: {exc.__class__.__name__}: "
                                 f"{ring.redact(str(exc))[:200]}", None, "network")
        else:
            requests += 1
            if r.status_code == 200:
                return r.json(), requests
            try:
                payload = r.json()
            except ValueError:
                payload = None
            kind, reason = classify_error(r.status_code, payload, r.text[:500])
            msg = ((payload or {}).get("error") or {}).get("message") or r.text[:300]
            err = PlacesAPIError(ring.redact(f"Places API returned {r.status_code} {reason}: {msg}")[:500],
                                 r.status_code, kind)

        if err.kind in KEY_KINDS or err.kind == "quota_exhausted":
            ring.reject(idx, err.kind)
            log.warning("Google Places key #%d stopped (%s); %s", idx + 1, err.kind,
                        "switching to the next key" if ring.active() else "no keys left")
            continue
        if err.kind in ("server", "network") and transient < TRANSIENT_RETRIES:
            sleep(TRANSIENT_BACKOFF * (2 ** transient))
            transient += 1
            continue
        err.requests = requests
        raise err


def _component(place: dict, kind: str) -> str | None:
    for c in place.get("addressComponents", []) or []:
        if kind in c.get("types", []):
            return c.get("longText")
    return None


def place_state(place: dict) -> str | None:
    return _component(place, "administrative_area_level_1")


def place_to_row(place: dict, district: str, taluka: str | None, keyword: str, category: str | None) -> dict:
    from app.utils.text import canonical_district

    loc = place.get("location") or {}
    address = place.get("formattedAddress") or ""
    flags = []
    # Prefer the district Google reports; fall back to the searched district and flag it.
    g_district = None
    for kind in ("administrative_area_level_3", "administrative_area_level_2"):
        d, ok = canonical_district(_component(place, kind))
        if ok:
            g_district = d
            break
    if not g_district:
        flags.append("district_from_search_area")
    # Only keep the searched taluka if the address actually mentions it.
    taluka_val = taluka if taluka and taluka.lower() in address.lower() else None
    return {
        "extra_flags": flags,
        "shop_name": (place.get("displayName") or {}).get("text"),
        "phone": place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber"),
        "website": place.get("websiteUri"),
        "address": place.get("formattedAddress"),
        "area": _component(place, "sublocality_level_1") or _component(place, "sublocality"),
        "city": _component(place, "locality"),
        "taluka": taluka_val,
        "district": g_district or district,
        "pincode": _component(place, "postal_code"),
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "google_maps_url": place.get("googleMapsUri"),
        "source": SOURCE_NAME,
        "source_url": place.get("googleMapsUri"),
        "source_place_id": place.get("id"),
        "rating": place.get("rating"),
        "review_count": place.get("userRatingCount"),
        "category": category,
        "discovered_keyword": keyword,
    }


def search_text_counted(api_key, query: str, max_pages: int = 1, client: httpx.Client | None = None,
                        rectangle: dict | None = None, sleep=time.sleep) -> tuple[list[dict], int]:
    """Text Search, following nextPageToken up to max_pages (max 3, 20 results each).

    api_key: a KeyRing (normal use: key_ring()), a list of keys, or a comma-separated string.
    rectangle = {"low": {"latitude":..,"longitude":..}, "high": {...}} restricts results to that box
    (used by the grid sweep). Returns (places, number_of_api_requests).
    If a later page fails, the raised PlacesAPIError carries the earlier pages in .partial_places.
    """
    ring = _as_ring(api_key)
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    places: list[dict] = []
    token = None
    requests = 0
    try:
        for _page in range(max(1, min(int(max_pages), 3))):
            body = {"textQuery": query, "regionCode": "IN", "languageCode": "en", "pageSize": 20}
            if rectangle:
                body["locationRestriction"] = {"rectangle": rectangle}
            if token:
                body["pageToken"] = token
            try:
                data, n = _post(client, body, FIELD_MASK, ring, sleep)
            except PlacesAPIError as exc:
                exc.requests += requests
                exc.partial_places = places
                raise
            requests += n
            places.extend(data.get("places", []))
            token = data.get("nextPageToken")
            if not token:
                break
            sleep(2)  # be polite between pages
    finally:
        if own:
            client.close()
    return places, requests


def search_text(api_key, query: str, max_pages: int = 1, client: httpx.Client | None = None) -> list[dict]:
    return search_text_counted(api_key, query, max_pages, client)[0]


def district_viewport(api_key, district: str, client: httpx.Client | None = None) -> dict | None:
    """Bounding box of a district, from Google's own place record for it (one cheap request)."""
    ring = _as_ring(api_key)
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT)
    try:
        data, _ = _post(client, {"textQuery": f"{district} district, Maharashtra, India",
                                 "regionCode": "IN", "pageSize": 1},
                        "places.viewport,places.displayName,places.types", ring)
        for p in data.get("places", []):
            if p.get("viewport"):
                return p["viewport"]
        return None
    finally:
        if own:
            client.close()
