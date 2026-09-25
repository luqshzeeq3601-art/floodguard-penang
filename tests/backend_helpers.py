"""Shared synthetic builders for backend tests (no JPS data, offline only)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from floodguard.backend.models import (
    Base,
    Observation,
    Sensor,
    SensorThreshold,
    Site,
)

UTC_ZERO = datetime(2030, 1, 1, tzinfo=UTC)


def utc(minutes: int = 0) -> datetime:
    return UTC_ZERO + timedelta(minutes=minutes)


def make_engine() -> Engine:
    engine: Engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection: Any, record: Any) -> None:
        # SQLite disables FK enforcement by default; PostgreSQL enforces
        # natively. Enable it so unit tests share production semantics.
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


def make_session(engine: Engine) -> Session:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)()


def make_site(site_id: str = "site-001", **overrides: Any) -> Site:
    fields: dict[str, Any] = {
        "fg_site_id": site_id,
        "source": "SYNTHETIC_TEST_ONLY",
        "jps_internal_id": "SYN001",
        "fg_source_site_key": "SYN001",
        "site_name": "Synthetic Site",
        "state": "Pulau Pinang",
        "district": "Timur Laut",
        "latitude": Decimal("5.410000"),
        "longitude": Decimal("100.320000"),
        "coordinate_source": "synthetic",
        "crs": "EPSG:4326 (inferred)",
        "main_basin": "Sungai Pinang",
        "sub_basin": None,
        "geom": "POINT(100.32 5.41)",
        "first_seen_at": utc(0),
        "last_verified_at": utc(60),
        "quality_flags": [],
        "schema_version": "station_master/v1",
    }
    fields.update(overrides)
    return Site(**fields)


def make_sensor(
    sensor_id: str = "sensor-wl-001", site_id: str = "site-001", **overrides: Any
) -> Sensor:
    fields: dict[str, Any] = {
        "fg_sensor_id": sensor_id,
        "fg_site_id": site_id,
        "sensor_type": "WATER_LEVEL",
        "jps_internal_id": "SYN001",
        "jps_display_station_id": "SYN-DISP-1",
        "jps_sensor_name": "Synthetic WL",
        "measurement_type": "WATER_LEVEL",
        "unit": "m",
        "expected_interval_minutes": None,
        "source_url": None,
        "first_seen_at": utc(0),
        "last_verified_at": utc(60),
        "quality_flags": [],
        "schema_version": "station_master/v1",
    }
    fields.update(overrides)
    return Sensor(**fields)


def make_threshold(
    threshold_id: str = "thr-001", sensor_id: str = "sensor-wl-001", **overrides: Any
) -> SensorThreshold:
    fields: dict[str, Any] = {
        "fg_threshold_id": threshold_id,
        "fg_sensor_id": sensor_id,
        "threshold_type": "WASPADA",
        "value_m": Decimal("1.500"),
        "value_raw": "1.5",
        "threshold_source": "SYNTHETIC_CAPTURE",
        "captured_at": utc(0),
        "source_verified_at": utc(0),
        "valid_from": None,
        "provenance": "synthetic",
        "fg_label_eligible": True,
        "quality_flags": [],
    }
    fields.update(overrides)
    return SensorThreshold(**fields)


def make_observation(
    source: str = "SYNTHETIC_TEST_ONLY",
    sensor_id: str = "sensor-wl-001",
    measurement_type: str = "WATER_LEVEL",
    minutes: int = 0,
    value: Any = Decimal("1.2000"),
    **overrides: Any,
) -> Observation:
    fields: dict[str, Any] = {
        "source": source,
        "fg_sensor_id": sensor_id,
        "measurement_type": measurement_type,
        "observation_time_utc": utc(minutes),
        "observation_time_raw": "01/01/2030 08:00",
        "observation_time_local": utc(minutes) + timedelta(hours=8),
        "timezone_status": "UNSPECIFIED_ASSUMED",
        "first_retrieved_at": utc(minutes) + timedelta(minutes=5),
        "value": value,
        "value_raw": None if value is None else str(value),
        "unit": "m",
        "usable": value is not None,
        "quality_flags": [] if value is not None else ["VALUE_MISSING_SENTINEL"],
        "duplicate_status": "UNIQUE",
        "provenance": [],
        "datasets": ["synthetic"],
        "schema_version": "observations/v1",
    }
    fields.update(overrides)
    return Observation(**fields)
