"""Offline tests for temporal features and cyclical encodings (Phase 4 Task 6)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from floodguard.features.registry import REGISTRY
from floodguard.features.temporal import compute_temporal_features, register_temporal_features

pytestmark = pytest.mark.usefixtures("no_network")

MYT = timezone(timedelta(hours=8))


def test_temporal_feature_registration() -> None:
    defs = register_temporal_features()
    assert len(defs) > 0
    assert REGISTRY.contains("time_hour")
    assert REGISTRY.contains("time_hour_sin")
    assert REGISTRY.contains("time_hour_cos")
    assert REGISTRY.contains("time_month_sin")
    assert REGISTRY.contains("time_month_cos")
    assert REGISTRY.contains("time_day_of_week_sin")
    assert REGISTRY.contains("time_day_of_week_cos")
    assert REGISTRY.contains("time_is_weekend")


def test_temporal_feature_computations() -> None:
    # 2030-01-01 was a Tuesday (weekday=1), at 06:00
    t = datetime(2030, 1, 1, 6, 0, tzinfo=MYT)
    feats = compute_temporal_features(t)

    assert feats["time_hour"] == 6
    assert feats["time_minute"] == 0
    assert feats["time_day_of_week"] == 1
    assert feats["time_month"] == 1
    assert feats["time_is_weekend"] == 0

    # 6:00 is 6/24 = 1/4 cycle -> sin(pi/2) = 1.0, cos(pi/2) = 0.0
    assert abs(feats["time_hour_sin"] - 1.0) < 1e-5
    assert abs(feats["time_hour_cos"] - 0.0) < 1e-5

    # Month 1 is (1-1)/12 = 0 -> sin(0) = 0.0, cos(0) = 1.0
    assert abs(feats["time_month_sin"] - 0.0) < 1e-5
    assert abs(feats["time_month_cos"] - 1.0) < 1e-5


def test_temporal_cyclical_ranges() -> None:
    keys = (
        "time_hour_sin",
        "time_hour_cos",
        "time_month_sin",
        "time_month_cos",
        "time_day_of_week_sin",
        "time_day_of_week_cos",
    )
    for m in range(1, 13):
        for h in range(24):
            for min_val in (0, 15, 30, 45):
                t = datetime(2030, m, 15, h, min_val, tzinfo=MYT)
                f = compute_temporal_features(t)
                for k in keys:
                    val = f[k]
                    assert -1.0 <= val <= 1.0, f"{k} out of bounds: {val}"
