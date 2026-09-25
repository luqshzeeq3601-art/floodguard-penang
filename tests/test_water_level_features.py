"""Offline tests for water-level deltas and rise-rate features (Phase 4 Tasks 3 & 4).

All series are SYNTHETIC (year 2030, test station IDs).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from floodguard.features.registry import REGISTRY, LeakageClassification
from floodguard.features.water_level import (
    extract_water_level_features,
    register_water_level_features,
)

pytestmark = pytest.mark.usefixtures("no_network")

MYT = timezone(timedelta(hours=8))
START = datetime(2030, 1, 1, 0, 5, tzinfo=MYT)


def make_wl_row(
    i: int,
    value: float | None,
    *,
    sensor: str = "WL_001",
    site: str = "SITE_001",
    start: datetime = START,
) -> dict[str, Any]:
    local = start + timedelta(minutes=5 * i)
    return {
        "observation_schema_version": "observations/v1",
        "source": "JPS_PUBLIC_INFOBANJIR",
        "fg_sensor_id": sensor,
        "fg_site_id": site,
        "sensor_type": "WATER_LEVEL",
        "measurement_type": "WATER_LEVEL",
        "observation_time_local": local.isoformat(),
        "observation_time_utc": local.astimezone(UTC).isoformat(),
        "value": value,
        "unit": "m",
        "quality_flags": ["TIMEZONE_ASSUMED"] if value is not None else ["VALUE_MISSING_SENTINEL"],
        "usable": value is not None,
    }


def make_wl_series(values: Sequence[float | None], **kw: Any) -> list[dict[str, Any]]:
    return [make_wl_row(i, v, **kw) for i, v in enumerate(values)]


# --- Tests for registry ---


def test_water_level_feature_registration() -> None:
    defs = register_water_level_features()
    assert len(defs) > 0
    assert REGISTRY.contains("wl_level_m")
    assert REGISTRY.contains("wl_delta_15m_m")
    assert REGISTRY.contains("wl_rate_15m_m_per_h")
    assert REGISTRY.contains("wl_min_30m_m")
    assert REGISTRY.contains("wl_max_30m_m")
    assert REGISTRY.contains("wl_range_30m_m")
    assert REGISTRY.contains("wl_trend_30m")
    assert REGISTRY.contains("wl_dist_to_waspada_m")

    # Check leakage classification
    d_waspada = REGISTRY.get("wl_dist_to_waspada_m")
    assert (
        d_waspada.leakage_classification == LeakageClassification.CURRENT_THRESHOLD_REFERENCE_ONLY
    )


# --- Tests for water level deltas and rates ---


def test_water_level_deltas_and_rates_rising() -> None:
    vals: Sequence[float | None] = [2.0, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6]
    rows = make_wl_series(vals)
    feats = extract_water_level_features(rows)
    assert len(feats) == 7

    last = feats[6]
    assert last["wl_level_m"] == 2.6
    assert last["wl_delta_5m_m"] == 0.1
    assert last["wl_rate_5m_m_per_h"] == 1.2
    assert last["wl_delta_15m_m"] == 0.3
    assert last["wl_rate_15m_m_per_h"] == 1.2
    assert last["wl_delta_30m_m"] == 0.6
    assert last["wl_rate_30m_m_per_h"] == 1.2

    # Window metrics trailing 30m
    assert last["wl_min_30m_m"] == 2.1
    assert last["wl_max_30m_m"] == 2.6
    assert last["wl_range_30m_m"] == 0.5
    assert last["wl_trend_30m"] == "RISING"


def test_water_level_deltas_falling_and_stable() -> None:
    # Falling
    rows_falling = make_wl_series([3.0, 2.8, 2.6, 2.4])
    feats_falling = extract_water_level_features(rows_falling)
    last_f = feats_falling[3]
    assert last_f["wl_delta_15m_m"] == -0.6
    assert last_f["wl_rate_15m_m_per_h"] == -2.4
    assert last_f["wl_trend_15m"] == "FALLING"

    # Stable
    rows_stable = make_wl_series([2.5, 2.5, 2.5, 2.5])
    feats_stable = extract_water_level_features(rows_stable)
    last_s = feats_stable[3]
    assert last_s["wl_delta_15m_m"] == 0.0
    assert last_s["wl_rate_15m_m_per_h"] == 0.0
    assert last_s["wl_trend_15m"] == "STABLE"


def test_water_level_missing_lag_yields_none() -> None:
    rows = make_wl_series([2.0, None, None, 2.5])
    feats = extract_water_level_features(rows)
    last = feats[-1]
    assert last["wl_delta_5m_m"] is None
    assert last["wl_rate_5m_m_per_h"] is None
    assert last["wl_delta_15m_m"] == 0.5


def test_water_level_distance_to_thresholds() -> None:
    thresholds = {
        "WL_001": [
            {"threshold_type": "WASPADA", "value_m": 3.0},
            {"threshold_type": "AMARAN", "value_m": 3.5},
            {"threshold_type": "BAHAYA", "value_m": 4.0},
        ]
    }
    rows = make_wl_series([2.8], sensor="WL_001")
    feats = extract_water_level_features(rows, threshold_reference=thresholds)
    f0 = feats[0]
    assert f0["wl_level_m"] == 2.8
    assert f0["wl_dist_to_waspada_m"] == -0.2
    assert f0["wl_dist_to_amaran_m"] == -0.7
    assert f0["wl_dist_to_bahaya_m"] == -1.2


def test_water_level_adversarial_future_mutation_leakage_guard() -> None:
    rows_orig = make_wl_series([2.0, 2.1, 2.2, 2.3, 2.4, 2.5])
    feats_orig = extract_water_level_features(rows_orig)
    orig_t3 = feats_orig[3]

    rows_mutated = make_wl_series([2.0, 2.1, 2.2, 2.3, 99.9, None])
    feats_mutated = extract_water_level_features(rows_mutated)
    mutated_t3 = feats_mutated[3]

    for k in orig_t3:
        assert orig_t3[k] == mutated_t3[k], f"Leakage in {k}: {orig_t3[k]} != {mutated_t3[k]}"
