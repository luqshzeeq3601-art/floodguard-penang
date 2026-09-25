"""Phase 8 backend: PostgreSQL/PostGIS storage and FastAPI service.

Production-quality infrastructure reusing established domain semantics:

- Identity: ``fg_site_id`` / ``fg_sensor_id`` (UUIDv5, station master),
  canonical observation identity
  ``(source, fg_sensor_id, measurement_type, observation_time)``.
- Time: source text vs normalized UTC vs retrieved time stay distinct;
  ``Asia/Kuala_Lumpur`` remains an assumption (``TIMEZONE_ASSUMED``).
- Thresholds: Waspada/Amaran/Bahaya are current references only
  (``CURRENT_THRESHOLD_REFERENCE_ONLY``); NORMAL is never label-eligible
  and never a flood target.
- Coordinates: WGS84/EPSG:4326 (inferred, per station master); PostGIS
  ``geometry(POINT,4326)`` on PostgreSQL, WKT text on other dialects
  (unit-test portability). No metric distances in degrees.
- Missing data: NULL values with quality flags (never zero-filled);
  conflicting duplicates fail loudly, never silently overwritten.
- Predictions reference model lineage or explicit no-model/baseline states;
  Phase 7 promotion gates are never bypassed (``NO_ELIGIBLE_MODEL`` stands).
"""

from __future__ import annotations

from typing import Final

BACKEND_SCHEMA_VERSION: Final[str] = "backend/v1"
SRID_WGS84: Final[int] = 4326
CRS_LABEL: Final[str] = "EPSG:4326 (inferred)"
