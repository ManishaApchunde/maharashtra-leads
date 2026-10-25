"""MySQL-friendly SQL expression helpers.

PostgreSQL features this project used before, and their MySQL replacements:
  haversine_m() SQL function      -> haversine_sql() inline expression (no stored function, so no
                                     SUPER / log_bin_trust_function_creators needed)
  JSONB @> '["flag"]'             -> json_has() using JSON_CONTAINS
  count(*) FILTER (WHERE ...)     -> count_if() using COUNT(CASE WHEN ... THEN 1 END)
  ORDER BY x NULLS LAST           -> nulls_last_asc()
  pg_trgm similarity()            -> rapidfuzz in Python (see services/dedup.py)
"""
import json

from sqlalchemy import case, func, literal

EARTH_RADIUS_M = 6371000.0


def haversine_sql(lat1, lng1, lat2, lng2):
    """Great-circle distance in metres as a SQL expression (same formula as utils.geo.haversine_m)."""
    a = (func.power(func.sin(func.radians(lat2 - lat1) / 2), 2)
         + func.cos(func.radians(lat1)) * func.cos(func.radians(lat2))
         * func.power(func.sin(func.radians(lng2 - lng1) / 2), 2))
    # LEAST(1, ..) guards against rounding pushing sqrt(a) just above 1 (ASIN would return NULL).
    return 2 * literal(EARTH_RADIUS_M) * func.asin(func.least(1.0, func.sqrt(a)))


def json_has(column, value: str):
    """True when the JSON array in `column` contains the string `value`."""
    return func.json_contains(column, json.dumps(value)) == 1


def count_if(cond):
    return func.count(case((cond, 1)))


def nulls_last_asc(column):
    """MySQL sorts NULLs first in ascending order and has no NULLS LAST clause."""
    return (column.is_(None).asc(), column.asc())
