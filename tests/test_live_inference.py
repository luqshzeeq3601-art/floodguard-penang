"""Live inference tests (Phase 10, Task 6; offline, synthetic, no-model path)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from floodguard.live.inference import (
    HORIZONS,
    NO_FORECAST_MODEL,
    NO_MODEL,
    SKIPPED_NO_MODEL,
    InferenceCollector,
    InferenceStatus,
    check_model_eligibility,
    run_live_inference,
)

pytestmark = pytest.mark.usefixtures("no_network")


def test_eligibility_is_closed_on_current_evidence() -> None:
    gate = check_model_eligibility(None)
    assert gate["classification"] == NO_MODEL
    assert gate["forecast"] == NO_FORECAST_MODEL
    # Even a stored production-looking family never flips the gate here.
    gate2 = check_model_eligibility({"production_model": "production"})
    assert gate2["classification"] == NO_MODEL


def test_no_model_path_per_horizon() -> None:
    result = run_live_inference(
        run_id="run-1",
        sensor_id="sen-1",
        origin_utc=datetime(2030, 1, 1, tzinfo=UTC),
    )
    assert tuple(h.horizon_minutes for h in result.horizons) == HORIZONS
    assert all(h.status is InferenceStatus.SKIPPED_NO_ELIGIBLE_MODEL for h in result.horizons)
    assert all(SKIPPED_NO_MODEL in h.reason for h in result.horizons)
    assert result.predictions == ()


def test_collector_counts_skips_factually() -> None:
    collector = InferenceCollector()
    collector.record(
        run_live_inference(run_id="r", sensor_id="s", origin_utc=datetime(2030, 1, 1, tzinfo=UTC))
    )
    assert collector.skipped == 3
    assert collector.predicted == 0
    assert collector.by_horizon[30]["skipped"] == 1
