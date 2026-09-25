"""Repository / data-access layer (Phase 8).

All database access goes through these repositories — no SQL scattered in
API or ingestion code. Every query is SQLAlchemy ORM (parameter-bound; no
string-concatenated user input reaches the database).

Measurement-name translation (review L8): the station master speaks
``rainfall``/``water_level`` (``station_master.SENSOR_MEASUREMENT``) while
canonical storage speaks ``RAINFALL_INTERVAL``/``RAINFALL_1H_TOTAL``/
``WATER_LEVEL`` (validated by ``preprocessing.units``). Callers must pass
canonical names — this layer validates them against CHECK constraints and
never guesses the mapping.

Write semantics mirror the Phase 2 data-quality contract:

- inserts are idempotent: replaying identical canonical rows is a no-op;
- conflicting duplicates (same identity, materially different content) raise
  :class:`ConflictError` instead of silently overwriting;
- missing/source-marker rows (NULL value + flags) are legitimate content.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from floodguard.backend.models import (
    Alert,
    IngestBatch,
    Observation,
    Prediction,
    Sensor,
    SensorThreshold,
    Site,
)

OBSERVATION_VALUE_FIELDS: Final[tuple[str, ...]] = (
    "value",
    "value_raw",
    "unit",
    "usable",
    "quality_flags",
    "duplicate_status",
    "provenance",
    "datasets",
    # Provenance metadata participates in identity: same PK with different
    # raw text, local time, tz status or schema version is a conflict, never
    # a silent merge. first_retrieved_at is excluded by design (earliest
    # capture wins; re-ingestion must not manufacture conflicts).
    "observation_time_raw",
    "observation_time_local",
    "timezone_status",
    "schema_version",
)


class RepositoryError(Exception):
    """Base class for repository failures (wraps driver errors)."""


class ConflictError(RepositoryError):
    """Same canonical identity, materially different content."""


class NotFoundError(RepositoryError):
    """Requested row does not exist."""


def _insert_flushed(session: Session, obj: object, *, what: str) -> None:
    """Add and flush one object; a failed INSERT becomes RepositoryError.

    Callers check first (idempotency) and pre-validate parents (deterministic
    FK errors), so a flush failure here means a concurrent primary-key race
    or a programming error. Either way the session transaction needs a
    caller-side rollback before reuse — no silent recovery read is attempted
    (reads after a failed flush raise ``PendingRollbackError``). Savepoints
    are deliberately not used: ``begin_nested()`` flushes pending state on
    entry and objects added inside it can escape outer rollback.
    """
    session.add(obj)
    try:
        session.flush()
    except IntegrityError as exc:
        raise RepositoryError(
            f"{what} insert failed; roll back and retry the unit of work: {exc}"
        ) from exc


def _norm(value: Any) -> Any:
    if isinstance(value, datetime):
        # Canonical storage is UTC instants; SQLite drops tzinfo on read, so
        # compare instants (naive read as UTC) rather than representations.
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return ("datetime", moment.timestamp())
    if isinstance(value, list):
        return [_norm(item) for item in value]
    if isinstance(value, dict):
        return {key: _norm(item) for key, item in sorted(value.items())}
    if isinstance(value, Decimal):
        return ("decimal", str(value))
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)):
        return ("decimal", str(Decimal(str(value))))
    return value


def _observation_signature(row: Observation) -> tuple[Any, ...]:
    return tuple(_norm(getattr(row, field)) for field in OBSERVATION_VALUE_FIELDS)


SITE_SIGNATURE_FIELDS: Final[tuple[str, ...]] = (
    "source",
    "jps_internal_id",
    "fg_source_site_key",
    "site_name",
    "state",
    "district",
    "latitude",
    "longitude",
    "coordinate_source",
    "crs",
    "main_basin",
    "sub_basin",
    "quality_flags",
    "schema_version",
)

SENSOR_SIGNATURE_FIELDS: Final[tuple[str, ...]] = (
    "fg_site_id",
    "sensor_type",
    "jps_internal_id",
    "jps_display_station_id",
    "jps_sensor_name",
    "measurement_type",
    "unit",
    "expected_interval_minutes",
    "source_url",
    "quality_flags",
    "schema_version",
)

THRESHOLD_SIGNATURE_FIELDS: Final[tuple[str, ...]] = (
    "fg_sensor_id",
    "threshold_type",
    "value_m",
    "value_raw",
    "threshold_source",
    "captured_at",
    "source_verified_at",
    "valid_from",
    "provenance",
    "fg_label_eligible",
    "quality_flags",
)


def _entity_signature(row: object, fields: tuple[str, ...]) -> tuple[Any, ...]:
    return tuple(_norm(getattr(row, field)) for field in fields)


def _site_signature(row: Site) -> tuple[Any, ...]:
    return _entity_signature(row, SITE_SIGNATURE_FIELDS)


def _sensor_signature(row: Sensor) -> tuple[Any, ...]:
    return _entity_signature(row, SENSOR_SIGNATURE_FIELDS)


def _threshold_signature(row: SensorThreshold) -> tuple[Any, ...]:
    return _entity_signature(row, THRESHOLD_SIGNATURE_FIELDS)


class SiteRepository:
    """CRUD for monitoring sites (display names are never keys)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, fg_site_id: str) -> Site:
        site = self._session.get(Site, fg_site_id)
        if site is None:
            raise NotFoundError(f"unknown site: {fg_site_id}")
        return site

    def list_sites(self, *, district: str | None = None, limit: int = 100) -> list[Site]:
        query = select(Site).order_by(Site.fg_site_id).limit(max(limit, 1))
        if district is not None:
            query = (
                select(Site)
                .where(Site.district == district)
                .order_by(Site.fg_site_id)
                .limit(max(limit, 1))
            )
        return list(self._session.scalars(query).all())

    def upsert(self, site: Site) -> str:
        """True upsert: insert, no-op replay if identical, ConflictError if different."""
        existing = self._session.get(Site, site.fg_site_id)
        if existing is not None:
            if _site_signature(existing) == _site_signature(site):
                return "duplicate_identical"
            raise ConflictError(f"conflicting site for {site.fg_site_id}")
        _insert_flushed(self._session, site, what=f"site {site.fg_site_id}")
        return "inserted"

    def bbox(self, min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> list[Site]:
        """Bounding-box lookup on stored coordinates (degrees, no metric math)."""
        query = (
            select(Site)
            .where(Site.longitude.is_not(None))
            .where(Site.latitude.is_not(None))
            .where(Site.longitude >= min_lon)
            .where(Site.longitude <= max_lon)
            .where(Site.latitude >= min_lat)
            .where(Site.latitude <= max_lat)
            .order_by(Site.fg_site_id)
        )
        return list(self._session.scalars(query).all())


class SensorRepository:
    """CRUD for sensors and their reference thresholds."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, fg_sensor_id: str) -> Sensor:
        sensor = self._session.get(Sensor, fg_sensor_id)
        if sensor is None:
            raise NotFoundError(f"unknown sensor: {fg_sensor_id}")
        return sensor

    def list_for_site(self, fg_site_id: str) -> list[Sensor]:
        query = select(Sensor).where(Sensor.fg_site_id == fg_site_id).order_by(Sensor.fg_sensor_id)
        return list(self._session.scalars(query).all())

    def upsert(self, sensor: Sensor) -> str:
        """True upsert mirroring :meth:`SiteRepository.upsert`."""
        existing = self._session.get(Sensor, sensor.fg_sensor_id)
        if existing is not None:
            if _sensor_signature(existing) == _sensor_signature(sensor):
                return "duplicate_identical"
            raise ConflictError(f"conflicting sensor for {sensor.fg_sensor_id}")
        if self._session.get(Site, sensor.fg_site_id) is None:
            raise RepositoryError(f"sensor references unknown site {sensor.fg_site_id}")
        _insert_flushed(self._session, sensor, what=f"sensor {sensor.fg_sensor_id}")
        return "inserted"

    def upsert_threshold(self, threshold: SensorThreshold) -> str:
        """True upsert mirroring :meth:`SiteRepository.upsert`."""
        existing = self._session.get(SensorThreshold, threshold.fg_threshold_id)
        if existing is not None:
            if _threshold_signature(existing) == _threshold_signature(threshold):
                return "duplicate_identical"
            raise ConflictError(f"conflicting threshold for {threshold.fg_threshold_id}")
        if self._session.get(Sensor, threshold.fg_sensor_id) is None:
            raise RepositoryError(f"threshold references unknown sensor {threshold.fg_sensor_id}")
        _insert_flushed(self._session, threshold, what=f"threshold {threshold.fg_threshold_id}")
        return "inserted"

    def thresholds_for_sensor(self, fg_sensor_id: str) -> list[SensorThreshold]:
        query = (
            select(SensorThreshold)
            .where(SensorThreshold.fg_sensor_id == fg_sensor_id)
            .order_by(SensorThreshold.threshold_type)
        )
        return list(self._session.scalars(query).all())


class ObservationRepository:
    """Idempotent canonical observation writes with conflict detection."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(
        self, source: str, fg_sensor_id: str, measurement_type: str, instant: datetime
    ) -> Observation:
        row = self._session.get(Observation, (source, fg_sensor_id, measurement_type, instant))
        if row is None:
            raise NotFoundError("unknown observation")
        return row

    def insert(self, row: Observation) -> str:
        """Insert or no-op replay; conflicting content raises ConflictError.

        Returns ``"inserted"`` or ``"duplicate_identical"``.
        """
        existing = self._session.get(
            Observation,
            (row.source, row.fg_sensor_id, row.measurement_type, row.observation_time_utc),
        )
        if existing is not None:
            if _observation_signature(existing) == _observation_signature(row):
                return "duplicate_identical"
            identity = (
                row.source,
                row.fg_sensor_id,
                row.measurement_type,
                row.observation_time_utc,
            )
            raise ConflictError(f"conflicting observation for {identity}")
        if self._session.get(Sensor, row.fg_sensor_id) is None:
            raise RepositoryError(f"observation references unknown sensor {row.fg_sensor_id}")
        identity = (
            row.source,
            row.fg_sensor_id,
            row.measurement_type,
            row.observation_time_utc,
        )
        _insert_flushed(self._session, row, what=f"observation {identity}")
        return "inserted"

    def insert_many(self, rows: Sequence[Observation]) -> dict[str, int]:
        """Replay-safe bulk insert with per-row outcome counts.

        A conflicting row aborts the batch with ConflictError (the caller
        rolls back and retries); callers needing partial progress commit
        per row instead.
        """
        counts = {"inserted": 0, "duplicate_identical": 0}
        for row in rows:
            counts[self.insert(row)] += 1
        return counts

    def series(
        self,
        fg_sensor_id: str,
        measurement_type: str,
        start_utc: datetime,
        end_utc: datetime,
        *,
        limit: int = 1000,
    ) -> list[Observation]:
        query = (
            select(Observation)
            .where(Observation.fg_sensor_id == fg_sensor_id)
            .where(Observation.measurement_type == measurement_type)
            .where(Observation.observation_time_utc >= start_utc)
            .where(Observation.observation_time_utc <= end_utc)
            .order_by(Observation.observation_time_utc)
            .limit(max(limit, 1))
        )
        return list(self._session.scalars(query).all())


