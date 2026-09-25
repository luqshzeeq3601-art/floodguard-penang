"""Forecasting gates: sequence justification, TimesFM harness, eligibility."""

from __future__ import annotations

from pathlib import Path

import pytest

from floodguard.forecasting import NO_ELIGIBLE_FORECAST_MODEL, NOT_JUSTIFIED
from floodguard.forecasting.evaluation import (
    CandidateRun,
    EligibilityConfig,
    select_forecast_candidate,
)
from floodguard.forecasting.sequence_gate import SequenceGateConfig, assess_sequence_justification
from floodguard.forecasting.timesfm import (
    STATUS_BLOCKED,
    check_timesfm_availability,
    zero_shot_benchmark,
)

pytestmark = pytest.mark.usefixtures("no_network")


def test_lstm_gru_not_justified_on_current_data_volume() -> None:
    """154 usable intervals: neural sequence training is not justified."""
    verdict = assess_sequence_justification(train_samples=120, stations_meeting_coverage=0)
    assert not verdict.justified
    assert verdict.status == NOT_JUSTIFIED


def test_sequence_gate_passes_with_sufficient_volume() -> None:
    verdict = assess_sequence_justification(
        train_samples=5000,
        stations_meeting_coverage=3,
        config=SequenceGateConfig(min_train_samples=1000, min_stations=2),
    )
    assert verdict.justified


def test_sequence_gate_rejects_single_station_history() -> None:
    verdict = assess_sequence_justification(train_samples=5000, stations_meeting_coverage=1)
    assert not verdict.justified
    assert verdict.status == NOT_JUSTIFIED


def test_timesfm_blocked_without_package_or_checkpoint(tmp_path: Path) -> None:
    status = check_timesfm_availability()
    assert status.status == STATUS_BLOCKED
    assert not status.package_installed
    missing = check_timesfm_availability(tmp_path / "nope")
    assert missing.status == STATUS_BLOCKED


def test_timesfm_substitute_predictor_offline() -> None:
    def last_value(history: list[float], steps: int) -> list[float]:
        return [history[-1]] * steps

    assert zero_shot_benchmark([1.0, 2.0, 3.0], 6, predictor=last_value) == [3.0] * 6
    with pytest.raises(ValueError, match="no predictor"):
        zero_shot_benchmark([1.0], 6, predictor=None)
    with pytest.raises(ValueError, match="non-empty"):
        zero_shot_benchmark([], 6, predictor=last_value)


def test_no_forecast_champion_on_station_days() -> None:
    runs = [
        CandidateRun("v1", "lb120", "exact", 30, "s1", "p1", "linear_ar", "a", 40, 1, 0, 0.05),
        CandidateRun(
            "v1", "lb120", "exact", 30, "s1", "p1", "xgboost_regressor", "b", 40, 1, 0, 0.04
        ),
    ]
    decision = select_forecast_candidate(runs, config=EligibilityConfig(min_stations=2))
    assert decision["status"] == NO_ELIGIBLE_FORECAST_MODEL


def test_forecast_selection_needs_matching_context() -> None:
    # Distinct dataset versions are not comparable even with full evidence.
    runs_mismatched = [
        CandidateRun("v1", "lb120", "exact", 30, "s1", "p1", "linear_ar", "a", 500, 3, 3, 0.05),
        CandidateRun("v2", "lb120", "exact", 30, "s1", "p1", "linear_ar", "b", 500, 3, 3, 0.04),
    ]
    decision = select_forecast_candidate(runs_mismatched)
    assert decision["status"] == NO_ELIGIBLE_FORECAST_MODEL


def test_coverage_criterion_enforced() -> None:
    """Stations without covered days cannot carry a candidate (review L2)."""
    runs = [
        CandidateRun("v1", "lb120", "exact", 30, "s1", "p1", "linear_ar", "a", 500, 3, 0, 0.05),
    ]
    decision = select_forecast_candidate(runs)
    assert decision["status"] == NO_ELIGIBLE_FORECAST_MODEL


def test_forecast_candidate_selected_with_evidence() -> None:
    runs = [
        CandidateRun("v1", "lb120", "exact", 30, "s1", "p1", "linear_ar", "a", 500, 3, 3, 0.05),
        CandidateRun(
            "v1", "lb120", "exact", 30, "s1", "p1", "xgboost_regressor", "b", 500, 3, 3, 0.04
        ),
    ]
    decision = select_forecast_candidate(runs)
    assert decision["status"] == "CANDIDATE_SELECTED"
    assert decision["champion_run_id"] == "b"
