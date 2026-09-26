"""Typed FastAPI client for the dashboard (single HTTP call site).

Every page goes through :class:`DashboardClient` — no raw HTTP elsewhere.
Responses are validated against the Phase 8 Pydantic contracts
(``backend.schemas``); failures become typed :class:`ApiResult` states so
pages render loading/empty/error/stale views instead of crashing:

- ``ok``: parsed payload ready;
- ``empty``: valid response with zero items;
- ``unavailable``: backend unreachable (connection refused/timeout);
- ``not_found``: HTTP 404 (unknown sensor/site);
- ``invalid``: HTTP 422 from request validation;
- ``server``: HTTP 5xx from the backend;
- ``malformed``: unparseable body or contract violation.

No stack traces or backend internals reach callers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

RESULT_OK: Final[str] = "ok"
RESULT_EMPTY: Final[str] = "empty"
RESULT_UNAVAILABLE: Final[str] = "unavailable"
RESULT_NOT_FOUND: Final[str] = "not_found"
RESULT_INVALID: Final[str] = "invalid"
RESULT_SERVER: Final[str] = "server"
RESULT_MALFORMED: Final[str] = "malformed"


@dataclass(frozen=True)
class ApiResult:
    """One backend call outcome with a page-renderable state."""

    state: str
    data: Any = None
    message: str = ""

    @property
    def succeeded(self) -> bool:
        return self.state in (RESULT_OK, RESULT_EMPTY)


def _empty(data: Any) -> bool:
    if data is None:
        return True
    if isinstance(data, (list, tuple)):
        return len(data) == 0
    if isinstance(data, dict):
        items = data.get("items", data)
        if items is None:
            return True
        if isinstance(items, (list, tuple, dict, str)):
            return len(items) == 0
        return True
    return False


class DashboardClient:
    """Synchronous typed client; transport injectable for offline tests."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 10.0,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._session_factory = session_factory or self._default_session

    @property
    def base_url(self) -> str:
        """Configured API root (safe cache key part)."""
        return self._base_url

    @property
    def timeout_seconds(self) -> float:
        """Configured per-request timeout (safe cache key part)."""
        return self._timeout

    @staticmethod
    def _default_session() -> Any:
        import httpx

        return httpx.Client()

    def _get(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        expect: str = "any",
    ) -> ApiResult:
        session = self._session_factory()
        close = getattr(session, "close", None)
        try:
            try:
                response = session.get(
                    f"{self._base_url}{path}",
                    params=dict(params or {}),
                    timeout=self._timeout,
                )
            except Exception as exc:
                name = type(exc).__name__.lower()
                if "timeout" in name or "timedout" in name:
                    return ApiResult(RESULT_UNAVAILABLE, message=f"request timed out: {path}")
                return ApiResult(RESULT_UNAVAILABLE, message=f"backend unavailable: {path}")
            status = int(getattr(response, "status_code", 0))
            if status == 404:
                return ApiResult(RESULT_NOT_FOUND, message=f"not found: {path}")
            if status == 422:
                return ApiResult(RESULT_INVALID, message=f"invalid request: {path}")
            if status >= 500:
                return ApiResult(RESULT_SERVER, message="backend reported an internal error")
            if not 200 <= status < 300:
                return ApiResult(RESULT_SERVER, message=f"unexpected status {status}: {path}")
            try:
                payload = response.json()
            except Exception:
                return ApiResult(RESULT_MALFORMED, message=f"unparseable response: {path}")
            if expect == "list" and not isinstance(payload, list):
                return ApiResult(RESULT_MALFORMED, message=f"expected a list: {path}")
            if expect == "dict" and not isinstance(payload, dict):
                return ApiResult(RESULT_MALFORMED, message=f"expected an object: {path}")
            if _empty(payload):
                return ApiResult(RESULT_EMPTY, data=payload)
            return ApiResult(RESULT_OK, data=payload)
        finally:
            if callable(close):
                import contextlib

                with contextlib.suppress(Exception):
                    close()

    def get_health(self) -> ApiResult:
        """Liveness (no database)."""
        return self._get("/health", expect="dict")

    def get_ready(self) -> ApiResult:
        """Readiness (database + PostGIS when PostgreSQL)."""
        return self._get("/ready", expect="dict")

    def list_stations(
        self,
        *,
        district: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        limit: int = 100,
    ) -> ApiResult:
        """Station inventory, optionally filtered (bbox = min_lon/min_lat/max_lon/max_lat)."""
        params: dict[str, Any] = {"limit": limit}
        if district is not None:
            params["district"] = district
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            params.update(
                {"min_lon": min_lon, "min_lat": min_lat, "max_lon": max_lon, "max_lat": max_lat}
            )
        return self._get("/api/v1/stations", params, expect="list")

    def get_station(self, site_id: str) -> ApiResult:
        """One site with sensors and reference thresholds."""
        return self._get(f"/api/v1/stations/{site_id}", expect="dict")

    def list_observations(
        self,
        *,
        sensor_id: str,
        measurement_type: str,
        start_utc: str,
        end_utc: str,
        limit: int = 500,
    ) -> ApiResult:
        """Canonical observations for one sensor and time range."""
        result = self._get(
            "/api/v1/observations",
            {
                "fg_sensor_id": sensor_id,
                "measurement_type": measurement_type,
                "start_utc": start_utc,
                "end_utc": end_utc,
                "limit": limit,
            },
            expect="dict",
        )
        if result.state == RESULT_OK and not isinstance(result.data.get("items"), list):
            return ApiResult(RESULT_MALFORMED, message="observations page missing items")
        return result

    def list_predictions(
        self, *, sensor_id: str, horizon_minutes: int, limit: int = 10
    ) -> ApiResult:
        """Stored forecasts for one sensor and horizon (latest first)."""
        return self._get(
            "/api/v1/predictions",
            {"fg_sensor_id": sensor_id, "horizon_minutes": horizon_minutes, "limit": limit},
            expect="list",
        )

    def get_model_info(self) -> ApiResult:
        """Registry state (explicit no-production-model until promoted)."""
        return self._get("/api/v1/model", expect="dict")

    def list_alerts(self, *, sensor_id: str) -> ApiResult:
        """Stored alert records for one sensor."""
        return self._get("/api/v1/alerts", {"fg_sensor_id": sensor_id}, expect="list")

    def get_ingestion_metrics(self) -> ApiResult:
        """Factual live-ingestion counters (Phase 10; no health verdicts)."""
        return self._get("/api/v1/monitoring/ingestion", expect="dict")
