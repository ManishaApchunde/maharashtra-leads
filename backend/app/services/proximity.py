"""Distance from each business to the nearest government office.

MySQL version: offices inside a small bounding box are fetched with the lat/lng index and
the exact haversine distance is computed in Python. The bulk refresh loads all offices once
into a grid of ~2 km cells and walks businesses in id batches, so it needs no LATERAL join,
no stored SQL function and no spatial extension.
"""
from collections import defaultdict
from math import floor

from sqlalchemy import bindparam, select, update
from sqlalchemy.orm import Session

from app.models import Business, GovernmentOffice
from app.utils.geo import haversine_m

MAX_RADIUS_M = 2000
# ~0.02 degrees latitude ≈ 2.2 km; longitude degrees are slightly shorter in Maharashtra
BOX_LAT = 0.019
BOX_LNG = 0.021
BATCH = 2000


def nearest_office(db: Session, lat: float | None, lng: float | None):
    """Returns (office_id, office_type, distance_m) within 2 km, or None."""
    if lat is None or lng is None:
        return None
    rows = db.execute(
        select(GovernmentOffice.id, GovernmentOffice.office_type, GovernmentOffice.latitude, GovernmentOffice.longitude)
        .where(GovernmentOffice.latitude.between(lat - BOX_LAT, lat + BOX_LAT),
               GovernmentOffice.longitude.between(lng - BOX_LNG, lng + BOX_LNG))
    ).all()
    best = None
    for oid, otype, olat, olng in rows:
        d = haversine_m(lat, lng, olat, olng)
        if best is None or d < best[2]:
            best = (oid, otype, d)
    if best and best[2] <= MAX_RADIUS_M:
        return best
    return None


def _cell(lat: float, lng: float) -> tuple[int, int]:
    return floor(lat / BOX_LAT), floor(lng / BOX_LNG)


def recompute_all(db: Session) -> int:
    """Refresh nearest office for every business (in batches). Returns rows whose value changed."""
    grid: dict[tuple[int, int], list[tuple[int, float, float]]] = defaultdict(list)
    for oid, olat, olng in db.execute(select(GovernmentOffice.id, GovernmentOffice.latitude, GovernmentOffice.longitude)
                                      .where(GovernmentOffice.latitude.isnot(None),
                                             GovernmentOffice.longitude.isnot(None))):
        grid[_cell(olat, olng)].append((oid, olat, olng))

    stmt = (update(Business.__table__)
            .where(Business.__table__.c.id == bindparam("b_id"))
            .values(nearest_gov_office_id=bindparam("office_id"), nearest_gov_office_m=bindparam("dist")))

    last_id, changed = 0, 0
    while True:
        rows = db.execute(
            select(Business.id, Business.latitude, Business.longitude,
                   Business.nearest_gov_office_id, Business.nearest_gov_office_m)
            .where(Business.id > last_id).order_by(Business.id).limit(BATCH)
        ).all()
        if not rows:
            break
        updates = []
        for bid, lat, lng, cur_id, cur_d in rows:
            office_id = dist = None
            if lat is not None and lng is not None:
                cy, cx = _cell(lat, lng)
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        for oid, olat, olng in grid.get((cy + dy, cx + dx), ()):
                            d = haversine_m(lat, lng, olat, olng)
                            if d <= MAX_RADIUS_M and (dist is None or d < dist):
                                office_id, dist = oid, d
            if office_id != cur_id or (dist is None) != (cur_d is None) or \
                    (dist is not None and abs(dist - cur_d) > 0.01):
                updates.append({"b_id": bid, "office_id": office_id, "dist": dist})
        if updates:
            db.execute(stmt, updates)
            changed += len(updates)
        db.commit()
        last_id = rows[-1].id
    return changed
