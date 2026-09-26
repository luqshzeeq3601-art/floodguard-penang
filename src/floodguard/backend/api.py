"""FastAPI application (Phase 8 API tasks).

Endpoints:

```text
/health                     liveness (no database)
/ready                      readiness (database + PostGIS when PostgreSQL)
/api/v1/stations            site/sensor inventory, optional bbox + district
/api/v1/stations/{site_id}  one site with sensors and reference thresholds
/api/v1/observations        canonical observations (sensor + time range)
/api/v1/predictions         stored forecasts (sensor + horizon, latest first)
/api/v1/model               registry state: explicit no-production-model
/api/v1/alerts              stored alerts for a sensor
/api/v1/monitoring/ingestion factual live-ingestion counters (Phase 10)
```

All handlers use the repository layer (parameter-bound ORM only), return
explicit Pydantic models, and convert failures to structured errors without
stack traces or secrets. Prediction output never claims a production model:
with ``NO_ELIGIBLE_MODEL`` the endpoints serve stored baseline records and
``/api/v1/model`` says so explicitly.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from floodguard.backend import health
from floodguard.backend.config import DatabaseConfig
from floodguard.backend.models import Prediction, SensorThreshold, Site
from floodguard.backend.repositories import (
    AlertRepository,
    NotFoundError,
    ObservationRepository,
    PredictionRepository,
    RepositoryError,
    SensorRepository,
    SiteRepository,
)
from floodguard.backend.schemas import (
    AlertResponse,
    HealthResponse,
    IngestionMetricsResponse,
    ModelInfoResponse,
    ObservationPage,
    ObservationResponse,
    PredictionResponse,
    ReadyResponse,
    SensorSummary,
    SiteResponse,
    ThresholdResponse,
)

API_VERSION: str = "v1"


def _require_aware(name: str, moment: datetime) -> datetime:
    """Reject naive datetimes: PG TIMESTAMPTZ semantics differ by input."""
    if moment.tzinfo is None:
        raise HTTPException(status_code=422, detail=f"{name} must carry a timezone offset")
    return moment


def _as_utc(moment: datetime) -> datetime:
    """Normalize stored instants to tz-aware UTC (SQLite drops tzinfo on read)."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def create_session_factory(config: DatabaseConfig) -> sessionmaker[Session]:
    """Session factory bound to the configured database URL."""
    engine = create_engine(config.url, echo=config.echo, future=True)
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def create_app(
    session_factory: Callable[[], Iterator[Session]] | sessionmaker[Session],
    ingestion_metrics_provider: Callable[[], dict[str, Any]] | None = None,
) -> FastAPI:
    """Application factory (session factory injectable for tests).

    ``ingestion_metrics_provider`` supplies factual Phase 10 live-ingestion
    counters for ``/api/v1/monitoring/ingestion``; when None the endpoint
    reports zero counters with an explicit notice (no health verdict).
    """
    app = FastAPI(title="FloodGuard Penang API", version=API_VERSION)

    def get_session() -> Iterator[Session]:
        if isinstance(session_factory, sessionmaker):
            with session_factory() as session:
                yield session
        else:
            yield from session_factory()

    @app.exception_handler(RepositoryError)
    async def _repository_error(_: Any, exc: RepositoryError) -> JSONResponse:
        # Generic external detail: driver/constraint text stays server-side.
        _ = exc
        return JSONResponse(
            status_code=502, content={"error": "storage_error", "detail": "storage unavailable"}
        )

    @app.get("/health", response_model=HealthResponse)
    def get_health() -> HealthResponse:
        return HealthResponse(**health.liveness())

    @app.get("/ready", response_model=ReadyResponse)
    def get_ready(session: Session = Depends(get_session)) -> ReadyResponse:
        return ReadyResponse(**health.readiness(session))

    @app.get("/api/v1/stations", response_model=list[SiteResponse])
    def list_stations(
        district: str | None = Query(default=None, max_length=64),
        min_lon: float | None = Query(default=None, ge=-180, le=180),
        min_lat: float | None = Query(default=None, ge=-90, le=90),
        max_lon: float | None = Query(default=None, ge=-180, le=180),
        max_lat: float | None = Query(default=None, ge=-90, le=90),
        limit: int = Query(default=100, ge=1, le=1000),
        session: Session = Depends(get_session),
    ) -> list[dict[str, Any]]:
        repo = SiteRepository(session)
        bbox_given = (
            min_lon is not None or min_lat is not None or max_lon is not None or max_lat is not None
        )
        if bbox_given:
            if min_lon is None or min_lat is None or max_lon is None or max_lat is None:
                raise HTTPException(status_code=422, detail="bbox needs all four bounds")
            sites = repo.bbox(min_lon, min_lat, max_lon, max_lat)
        else:
            sites = repo.list_sites(district=district, limit=limit)
        return [_site_payload(site, session) for site in sites[:limit]]

    @app.get("/api/v1/stations/{site_id}", response_model=SiteResponse)
    def get_station(site_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
        try:
            site = SiteRepository(session).get(site_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        payload = _site_payload(site, session)
        payload["thresholds"] = _thresholds_payload(site, session)
        return payload

    @app.get("/api/v1/observations", response_model=ObservationPage)
    def list_observations(
        fg_sensor_id: str = Query(min_length=1, max_length=36),
        measurement_type: str = Query(min_length=1, max_length=32),
        start_utc: datetime = Query(),
        end_utc: datetime = Query(),
        limit: int = Query(default=200, ge=1, le=5000),
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        start = _require_aware("start_utc", start_utc)
        end = _require_aware("end_utc", end_utc)
        if end < start:
            raise HTTPException(status_code=422, detail="end_utc precedes start_utc")
        try:
            SensorRepository(session).get(fg_sensor_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        rows = ObservationRepository(session).series(
            fg_sensor_id, measurement_type, start, end, limit=limit
        )
        items = [
            ObservationResponse(
                source=row.source,
                fg_sensor_id=row.fg_sensor_id,
                measurement_type=row.measurement_type,
                observation_time_utc=_as_utc(row.observation_time_utc),
                value=float(row.value) if row.value is not None else None,
                value_raw=row.value_raw,
                unit=row.unit,
                usable=bool(row.usable),
                quality_flags=list(row.quality_flags or []),
            )
            for row in rows
        ]
        return {"items": items, "count": len(items)}

    @app.get("/api/v1/predictions", response_model=list[PredictionResponse])
    def list_predictions(
        fg_sensor_id: str = Query(min_length=1, max_length=36),
        horizon_minutes: int = Query(ge=1, le=720),
        limit: int = Query(default=10, ge=1, le=100),
        session: Session = Depends(get_session),
    ) -> list[dict[str, Any]]:
        rows = PredictionRepository(session).latest(fg_sensor_id, horizon_minutes, limit=limit)
        return [
            {
                "prediction_id": row.prediction_id,
                "fg_sensor_id": row.fg_sensor_id,
                "horizon_minutes": row.horizon_minutes,
                "prediction_origin_utc": _as_utc(row.prediction_origin_utc),
                "target_time_utc": _as_utc(row.target_time_utc),
                "predicted_value": float(row.predicted_value)
                if row.predicted_value is not None
                else None,
                "predicted_label": row.predicted_label,
                "predicted_probability": float(row.predicted_probability)
                if row.predicted_probability is not None
                else None,
                "model_family": row.model_family,
                "run_id": row.run_id,
                "evidence_level": row.evidence_level,
                "lineage": dict(row.lineage or {}),
            }
            for row in rows
        ]

    @app.get("/api/v1/model", response_model=ModelInfoResponse)
    def get_model_info(session: Session = Depends(get_session)) -> dict[str, Any]:
        # Honest by construction: promotion verdicts live in the Phase 7
        # registry (PROMOTE + REAL evidence), which this service does not
        # invent from prediction rows. A stored `model_family="production"`
        # label is NOT a promotion claim, so it can never flip this status.
        families = sorted(
            {family for family in session.scalars(select(Prediction.model_family).distinct()).all()}
        )
        return {
            "production_model": None,
            "status": "NO_ELIGIBLE_MODEL",
            "detail": (
                "No production model is registered. Stored predictions, if any, "
                "are baselines or unevaluated candidates (see evidence_level). "
                "Phase 7 promotion gates apply; model families seen in storage: "
                + (", ".join(families) if families else "none")
                + "."
            ),
            "registry_models": families,
        }

    @app.get("/api/v1/alerts", response_model=list[AlertResponse])
    def list_alerts(
        fg_sensor_id: str = Query(min_length=1, max_length=36),
        session: Session = Depends(get_session),
    ) -> list[dict[str, Any]]:
        rows = AlertRepository(session).active_for_sensor(fg_sensor_id)
        return [
            {
                "alert_id": row.alert_id,
                "fg_sensor_id": row.fg_sensor_id,
                "alert_type": row.alert_type,
                "severity": row.severity,
                "status": row.status,
                "message": row.message,
                "created_at": _as_utc(row.created_at),
            }
            for row in rows
        ]

    @app.get("/api/v1/monitoring/ingestion", response_model=IngestionMetricsResponse)
    def get_ingestion_metrics() -> dict[str, Any]:
        # Factual counters only; never a freshness/health verdict.
        if ingestion_metrics_provider is None:
            return IngestionMetricsResponse().model_dump()
        try:
            supplied = dict(ingestion_metrics_provider())
        except Exception:
            return IngestionMetricsResponse().model_dump()
        supplied.setdefault("schema_version", "live_metrics/v1")
        supplied.setdefault(
            "notice",
            "Factual engineering counters only; no freshness/health verdict is implied.",
        )
        return IngestionMetricsResponse(**supplied).model_dump()

    return app


def _site_payload(site: Site, session: Session) -> dict[str, Any]:
    sensors = SensorRepository(session).list_for_site(site.fg_site_id)
    return {
        "fg_site_id": site.fg_site_id,
        "site_name": site.site_name,
        "district": site.district,
        "latitude": float(site.latitude) if site.latitude is not None else None,
        "longitude": float(site.longitude) if site.longitude is not None else None,
        "crs": site.crs,
        "main_basin": site.main_basin,
        "sensors": [
            SensorSummary(
                fg_sensor_id=sensor.fg_sensor_id,
                sensor_type=sensor.sensor_type,
                measurement_type=sensor.measurement_type,
                unit=sensor.unit,
            ).model_dump()
            for sensor in sensors
        ],
    }


def _thresholds_payload(site: Site, session: Session) -> list[dict[str, Any]]:
    sensors = SensorRepository(session).list_for_site(site.fg_site_id)
    payload: list[dict[str, Any]] = []
    for sensor in sensors:
        for threshold in session.scalars(
            select(SensorThreshold).where(SensorThreshold.fg_sensor_id == sensor.fg_sensor_id)
        ).all():
            payload.append(
                ThresholdResponse(
                    threshold_type=threshold.threshold_type,
                    value_m=float(threshold.value_m) if threshold.value_m is not None else None,
                    threshold_source=threshold.threshold_source,
                    captured_at=_as_utc(threshold.captured_at)
                    if threshold.captured_at is not None
                    else None,
                    fg_label_eligible=bool(threshold.fg_label_eligible),
                ).model_dump()
            )
    return payload