class PredictionRepository:
    """Stored forecasts with lineage (supports explicit no-model states)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def insert(self, prediction: Prediction) -> Prediction:
        sensor = self._session.get(Sensor, prediction.fg_sensor_id)
        if sensor is None:
            raise RepositoryError(f"prediction references unknown sensor {prediction.fg_sensor_id}")
        if sensor.fg_site_id != prediction.fg_site_id:
            raise RepositoryError(
                "prediction site does not match its sensor's site "
                f"({prediction.fg_site_id} != {sensor.fg_site_id})"
            )
        try:
            self._session.add(prediction)
            self._session.flush()
        except IntegrityError as exc:
            raise RepositoryError(f"prediction insert failed: {exc}") from exc
        return prediction

    def latest(
        self, fg_sensor_id: str, horizon_minutes: int, *, limit: int = 10
    ) -> list[Prediction]:
        query = (
            select(Prediction)
            .where(Prediction.fg_sensor_id == fg_sensor_id)
            .where(Prediction.horizon_minutes == horizon_minutes)
            .order_by(Prediction.prediction_origin_utc.desc())
            .limit(max(limit, 1))
        )
        return list(self._session.scalars(query).all())


class AlertRepository:
    """Alert-schema storage (delivery is Phase 11)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def insert(self, alert: Alert) -> Alert:
        # Site-only or sensor-only alerts are legitimate (nullable FKs); when
        # both are set they must agree, mirroring PredictionRepository.
        if alert.fg_sensor_id is not None:
            sensor = self._session.get(Sensor, alert.fg_sensor_id)
            if sensor is None:
                raise RepositoryError(f"alert references unknown sensor {alert.fg_sensor_id}")
            if alert.fg_site_id is not None and sensor.fg_site_id != alert.fg_site_id:
                raise RepositoryError(
                    "alert site does not match its sensor's site "
                    f"({alert.fg_site_id} != {sensor.fg_site_id})"
                )
        try:
            self._session.add(alert)
            self._session.flush()
        except IntegrityError as exc:
            raise RepositoryError(f"alert insert failed: {exc}") from exc
        return alert

    def active_for_sensor(self, fg_sensor_id: str) -> list[Alert]:
        query = (
            select(Alert)
            .where(Alert.fg_sensor_id == fg_sensor_id)
            .where(Alert.status == "active")
            .order_by(Alert.created_at.desc())
        )
        return list(self._session.scalars(query).all())

    def acknowledge(self, alert_id: str) -> Alert:
        alert = self._session.get(Alert, alert_id)
        if alert is None:
            raise NotFoundError(f"unknown alert: {alert_id}")
        alert.status = "acknowledged"
        self._session.flush()
        return alert


class IngestBatchRepository:
    """Ingestion/source lineage rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def insert(self, batch: IngestBatch) -> IngestBatch:
        try:
            self._session.add(batch)
            self._session.flush()
        except IntegrityError as exc:
            raise RepositoryError(f"batch insert failed: {exc}") from exc
        return batch
