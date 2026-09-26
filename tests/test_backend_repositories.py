"""Repository tests on SQLite: idempotency, conflicts, rollback, injection (offline)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.orm import Session, sessionmaker

from floodguard.backend import models
from floodguard.backend.models import Base
from floodguard.backend.repositories import (
    AlertRepository,
    ConflictError,
    IngestBatchRepository,
    NotFoundError,
    ObservationRepository,
    PredictionRepository,
    RepositoryError,
    SensorRepository,
    SiteRepository,
)
from tests.backend_helpers import (
    make_engine,
    make_observation,
    make_sensor,
    make_site,
    make_threshold,
    utc,
)

pytestmark = pytest.mark.usefixtures("no_network")


def _session() -> Session:
    return sessionmaker(bind=make_engine(), class_=Session, expire_on_commit=False)()


def _seed_station(session: Session) -> None:
    session.add(make_site())
    session.add(make_sensor())
    session.commit()


def test_site_sensor_identity_and_fk() -> None:
    session = _session()
    SiteRepository(session).upsert(make_site())
    SensorRepository(session).upsert(make_sensor())
    session.commit()
    assert SiteRepository(session).get("site-001").district == "Timur Laut"
    assert SensorRepository(session).list_for_site("site-001")[0].fg_sensor_id == "sensor-wl-001"
    with pytest.raises(NotFoundError):
        SiteRepository(session).get("nope")


def test_sensor_without_site_fails_loudly() -> None:
    session = _session()
    with pytest.raises(RepositoryError):
        SensorRepository(session).upsert(make_sensor())


def test_master_data_replay_is_idempotent() -> None:
    session = _session()
    assert SiteRepository(session).upsert(make_site()) == "inserted"
    assert SiteRepository(session).upsert(make_site()) == "duplicate_identical"
    assert SensorRepository(session).upsert(make_sensor()) == "inserted"
    assert SensorRepository(session).upsert(make_sensor()) == "duplicate_identical"
    session.commit()
    assert session.query(models.Site).count() == 1


def test_master_data_conflict_raises() -> None:
    session = _session()
    SiteRepository(session).upsert(make_site())
    with pytest.raises(ConflictError):
        SiteRepository(session).upsert(make_site(site_name="Renamed"))


def test_single_flush_covers_all_child_tables() -> None:
    from floodguard.backend.models import Alert, Prediction

    session = _session()
    session.add(make_site())
    session.add(make_sensor())
    session.add(make_threshold())
    session.add(
        Prediction(
            prediction_id="pred-1",
            fg_sensor_id="sensor-wl-001",
            fg_site_id="site-001",
            horizon_minutes=30,
            prediction_origin_utc=utc(0),
            target_time_utc=utc(30),
            predicted_value=1.0,
            predicted_label=None,
            predicted_probability=None,
            model_family="persistence",
            run_id="persistence",
            evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
            created_at=utc(30),
            lineage={},
        )
    )
    session.add(
        Alert(
            alert_id="alert-1",
            fg_sensor_id="sensor-wl-001",
            fg_site_id="site-001",
            alert_type="t",
            severity="watch",
            message="m",
            status="active",
            created_at=utc(0),
            lineage={},
        )
    )
    session.commit()
    assert session.query(models.Prediction).count() == 1
    assert session.query(Alert).count() == 1


def test_alert_cross_site_rejected_and_site_only_allowed() -> None:
    from floodguard.backend.models import Alert

    session = _session()
    session.add(make_site())
    session.add(make_sensor())
    session.commit()

    def _alert(site: str | None) -> Alert:
        return Alert(
            alert_id=f"a-{site}",
            fg_sensor_id="sensor-wl-001",
            fg_site_id=site,
            alert_type="t",
            severity="watch",
            message="m",
            status="active",
            created_at=utc(0),
            lineage={},
        )

    with pytest.raises(RepositoryError, match="does not match"):
        AlertRepository(session).insert(_alert("other-site"))
    session.rollback()
    # Sensor-only alerts (NULL site) remain legitimate.
    AlertRepository(session).insert(_alert(None))
    session.commit()
    assert session.query(Alert).count() == 1


def test_prediction_cross_site_rejected() -> None:
    from floodguard.backend.models import Prediction

    session = _session()
    session.add(make_site())
    session.add(make_sensor())
    session.commit()
    with pytest.raises(RepositoryError, match="does not match"):
        PredictionRepository(session).insert(
            Prediction(
                prediction_id="pred-x",
                fg_sensor_id="sensor-wl-001",
                fg_site_id="other-site",
                horizon_minutes=30,
                prediction_origin_utc=utc(0),
                target_time_utc=utc(30),
                predicted_value=1.0,
                predicted_label=None,
                predicted_probability=None,
                model_family="persistence",
                run_id="persistence",
                evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
                created_at=utc(30),
                lineage={},
            )
        )


def test_single_flush_orders_parents_before_children() -> None:
    """Regression: UOW dependency edges come from ORM relationships.

    Without the Observation.sensor relationship, SQLAlchemy may emit the
    child INSERT first and trip FK enforcement on backends that enforce it
    (PostgreSQL always; SQLite with PRAGMA foreign_keys=ON).
    """
    session = _session()
    session.add(make_site())
    session.add(make_sensor())
    session.add(make_observation())
    session.commit()
    assert session.query(models.Site).count() == 1
    assert session.query(models.Sensor).count() == 1
    assert session.query(models.Observation).count() == 1


def test_observation_replay_is_idempotent() -> None:
    session = _session()
    _seed_station(session)
    repo = ObservationRepository(session)
    assert repo.insert(make_observation()) == "inserted"
    assert repo.insert(make_observation()) == "duplicate_identical"
    session.commit()
    assert session.query(models.Observation).count() == 1
    counts = repo.insert_many([make_observation(minutes=5), make_observation(minutes=5)])
    session.commit()
    assert counts == {"inserted": 1, "duplicate_identical": 1}
    assert session.query(models.Observation).count() == 2


def test_conflicting_duplicate_raises_and_keeps_original() -> None:
    session = _session()
    _seed_station(session)
    repo = ObservationRepository(session)
    repo.insert(make_observation(value=Decimal("1.2")))
    with pytest.raises(ConflictError):
        repo.insert(make_observation(value=Decimal("9.9")))
    session.commit()
    stored = session.query(models.Observation).one().value
    assert stored is not None
    assert float(str(stored)) == 1.2


def test_series_ordering_and_range() -> None:
    session = _session()
    _seed_station(session)
    repo = ObservationRepository(session)
    for minutes in (30, 0, 60, 15):
        repo.insert(make_observation(minutes=minutes, value=Decimal(minutes)))
    session.commit()
    rows = repo.series("sensor-wl-001", "WATER_LEVEL", utc(0), utc(30))
    assert [r.observation_time_utc for r in rows] == sorted(r.observation_time_utc for r in rows)
    assert len(rows) == 3


def test_transaction_rollback_on_conflict() -> None:
    session = _session()
    _seed_station(session)
    repo = ObservationRepository(session)
    repo.insert(make_observation(minutes=0))
    try:
        repo.insert(make_observation(minutes=0, value=Decimal("5.0")))
    except ConflictError:
        session.rollback()
    assert session.query(models.Observation).count() == 0


def test_malicious_strings_stored_literally() -> None:
    session = _session()
    evil = "'; DROP TABLE sites; --"
    SiteRepository(session).upsert(make_site(site_id="evil-1", site_name=evil, district=evil))
    session.commit()
    assert SiteRepository(session).get("evil-1").site_name == evil
    assert session.query(models.Site).count() == 1
    # Table intact: ORM parameter binding never executes stored text.
    assert Base.metadata.tables["sites"] is not None


def test_threshold_provenance_round_trip() -> None:
    session = _session()
    _seed_station(session)
    SensorRepository(session).upsert_threshold(make_threshold())
    session.commit()
    thresholds = SensorRepository(session).thresholds_for_sensor("sensor-wl-001")
    assert thresholds[0].threshold_source == "SYNTHETIC_CAPTURE"
    assert thresholds[0].fg_label_eligible is True


def test_predictions_support_baseline_states() -> None:
    from datetime import UTC

    from floodguard.backend.models import Prediction

    session = _session()
    _seed_station(session)
    repo = PredictionRepository(session)
    repo.insert(
        Prediction(
            prediction_id="pred-1",
            fg_sensor_id="sensor-wl-001",
            fg_site_id="site-001",
            horizon_minutes=30,
            prediction_origin_utc=utc(0),
            target_time_utc=utc(30),
            predicted_value=Decimal("1.2"),
            predicted_label=None,
            predicted_probability=None,
            model_family="persistence",
            run_id="persistence",
            evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
            created_at=utc(30).replace(tzinfo=UTC),
            lineage={"dataset_version": "syn"},
        )
    )
    session.commit()
    latest = repo.latest("sensor-wl-001", 30)
    assert len(latest) == 1
    assert latest[0].run_id == "persistence"


def test_alert_lifecycle() -> None:
    from floodguard.backend.models import Alert

    session = _session()
    _seed_station(session)
    repo = AlertRepository(session)
    repo.insert(
        Alert(
            alert_id="alert-1",
            fg_sensor_id="sensor-wl-001",
            fg_site_id="site-001",
            alert_type="threshold_watch",
            severity="watch",
            horizon_minutes=60,
            prediction_origin_utc=utc(0),
            target_time_utc=utc(60),
            message="Synthetic watch",
            status="active",
            created_at=utc(0),
            lineage={},
        )
    )
    session.commit()
    assert len(repo.active_for_sensor("sensor-wl-001")) == 1
    repo.acknowledge("alert-1")
    session.commit()
    assert repo.active_for_sensor("sensor-wl-001") == []
    with pytest.raises(NotFoundError):
        repo.acknowledge("missing")


def test_ingest_batch_lineage() -> None:
    from floodguard.backend.models import IngestBatch

    session = _session()
    IngestBatchRepository(session).insert(
        IngestBatch(
            batch_id="batch-1",
            source="SYNTHETIC_TEST_ONLY",
            dataset="water_level_history",
            retrieved_at=utc(0),
            payload_sha256="ab" * 32,
            status="SUCCEEDED",
            record_count=10,
        )
    )
    session.commit()
    assert session.query(IngestBatch).one().payload_sha256 == "ab" * 32
