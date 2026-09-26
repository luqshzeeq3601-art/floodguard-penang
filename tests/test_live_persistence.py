"""Prediction persistence tests (Phase 10, Task 7; offline SQLite, synthetic)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from floodguard.backend.repositories import PredictionRepository
from floodguard.live.persistence import build_prediction, persist_predictions
from tests.backend_helpers import make_engine, make_sensor, make_session, make_site

pytestmark = pytest.mark.usefixtures("no_network")


def _seeded_session() -> Session:
    engine = make_engine()
    session = make_session(engine)
    session.add(make_site())
    session.add(make_sensor())
    session.commit()
    assert isinstance(session, Session)
    return session


def test_persist_baseline_predictions_with_lineage() -> None:
    session = _seeded_session()
    try:
        from datetime import timedelta

        origin = datetime(2030, 1, 1, tzinfo=UTC)
        rows = [
            build_prediction(
                fg_sensor_id="sensor-wl-001",
                fg_site_id="site-001",
                horizon_minutes=h,
                origin_utc=origin,
                target_utc=origin + timedelta(minutes=h),
                model_family="persistence",
                run_id="persistence",
                evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
                predicted_value=1.2,
                lineage={"dataset_version": "syn"},
            )
            for h in (30, 60, 120)
        ]
        counts = persist_predictions(session, rows)
        assert counts == {"inserted": 3, "requested": 3}
        stored = PredictionRepository(session).latest("sensor-wl-001", 30)
        assert len(stored) == 1
        assert stored[0].run_id == "persistence"
        assert stored[0].lineage["dataset_version"] == "syn"
    finally:
        session.close()


def test_no_model_live_path_persists_zero_rows() -> None:
    from floodguard.live.inference import run_live_inference

    result = run_live_inference(
        run_id="r", sensor_id="sensor-wl-001", origin_utc=datetime(2030, 1, 1, tzinfo=UTC)
    )
    assert result.predictions == ()
    session = _seeded_session()
    try:
        assert persist_predictions(session, []) == {"inserted": 0, "requested": 0}
    finally:
        session.close()


def test_prediction_guards_reject_bad_rows() -> None:
    origin = datetime(2030, 1, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="horizon"):
        build_prediction(
            fg_sensor_id="s",
            fg_site_id="site",
            horizon_minutes=45,
            origin_utc=origin,
            target_utc=origin,
            model_family="m",
            run_id="r",
            evidence_level="syn",
        )
    with pytest.raises(ValueError, match="run_id"):
        build_prediction(
            fg_sensor_id="s",
            fg_site_id="site",
            horizon_minutes=30,
            origin_utc=origin,
            target_utc=origin,
            model_family="m",
            run_id="",
            evidence_level="syn",
        )
    with pytest.raises(ValueError, match="binary-or-NULL"):
        build_prediction(
            fg_sensor_id="s",
            fg_site_id="site",
            horizon_minutes=30,
            origin_utc=origin,
            target_utc=origin,
            model_family="m",
            run_id="r",
            evidence_level="syn",
            predicted_label=7,
        )


def test_cross_site_prediction_rejected() -> None:
    session = _seeded_session()
    try:
        from sqlalchemy.exc import IntegrityError  # noqa: F401

        from floodguard.backend.repositories import RepositoryError

        row = build_prediction(
            fg_sensor_id="sensor-wl-001",
            fg_site_id="other-site",
            horizon_minutes=30,
            origin_utc=datetime(2030, 1, 1, tzinfo=UTC),
            target_utc=datetime(2030, 1, 1, 0, 30, tzinfo=UTC),
            model_family="persistence",
            run_id="persistence",
            evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
        )
        with pytest.raises(RepositoryError):
            persist_predictions(session, [row])
    finally:
        session.close()
