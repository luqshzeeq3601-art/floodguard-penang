"""FastAPI tests via TestClient (offline, SQLite-backed, no server)."""

from __future__ import annotations

from datetime import UTC

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from tests.backend_helpers import (
    make_observation,
    make_sensor,
    make_site,
    make_threshold,
    utc,
)

from floodguard.backend.api import create_app
from floodguard.backend.models import Prediction
from floodguard.backend.repositories import ObservationRepository, PredictionRepository

# `loopback_only` (not `no_network`): Starlette's TestClient runs the ASGI app
# in-process but needs loopback socketpair on Windows. External connections
# and DNS stay forbidden, so a real-network regression is still caught.
pytestmark = [
    pytest.mark.filterwarnings("ignore::DeprecationWarning"),
    pytest.mark.usefixtures("loopback_only"),
]


def _seeded_client(with_observations: bool = False) -> TestClient:
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from floodguard.backend.models import Base

    # Shared-cache in-memory database: TestClient serves requests on worker
    # threads, and plain :memory: SQLite is per-connection.
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    seed = factory()
    seed.add(make_site())
    seed.add(make_sensor())
    seed.add(make_threshold())
    if with_observations:
        ObservationRepository(seed).insert(make_observation(minutes=0))
        ObservationRepository(seed).insert(make_observation(minutes=5, value=None))
    seed.commit()
    seed.close()
    return TestClient(create_app(factory))


def test_health_and_ready() -> None:
    client = _seeded_client()
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["checks"]["database"] == "ok"


def test_stations_list_detail_and_bbox() -> None:
    client = _seeded_client()
    listing = client.get("/api/v1/stations")
    assert listing.status_code == 200
    assert listing.json()[0]["fg_site_id"] == "site-001"
    assert listing.json()[0]["sensors"][0]["unit"] == "m"
    detail = client.get("/api/v1/stations/site-001")
    assert detail.status_code == 200
    assert any(
        t["temporal_validity"] == "CURRENT_THRESHOLD_REFERENCE_ONLY"
        for t in detail.json()["thresholds"]
    )
    assert any(
        t["threshold_type"] == "WASPADA" and t["fg_label_eligible"]
        for t in detail.json()["thresholds"]
    )
    assert client.get("/api/v1/stations/nope").status_code == 404
    bbox = client.get("/api/v1/stations?min_lon=100&min_lat=5&max_lon=101&max_lat=6")
    assert bbox.status_code == 200
    assert len(bbox.json()) == 1
    assert client.get("/api/v1/stations?min_lon=100").status_code == 422


def test_observations_range_and_validation() -> None:
    client = _seeded_client(with_observations=True)
    good = client.get(
        "/api/v1/observations?fg_sensor_id=sensor-wl-001&measurement_type=WATER_LEVEL"
        "&start_utc=2030-01-01T00:00:00%2B00:00&end_utc=2030-01-01T01:00:00%2B00:00"
    )
    assert good.status_code == 200
    assert good.json()["count"] == 2
    assert good.json()["items"][1]["value"] is None
    bad_range = client.get(
        "/api/v1/observations?fg_sensor_id=sensor-wl-001&measurement_type=WATER_LEVEL"
        "&start_utc=2030-01-01T01:00:00%2B00:00&end_utc=2030-01-01T00:00:00%2B00:00"
    )
    assert bad_range.status_code == 422
    assert "traceback" not in bad_range.text.lower()
    missing = client.get(
        "/api/v1/observations?fg_sensor_id=ghost&measurement_type=WATER_LEVEL"
        "&start_utc=2030-01-01T00:00:00%2B00:00&end_utc=2030-01-01T01:00:00%2B00:00"
    )
    assert missing.status_code == 404


def test_predictions_and_model_state() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from floodguard.backend.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    seed = factory()
    seed.add(make_site())
    seed.add(make_sensor())
    PredictionRepository(seed).insert(
        Prediction(
            prediction_id="pred-1",
            fg_sensor_id="sensor-wl-001",
            fg_site_id="site-001",
            horizon_minutes=30,
            prediction_origin_utc=utc(0),
            target_time_utc=utc(30),
            predicted_value=1.2,
            predicted_label=None,
            predicted_probability=None,
            model_family="persistence",
            run_id="persistence",
            evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
            created_at=utc(30).replace(tzinfo=UTC),
            lineage={"dataset_version": "syn"},
        )
    )
    seed.commit()
    seed.close()
    client = TestClient(create_app(factory))
    predictions = client.get("/api/v1/predictions?fg_sensor_id=sensor-wl-001&horizon_minutes=30")
    assert predictions.status_code == 200
    assert predictions.json()[0]["model_family"] == "persistence"
    model = client.get("/api/v1/model")
    assert model.status_code == 200
    assert model.json()["status"] == "NO_ELIGIBLE_MODEL"
    assert model.json()["production_model"] is None
    alerts = client.get("/api/v1/alerts?fg_sensor_id=sensor-wl-001")
    assert alerts.status_code == 200
    assert alerts.json() == []


def test_observations_reject_naive_datetimes() -> None:
    client = _seeded_client(with_observations=True)
    naive = client.get(
        "/api/v1/observations?fg_sensor_id=sensor-wl-001&measurement_type=WATER_LEVEL"
        "&start_utc=2030-01-01T00:00:00&end_utc=2030-01-01T01:00:00"
    )
    assert naive.status_code == 422
    assert "timezone" in naive.json()["detail"]


def test_observations_emit_tz_aware_times() -> None:
    client = _seeded_client(with_observations=True)
    good = client.get(
        "/api/v1/observations?fg_sensor_id=sensor-wl-001&measurement_type=WATER_LEVEL"
        "&start_utc=2030-01-01T00:00:00%2B00:00&end_utc=2030-01-01T01:00:00%2B00:00"
    )
    assert good.status_code == 200
    stamp = good.json()["items"][0]["observation_time_utc"]
    assert stamp.endswith("+00:00") or stamp.endswith("Z")


def _static_client(seed_extra: object = None) -> TestClient:
    """Seeded client on a shared-cache SQLite engine (TestClient threads)."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from floodguard.backend.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    seed = factory()
    seed.add(make_site())
    seed.add(make_sensor())
    seed.add(make_threshold())
    if seed_extra is not None:
        from collections.abc import Iterable

        extras = seed_extra if isinstance(seed_extra, Iterable) else [seed_extra]
        for extra in extras:
            seed.add(extra)
    seed.commit()
    seed.close()
    return TestClient(create_app(factory))


def test_production_family_label_never_flips_model_status() -> None:
    from floodguard.backend.models import Prediction as PredictionModel

    client = _static_client(
        PredictionModel(
            prediction_id="pred-prod",
            fg_sensor_id="sensor-wl-001",
            fg_site_id="site-001",
            horizon_minutes=30,
            prediction_origin_utc=utc(0),
            target_time_utc=utc(30),
            predicted_value=2.0,
            predicted_label=1,
            predicted_probability=0.99,
            model_family="production",
            run_id="forged",
            evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
            created_at=utc(30),
            lineage={},
        )
    )
    model = client.get("/api/v1/model")
    assert model.status_code == 200
    assert model.json()["status"] == "NO_ELIGIBLE_MODEL"
    assert model.json()["production_model"] is None


def test_error_payloads_hide_internals() -> None:
    client = _seeded_client()
    response = client.get("/api/v1/stations/%27%20OR%201%3D1%20--")
    assert response.status_code in (404, 422)
    assert "traceback" not in response.text.lower()
    assert "psycopg" not in response.text.lower()
