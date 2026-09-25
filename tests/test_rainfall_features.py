"""Offline tests for rainfall rolling and antecedent features (Phase 4 Tasks 1 & 2).

All series are SYNTHETIC (year 2030, test station IDs).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from floodguard.features.rainfall import (
    compute_rainfall_window_metrics,
    extract_rainfall_features,
    register_rainfall_features,
)
from floodguard.features.registry import REGISTRY

pytestmark = pytest.mark.usefixtures("no_network")

MYT = timezone(timedelta(hours=8))
START = datetime(2030, 1, 1, 0, 5, tzinfo=MYT)


def make_rf_row(
    i: int,
    value: float | None,
    *,
    sensor: str = "RF_001",
    site: str = "SITE_001",
    start: datetime = START,
) -> dict[str, Any]:
    local = start + timedelta(minutes=5 * i)
    return {
        "observation_schema_version": "observations/v1",
        "source": "JPS_PUBLIC_INFOBANJIR",
        "fg_sensor_id": sensor,
        "fg_site_id": site,
        "sensor_type": "RAINFALL",
        "measurement_type": "RAINFALL_INTERVAL",
        "observation_time_local": local.isoformat(),
        "observation_time_utc": local.astimezone(UTC).isoformat(),
        "value": value,
        "unit": "mm",
        "quality_flags": ["TIMEZONE_ASSUMED"] if value is not None else ["VALUE_MISSING_SENTINEL"],
        "usable": value is not None,
    }


def make_rf_series(values: Sequence[float | None], **kw: Any) -> list[dict[str, Any]]:
    return [make_rf_row(i, v, **kw) for i, v in enumerate(values)]


# --- Tests for registry ---


def test_rainfall_feature_registration() -> None:
    defs = register_rainfall_features()
    assert len(defs) > 0
    assert REGISTRY.contains("rf_roll_15m_sum_mm")
    assert REGISTRY.contains("rf_roll_60m_sum_mm")
    assert REGISTRY.contains("rf_roll_180m_sum_mm")
    assert REGISTRY.contains("rf_minutes_since_last_wet")
    assert REGISTRY.contains("rf_lag_0m_mm")
    assert REGISTRY.contains("rf_lag_5m_mm")
    assert REGISTRY.contains("rf_lag_30m_mm")
    assert REGISTRY.contains("rf_antecedent_6h_sum_mm")
    assert REGISTRY.contains("rf_antecedent_24h_sum_mm")


# --- Window metric pure function tests ---


def test_window_metrics_full_coverage() -> None:
    res = compute_rainfall_window_metrics([2.0, 3.0, 5.0], expected_slots=3, min_coverage_ratio=0.8)
    assert res["sum_mm"] == 10.0
    assert res["max_mm"] == 5.0
    assert res["wet_count"] == 3
    assert res["coverage_ratio"] == 1.0
    assert res["is_wet"] == 1


def test_window_metrics_all_zero() -> None:
    res = compute_rainfall_window_metrics([0.0, 0.0, 0.0], expected_slots=3, min_coverage_ratio=0.8)
    assert res["sum_mm"] == 0.0
    assert res["max_mm"] == 0.0
    assert res["wet_count"] == 0
    assert res["coverage_ratio"] == 1.0
    assert res["is_wet"] == 0


def test_window_metrics_insufficient_coverage() -> None:
    res = compute_rainfall_window_metrics([5.0], expected_slots=3, min_coverage_ratio=0.8)
    assert res["sum_mm"] is None
    assert res["max_mm"] is None
    assert res["wet_count"] is None
    assert res["coverage_ratio"] == 0.333333
    assert res["is_wet"] is None


# --- End-to-end rainfall feature extraction tests ---


def test_rainfall_features_exact_boundaries_and_lags() -> None:
    vals: Sequence[float | None] = [0.0] * 6 + [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    rows = make_rf_series(vals)
    feats = extract_rainfall_features(rows)
    assert len(feats) == 12

    last = feats[11]
    assert last["rf_lag_0m_mm"] == 6.0
    assert last["rf_lag_5m_mm"] == 5.0
    assert last["rf_lag_10m_mm"] == 4.0
    assert last["rf_lag_15m_mm"] == 3.0
    assert last["rf_lag_30m_mm"] == 0.0
    assert last["rf_lag_60m_mm"] is None

    assert last["rf_roll_15m_sum_mm"] == 15.0
    assert last["rf_roll_15m_max_mm"] == 6.0
    assert last["rf_roll_15m_wet_count"] == 3
    assert last["rf_roll_15m_coverage_ratio"] == 1.0
    assert last["rf_roll_15m_is_wet"] == 1

    assert last["rf_roll_30m_sum_mm"] == 21.0
    assert last["rf_roll_30m_max_mm"] == 6.0
    assert last["rf_roll_30m_wet_count"] == 6
    assert last["rf_roll_30m_coverage_ratio"] == 1.0

    assert last["rf_minutes_since_last_wet"] == 0.0


def test_minutes_since_last_wet_dry_run() -> None:
    vals: Sequence[float | None] = [0.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0]
    rows = make_rf_series(vals)
    feats = extract_rainfall_features(rows)

    assert feats[0]["rf_minutes_since_last_wet"] is None
    assert feats[3]["rf_minutes_since_last_wet"] is None

    assert feats[4]["rf_minutes_since_last_wet"] == 0.0

    assert feats[5]["rf_minutes_since_last_wet"] == 5.0
    assert feats[6]["rf_minutes_since_last_wet"] == 10.0
    assert feats[7]["rf_minutes_since_last_wet"] == 15.0


def test_missing_intervals_not_zero() -> None:
    vals: Sequence[float | None] = [1.0, None, None, 2.0, None, 3.0]
    rows = make_rf_series(vals)
    feats = extract_rainfall_features(rows)

    last = feats[-1]
    assert last["rf_roll_30m_coverage_ratio"] == 0.5
    assert last["rf_roll_30m_sum_mm"] is None
    assert last["rf_roll_30m_max_mm"] is None
    assert last["rf_roll_30m_wet_count"] is None


def test_adversarial_future_mutation_leakage_guard() -> None:
    """ADVERSARIAL LEAKAGE TEST:
    Mutate all observations at t' > 5 radically and verify features at t=5 remain identical.
    """
    base_vals: Sequence[float | None] = [0.0, 1.0, 2.0, 0.5, 0.0, 3.0, 0.0, 0.0, 1.0, 0.0]
    rows_original = make_rf_series(base_vals)

    feats_orig = extract_rainfall_features(rows_original)
    orig_t5 = feats_orig[5]

    mutated_vals: Sequence[float | None] = [0.0, 1.0, 2.0, 0.5, 0.0, 3.0, 999.0, None, 500.0, 250.0]
    rows_mutated = make_rf_series(mutated_vals)

    feats_mutated = extract_rainfall_features(rows_mutated)
    mutated_t5 = feats_mutated[5]

    for k in orig_t5:
        assert orig_t5[k] == mutated_t5[k], (
            f"Leakage detected in {k}: {orig_t5[k]} != {mutated_t5[k]}"
        )
