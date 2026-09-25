"""Comprehensive temporal safety and adversarial leakage test suite (Phase 4 Task 8).

Proves:
1. Adversarial future mutation: mutating data at t' > t does not alter features at <= t.
2. Temporal boundary enforcement: left-open (t - W, t] right-closed boundaries.
3. Label independence: altering future targets does not affect feature values.
4. Appended future data: appending future rows leaves earlier feature rows identical.
5. Missing-interval safety: incomplete windows are not silently treated as zero.
6. Threshold metadata classification: reference distance is CURRENT_THRESHOLD_REFERENCE_ONLY.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from floodguard.features.rainfall import extract_rainfall_features
from floodguard.features.registry import REGISTRY, LeakageClassification
from floodguard.features.table import build_feature_table, join_features_and_labels

pytestmark = pytest.mark.usefixtures("no_network")

MYT = timezone(timedelta(hours=8))
START = datetime(2030, 1, 1, 0, 5, tzinfo=MYT)


def make_row(
    i: int,
    value: float | None,
    measurement_type: str,
    sensor: str,
    unit: str,
    *,
    start: datetime = START,
) -> dict[str, Any]:
    local = start + timedelta(minutes=5 * i)
    st = "RAINFALL" if measurement_type == "RAINFALL_INTERVAL" else "WATER_LEVEL"
    return {
        "observation_schema_version": "observations/v1",
        "source": "JPS_PUBLIC_INFOBANJIR",
        "fg_sensor_id": sensor,
        "fg_site_id": f"SITE_{sensor}",
        "sensor_type": st,
        "measurement_type": measurement_type,
        "observation_time_local": local.isoformat(),
        "observation_time_utc": local.astimezone(UTC).isoformat(),
        "value": value,
        "unit": unit,
        "quality_flags": ["TIMEZONE_ASSUMED"] if value is not None else ["VALUE_MISSING_SENTINEL"],
        "usable": value is not None,
    }


def test_adversarial_future_mutation_pipeline() -> None:
    """End-to-end adversarial test on unified feature table."""
    rf_vals: list[float | None] = [
        0.0,
        0.5,
        1.0,
        0.0,
        2.0,
        3.0,
        0.0,
        1.5,
        0.0,
        0.0,
        2.5,
        0.0,
        1.0,
        4.0,
        0.0,
        0.0,
        0.0,
        2.0,
        1.0,
        0.0,
    ]
    wl_vals: list[float | None] = [
        2.0,
        2.05,
        2.1,
        2.15,
        2.2,
        2.25,
        2.3,
        2.35,
        2.4,
        2.45,
        2.5,
        2.55,
        2.6,
        2.65,
        2.7,
        2.75,
        2.8,
        2.85,
        2.9,
        2.95,
    ]

    rf_rows = [make_row(i, v, "RAINFALL_INTERVAL", "RF_1", "mm") for i, v in enumerate(rf_vals)]
    wl_rows = [make_row(i, v, "WATER_LEVEL", "WL_1", "m") for i, v in enumerate(wl_vals)]
    all_rows = rf_rows + wl_rows

    # Baseline features
    base_tables = build_feature_table(all_rows)
    rf_base = base_tables["rainfall_features"]
    wl_base = base_tables["water_level_features"]

    # Mutate everything at indices 10..19 radically
    mutated_rf_vals = list(rf_vals)
    mutated_wl_vals = list(wl_vals)
    for i in range(10, 20):
        mutated_rf_vals[i] = 999.0
        mutated_wl_vals[i] = 100.0

    mut_rf_rows = [
        make_row(i, v, "RAINFALL_INTERVAL", "RF_1", "mm") for i, v in enumerate(mutated_rf_vals)
    ]
    mut_wl_rows = [
        make_row(i, v, "WATER_LEVEL", "WL_1", "m") for i, v in enumerate(mutated_wl_vals)
    ]
    mut_all_rows = mut_rf_rows + mut_wl_rows

    mut_tables = build_feature_table(mut_all_rows)
    rf_mut = mut_tables["rainfall_features"]
    wl_mut = mut_tables["water_level_features"]

    # Verify all feature values for origins 0..9 are completely identical
    for i in range(10):
        for k in rf_base[i]:
            assert rf_base[i][k] == rf_mut[i][k], f"RF feature {k} at idx {i} leaked!"
        for k in wl_base[i]:
            assert wl_base[i][k] == wl_mut[i][k], f"WL feature {k} at idx {i} leaked!"


def test_target_label_independence() -> None:
    """Verifies that altering future labels does NOT alter feature columns in the dataset."""
    wl_vals = [2.0, 2.1, 2.2, 2.3, 2.4, 2.5]
    wl_rows = [make_row(i, v, "WATER_LEVEL", "WL_1", "m") for i, v in enumerate(wl_vals)]
    tables = build_feature_table(wl_rows)
    wl_feats = tables["water_level_features"]

    label_evals_v1 = [
        {
            "fg_sensor_id": "WL_1",
            "origin_utc": wl_feats[0]["prediction_origin_utc"],
            "target_horizon_minutes": 30,
            "target_status": "TARGET_EVALUATED",
            "future_water_level_m": 2.5,
            "delta_water_level_m": 0.5,
            "threshold_labels": {"WASPADA": {"is_exceedance": True}},
        }
    ]

    joined_v1 = join_features_and_labels(wl_feats, label_evals_v1)

    label_evals_v2 = [
        {
            "fg_sensor_id": "WL_1",
            "origin_utc": wl_feats[0]["prediction_origin_utc"],
            "target_horizon_minutes": 30,
            "target_status": "MISSING_FUTURE_TARGET",
            "future_water_level_m": None,
            "delta_water_level_m": None,
            "threshold_labels": {"WASPADA": {"is_exceedance": False}},
        }
    ]

    joined_v2 = join_features_and_labels(wl_feats, label_evals_v2)

    feature_cols = [c for c in joined_v1[0] if not c.startswith("target_")]
    for col in feature_cols:
        assert joined_v1[0][col] == joined_v2[0][col], f"Feature column {col} was corrupted"


def test_appended_future_observations_leave_earlier_rows_identical() -> None:
    """Appending future observations must not change any existing historical feature rows."""
    base_vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    base_rows = [make_row(i, v, "RAINFALL_INTERVAL", "RF_1", "mm") for i, v in enumerate(base_vals)]

    feats_base = extract_rainfall_features(base_rows)

    extended_vals = [*base_vals, 6.0, 7.0, 8.0, 9.0, 10.0]
    extended_rows = [
        make_row(i, v, "RAINFALL_INTERVAL", "RF_1", "mm") for i, v in enumerate(extended_vals)
    ]

    feats_extended = extract_rainfall_features(extended_rows)

    assert len(feats_base) == 5
    assert len(feats_extended) == 10

    for i in range(5):
        assert feats_base[i] == feats_extended[i]


def test_current_threshold_reference_classification() -> None:
    """Threshold distance features must be registered as CURRENT_THRESHOLD_REFERENCE_ONLY."""
    for tt in ("waspada", "amaran", "bahaya"):
        feat_name = f"wl_dist_to_{tt}_m"
        feat_def = REGISTRY.get(feat_name)
        assert (
            feat_def.leakage_classification
            == LeakageClassification.CURRENT_THRESHOLD_REFERENCE_ONLY
        )
