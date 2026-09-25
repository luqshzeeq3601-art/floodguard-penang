"""SQLAlchemy ORM models for FloodGuard Penang (Phase 8 schema tasks).

Tables mirror established domain contracts — no new identity system:

- sites/sensors/sensor_thresholds: station-master entities (UUIDv5 IDs,
  verbatim source IDs, WGS84 coordinates, threshold provenance).
- observations: canonical identity
  ``(source, fg_sensor_id, measurement_type, observation_time_utc)`` with
  NULL values + quality flags for missing/source-marker rows.
- predictions: per-sensor horizon forecasts with model lineage or explicit
  no-model/baseline states (never a false production model).
- alerts: alert-schema storage (service logic is Phase 11).
- ingest_batches: ingestion/source lineage.

CHECK constraints derive their value sets from the Python enums
(``station_master.SensorType/ThresholdType``) so SQL can never drift from
the canonical rules. PostGIS appears only as ``geometry(POINT,4326)`` on
PostgreSQL (see ``backend.types.Wgs84Point``); GIST indexes use
``postgresql_using="gist"`` and compile to plain indexes elsewhere.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from floodguard.backend.types import SRID_WGS84, Wgs84Point
from floodguard.station_master import SensorType, ThresholdType

SCHEMA_VERSION: Final[str] = "backend_schema/v1"

SENSOR_TYPES: Final[tuple[str, ...]] = (SensorType.RAINFALL.value, SensorType.WATER_LEVEL.value)
THRESHOLD_TYPES: Final[tuple[str, ...]] = (
    ThresholdType.NORMAL.value,
    ThresholdType.WASPADA.value,
    ThresholdType.AMARAN.value,
    ThresholdType.BAHAYA.value,
)
MEASUREMENT_TYPES: Final[tuple[str, ...]] = (
    "RAINFALL_INTERVAL",
    "RAINFALL_1H_TOTAL",
    "WATER_LEVEL",
)
ALERT_STATUSES: Final[tuple[str, ...]] = ("active", "acknowledged", "expired")
ALERT_SEVERITIES: Final[tuple[str, ...]] = ("info", "watch", "warning")


def _check_lists() -> dict[str, str]:
    """Render CHECK value lists from the canonical Python enums (no drift)."""
    return {
        "measurements": ", ".join(f"'{t}'" for t in MEASUREMENT_TYPES),
        "statuses": ", ".join(f"'{t}'" for t in ALERT_STATUSES),
        "severities": ", ".join(f"'{t}'" for t in ALERT_SEVERITIES),
    }


_CHECKS = _check_lists()

# CHECK expressions below are composed from enums (never hand-duplicated),
# so SQL value sets cannot drift from station_master.SensorType/ThresholdType.
_WASPADA_SET = ", ".join(
    f"'{t}'"
    for t in (
        ThresholdType.WASPADA.value,
        ThresholdType.AMARAN.value,
        ThresholdType.BAHAYA.value,
    )
)
_NORM = ThresholdType.NORMAL.value
_RF, _WL = SensorType.RAINFALL.value, SensorType.WATER_LEVEL.value
CK_SENSORS_TYPE_MEASUREMENT_UNIT: Final[str] = (
    f"(sensor_type = '{_RF}' AND measurement_type = 'RAINFALL_INTERVAL' AND unit = 'mm') "
    f"OR (sensor_type = '{_WL}' AND measurement_type = 'WATER_LEVEL' AND unit = 'm')"
)
CK_THRESHOLDS_NORMAL: Final[str] = (
    f"(threshold_type = '{_NORM}' AND fg_label_eligible = FALSE) "
    f"OR (threshold_type IN ({_WASPADA_SET}) AND fg_label_eligible = TRUE)"
)
CK_OBSERVATIONS_MEASUREMENT: Final[str] = f"measurement_type IN ({_CHECKS['measurements']})"
CK_OBSERVATIONS_UNIT: Final[str] = (
    "(measurement_type LIKE 'RAINFALL%' AND unit = 'mm') "
    "OR (measurement_type = 'WATER_LEVEL' AND unit = 'm')"
)
CK_ALERTS_STATUS: Final[str] = f"status IN ({_CHECKS['statuses']})"
CK_ALERTS_SEVERITY: Final[str] = f"severity IN ({_CHECKS['severities']})"
CK_PREDICTED_LABEL: Final[str] = "(predicted_label IS NULL OR predicted_label IN (0, 1))"
CK_COORDINATES_DEGREES: Final[str] = (
    "(latitude IS NULL OR (latitude >= -90 AND latitude <= 90)) "
    "AND (longitude IS NULL OR (longitude >= -180 AND longitude <= 180))"
)


class Base(DeclarativeBase):
    """Declarative base for all FloodGuard tables."""


class Site(Base):
    """Monitoring location (station-master site; names are display-only)."""

    __tablename__ = "sites"

    fg_site_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    jps_internal_id: Mapped[str] = mapped_column(Text, nullable=False)
    fg_source_site_key: Mapped[str] = mapped_column(String(64), nullable=False)
    site_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    district: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latitude: Mapped[Any | None] = mapped_column(Numeric(10, 6), nullable=True)
    longitude: Mapped[Any | None] = mapped_column(Numeric(10, 6), nullable=True)
    coordinate_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    crs: Mapped[str] = mapped_column(String(64), nullable=False, default="EPSG:4326 (inferred)")
    main_basin: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sub_basin: Mapped[str | None] = mapped_column(String(128), nullable=True)
    geom: Mapped[Any | None] = mapped_column(Wgs84Point(), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    quality_flags: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)

    sensors: Mapped[list[Sensor]] = relationship(back_populates="site")

    __table_args__ = (
        Index("ix_sites_district", "district"),
        Index("ix_sites_geom", "geom", postgresql_using="gist"),
        CheckConstraint(CK_COORDINATES_DEGREES, name="ck_sites_coordinates_degrees"),
    )


class Sensor(Base):
    """One measurement type at one site (never keyed by station name)."""

    __tablename__ = "sensors"

    fg_sensor_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fg_site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.fg_site_id", ondelete="RESTRICT"), nullable=False
    )
    sensor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    jps_internal_id: Mapped[str] = mapped_column(Text, nullable=False)
    jps_display_station_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    jps_sensor_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    measurement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    expected_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    quality_flags: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)

    site: Mapped[Site] = relationship(back_populates="sensors")
    thresholds: Mapped[list[SensorThreshold]] = relationship(back_populates="sensor")
    observations: Mapped[list[Observation]] = relationship(back_populates="sensor")
    predictions: Mapped[list[Prediction]] = relationship(back_populates="sensor")
    alerts: Mapped[list[Alert]] = relationship(back_populates="sensor")

    __table_args__ = (
        UniqueConstraint("fg_site_id", "sensor_type", name="uq_sensors_site_type"),
        CheckConstraint(
            CK_SENSORS_TYPE_MEASUREMENT_UNIT,
            name="ck_sensors_type_measurement_unit",
        ),
        Index("ix_sensors_site", "fg_site_id"),
    )


class SensorThreshold(Base):
    """Published water-level reference thresholds with capture provenance.

    Values are current references (``CURRENT_THRESHOLD_REFERENCE_ONLY``):
    joining them to historical observations never implies historical
    validity. ``NORMAL`` rows are stored (published metadata) but never
    label-eligible and never a flood target (enforced below).
    """

    __tablename__ = "sensor_thresholds"

    fg_threshold_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fg_sensor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sensors.fg_sensor_id", ondelete="RESTRICT"), nullable=False
    )
    threshold_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value_m: Mapped[Any | None] = mapped_column(Numeric(10, 3), nullable=True)
    value_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    threshold_source: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance: Mapped[str | None] = mapped_column(Text, nullable=True)
    fg_label_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quality_flags: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)

    sensor: Mapped[Sensor] = relationship(back_populates="thresholds")

    __table_args__ = (
        CheckConstraint(
            CK_THRESHOLDS_NORMAL,
            name="ck_thresholds_normal_never_eligible",
        ),
        Index("ix_thresholds_sensor", "fg_sensor_id"),
    )


class Observation(Base):
    """Canonical observation (source + sensor + type + instant identity).

    Missing/source-marker rows keep ``value`` NULL with quality flags (never
    zero-filled). Conflicting duplicates are rejected by the repository
    before insert; the PK makes replays idempotent.
    """

    __tablename__ = "observations"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    fg_sensor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sensors.fg_sensor_id", ondelete="RESTRICT"), primary_key=True
    )
    measurement_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    observation_time_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    observation_time_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    observation_time_local: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    timezone_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNSPECIFIED_ASSUMED"
    )
    first_retrieved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    value: Mapped[Any | None] = mapped_column(Numeric(12, 4), nullable=True)
    value_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    usable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quality_flags: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    duplicate_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNIQUE")
    provenance: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    datasets: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)

    sensor: Mapped[Sensor] = relationship(back_populates="observations")

    __table_args__ = (
        CheckConstraint(
            CK_OBSERVATIONS_MEASUREMENT,
            name="ck_observations_measurement_type",
        ),
        CheckConstraint(
            CK_OBSERVATIONS_UNIT,
            name="ck_observations_unit",
        ),
        Index("ix_observations_sensor_time", "fg_sensor_id", "observation_time_utc"),
        Index("ix_observations_type_time", "measurement_type", "observation_time_utc"),
    )


class Prediction(Base):
    """Stored forecast/classification output with model lineage.

    ``run_id`` is NOT NULL: persistence/rule baselines use explicit run IDs
    (``persistence``, ``rule``), so "no model" is a recorded state, never a
    NULL ambiguity — and never a false production model claim.
    """

    __tablename__ = "predictions"

    prediction_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fg_sensor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sensors.fg_sensor_id", ondelete="RESTRICT"), nullable=False
    )
    fg_site_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sites.fg_site_id", ondelete="RESTRICT"), nullable=False
    )
    horizon_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    prediction_origin_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    predicted_value: Mapped[Any | None] = mapped_column(Numeric(12, 4), nullable=True)
    predicted_label: Mapped[int | None] = mapped_column(Integer, nullable=True)
    predicted_probability: Mapped[Any | None] = mapped_column(Numeric(8, 6), nullable=True)
    model_family: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_level: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lineage: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint(
            "fg_sensor_id",
            "horizon_minutes",
            "prediction_origin_utc",
            "model_family",
            "run_id",
            name="uq_predictions_identity",
        ),
        CheckConstraint("horizon_minutes IN (30, 60, 120)", name="ck_predictions_horizon"),
        CheckConstraint(CK_PREDICTED_LABEL, name="ck_predictions_label_binary"),
        Index(
            "ix_predictions_sensor_horizon_origin",
            "fg_sensor_id",
            "horizon_minutes",
            "prediction_origin_utc",
        ),
    )

    sensor: Mapped[Sensor] = relationship(back_populates="predictions")
    site: Mapped[Site] = relationship()


class Alert(Base):
    """Alert-schema storage (delivery/service logic is Phase 11)."""

    __tablename__ = "alerts"

    alert_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fg_sensor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sensors.fg_sensor_id", ondelete="RESTRICT"), nullable=True
    )
    fg_site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sites.fg_site_id", ondelete="RESTRICT"), nullable=True
    )
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    horizon_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prediction_origin_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    target_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lineage: Mapped[Any] = mapped_column(JSON, nullable=False, default=dict)

    sensor: Mapped[Sensor | None] = relationship(back_populates="alerts")
    site: Mapped[Site | None] = relationship()

    __table_args__ = (
        CheckConstraint(CK_ALERTS_STATUS, name="ck_alerts_status"),
        CheckConstraint(CK_ALERTS_SEVERITY, name="ck_alerts_severity"),
        Index("ix_alerts_sensor_status", "fg_sensor_id", "status"),
    )


class IngestBatch(Base):
    """Ingestion/source lineage (one row per raw batch attempt)."""

    __tablename__ = "ingest_batches"

    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("status IN ('SUCCEEDED', 'FAILED', 'DUPLICATE')", name="ck_batches_status"),
        Index("ix_batches_source_dataset", "source", "dataset"),
    )


TABLES_IN_ORDER: Final[tuple[str, ...]] = (
    "sites",
    "sensors",
    "sensor_thresholds",
    "observations",
    "predictions",
    "alerts",
    "ingest_batches",
)
SRID_DOCUMENTED: Final[int] = SRID_WGS84
