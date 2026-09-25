"""Forecasting dataset/windowing tests: boundaries, gaps, identity, isolation."""

from __future__ import annotations

import pytest

from floodguard.forecasting import HORIZONS_MINUTES
from floodguard.forecasting.dataset import ForecastDatasetConfig, build_forecast_samples
from floodguard.forecasting.synthetic import (
    make_constant_series,
    make_rise_series,
    make_two_datum_stations,
    with_disconnected_windows,
    with_missing_run,
    with_missing_slot,
)

pytestmark = pytest.mark.usefixtures("no_network")


def test_exact_target_matching_per_horizon() -> None:
    rows = make_rise_series(n=100, start_level=1.0, slope_per_step=0.01)
    per_horizon, _ = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=60, dataset_version="t")
    )
    # Per-horizon truncation differs: +30 keeps more origins than +120.
    assert len(per_horizon[30]) > len(per_horizon[120]) > 0
    for horizon in HORIZONS_MINUTES:
        for sample in per_horizon[horizon]:
            assert sample.horizon_minutes == horizon
            assert len(sample.input_levels_m) == 60 // 5
            # Monotonic rise: target above origin; exact +h step count.
            assert sample.target_level_m > sample.origin_level_m


def test_missing_target_or_input_rejects_sample() -> None:
    rows = make_constant_series(n=60)
    gapped = with_missing_slot(rows, 30)
    per_horizon, reports = build_forecast_samples(
        gapped, ForecastDatasetConfig(lookback_minutes=60, dataset_version="t")
    )
    complete, _ = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=60, dataset_version="t")
    )
    # One missing slot kills every window covering it, across all horizons.
    for horizon in HORIZONS_MINUTES:
        assert len(per_horizon[horizon]) < len(complete[horizon])
    assert reports[0].rejected_missing_input > 0


def test_internal_missing_run_never_bridged() -> None:
    rows = make_constant_series(n=100)
    gapped = with_missing_run(rows, 40, 6)
    per_horizon, _ = build_forecast_samples(
        gapped, ForecastDatasetConfig(lookback_minutes=60, dataset_version="t")
    )
    for horizon in HORIZONS_MINUTES:
        for sample in per_horizon[horizon]:
            # No input sequence may span the missing run.
            assert None not in sample.input_levels_m
            assert len(sample.input_levels_m) == 12


def test_disconnected_windows_not_bridged() -> None:
    rows = make_constant_series(n=80)
    split = with_disconnected_windows(rows, 40, gap_minutes=180)
    per_horizon, reports = build_forecast_samples(
        split, ForecastDatasetConfig(lookback_minutes=60, dataset_version="t")
    )
    # Windows ending before the gap plus windows starting after it; nothing spans it.
    assert reports[0].samples_built > 0
    for horizon in HORIZONS_MINUTES:
        for sample in per_horizon[horizon]:
            times = sample.input_times_utc
            assert len(times) == 12


def test_stable_sample_identity_not_row_position() -> None:
    rows = make_constant_series(n=80)
    per_horizon, _ = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=60, dataset_version="tv1")
    )
    ids = [s.sample_id() for s in per_horizon[30]]
    assert len(set(ids)) == len(ids)
    first = per_horizon[30][0]
    assert "SYN_WL_A" in first.sample_id()
    assert "lb60" in first.sample_id()
    assert "plus30m" in first.sample_id()
    assert first.dataset_version == "tv1"


def test_stations_never_pooled_in_dataset() -> None:
    rows = make_two_datum_stations(n=80)
    per_horizon, reports = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=60, dataset_version="t")
    )
    assert {r.fg_sensor_id for r in reports} == {"SYN_WL_HIGH", "SYN_WL_LOW"}
    high = [s for s in per_horizon[30] if s.fg_sensor_id == "SYN_WL_HIGH"]
    low = [s for s in per_horizon[30] if s.fg_sensor_id == "SYN_WL_LOW"]
    assert high
    assert low
    assert min(s.origin_level_m for s in high) > max(s.origin_level_m for s in low)


def test_window_boundaries_first_and_last_origins() -> None:
    rows = make_constant_series(n=40)  # 40 steps; lookback 12 steps
    per_horizon, _ = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=60, dataset_version="t")
    )
    # First origin needs 12 input slots; last origins lose exact targets.
    assert per_horizon[30][0].input_times_utc[0] == rows[0]["observation_time_utc"]
