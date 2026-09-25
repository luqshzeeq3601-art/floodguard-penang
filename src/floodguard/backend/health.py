"""Health and readiness checks (Phase 8 health endpoints support).

- liveness: process state only, never touches the database;
- readiness: database connectivity plus, on PostgreSQL, a PostGIS
  extension probe. Failures are reported as data, never raised.
"""

from __future__ import annotations

from typing import Any, Final

from sqlalchemy import text
from sqlalchemy.orm import Session

BACKEND_HEALTH_VERSION: Final[str] = "backend_health/v1"


def liveness() -> dict[str, Any]:
    """Process liveness (no database access)."""
    return {"status": "ok", "service": "floodguard-api", "version": BACKEND_HEALTH_VERSION}


def readiness(session: Session) -> dict[str, Any]:
    """Readiness: connectivity plus optional PostGIS availability."""
    checks: dict[str, Any] = {"database": "unknown", "postgis": "unknown"}
    try:
        session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # readiness must report, never raise
        checks["database"] = f"unavailable: {type(exc).__name__}"
        return {"status": "not_ready", "checks": checks}
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "postgresql":
        try:
            version = session.execute(text("SELECT PostGIS_version()")).scalar()
            checks["postgis"] = f"ok: {version}"
        except Exception as exc:
            checks["postgis"] = f"unavailable: {type(exc).__name__}"
            return {"status": "not_ready", "checks": checks}
    else:
        checks["postgis"] = f"skipped (dialect: {dialect or 'unknown'})"
    return {"status": "ready", "checks": checks}
