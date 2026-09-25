"""Temporal feature engineering for FloodGuard Penang.

Strict point-in-time calculation from normalized observation timestamps in Asia/Kuala_Lumpur.
Covers:
- Phase 4 Task 6: Temporal features (hour, minute, day of week, month, cyclical encodings)

Rules:
- Stateless mathematical transformations: no fitting on full dataset.
- Exact ranges: sine/cosine in [-1.0, 1.0].
- Does NOT fabricate seasonal monsoon boundaries without official meteorological definitions.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from floodguard.features.registry import (
    REGISTRY,
    FeatureDefinition,
    FeatureFamily,
    LeakageClassification,
)

DECIMALS = 6


def _r(x: float) -> float:
    return round(float(x), DECIMALS) + 0.0


def register_temporal_features() -> list[FeatureDefinition]:
    """Register all temporal features into the global registry."""
    defs: list[FeatureDefinition] = [
        FeatureDefinition(
            name="time_hour",
            family=FeatureFamily.TEMPORAL,
            description="Local hour of the day (0-23) at prediction origin t",
            measurement_type="TEMPORAL_COORDINATE",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present for valid prediction origin",
            point_in_time_semantics="Instant t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="time_minute",
            family=FeatureFamily.TEMPORAL,
            description="Local minute of the hour (0-55) at prediction origin t",
            measurement_type="TEMPORAL_COORDINATE",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present for valid prediction origin",
            point_in_time_semantics="Instant t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="time_day_of_week",
            family=FeatureFamily.TEMPORAL,
            description="Day of week (0=Monday to 6=Sunday) at prediction origin t",
            measurement_type="TEMPORAL_COORDINATE",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present for valid prediction origin",
            point_in_time_semantics="Instant t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="time_month",
            family=FeatureFamily.TEMPORAL,
            description="Calendar month (1-12) at prediction origin t",
            measurement_type="TEMPORAL_COORDINATE",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present for valid prediction origin",
            point_in_time_semantics="Instant t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="time_hour_sin",
            family=FeatureFamily.TEMPORAL,
            description="Cyclical sine transformation of hour of day: sin(2*pi*hour/24)",
            measurement_type="CYCLICAL_COORDINATE",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present in [-1.0, 1.0]",
            point_in_time_semantics="Instant t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="time_hour_cos",
            family=FeatureFamily.TEMPORAL,
            description="Cyclical cosine transformation of hour of day: cos(2*pi*hour/24)",
            measurement_type="CYCLICAL_COORDINATE",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present in [-1.0, 1.0]",
            point_in_time_semantics="Instant t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="time_month_sin",
            family=FeatureFamily.TEMPORAL,
            description="Cyclical sine transformation of month: sin(2*pi*(month-1)/12)",
            measurement_type="CYCLICAL_COORDINATE",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present in [-1.0, 1.0]",
            point_in_time_semantics="Instant t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="time_month_cos",
            family=FeatureFamily.TEMPORAL,
            description="Cyclical cosine transformation of month: cos(2*pi*(month-1)/12)",
            measurement_type="CYCLICAL_COORDINATE",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present in [-1.0, 1.0]",
            point_in_time_semantics="Instant t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="time_day_of_week_sin",
            family=FeatureFamily.TEMPORAL,
            description="Cyclical sine transformation of day of week: sin(2*pi*day/7)",
            measurement_type="CYCLICAL_COORDINATE",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present in [-1.0, 1.0]",
            point_in_time_semantics="Instant t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="time_day_of_week_cos",
            family=FeatureFamily.TEMPORAL,
            description="Cyclical cosine transformation of day of week: cos(2*pi*day/7)",
            measurement_type="CYCLICAL_COORDINATE",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present in [-1.0, 1.0]",
            point_in_time_semantics="Instant t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
        FeatureDefinition(
            name="time_is_weekend",
            family=FeatureFamily.TEMPORAL,
            description="Binary indicator whether origin falls on weekend (Sat/Sun) (1/0)",
            measurement_type="TEMPORAL_INDICATOR",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present (0 or 1)",
            point_in_time_semantics="Instant t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        ),
    ]

    for d in defs:
        if not REGISTRY.contains(d.name):
            REGISTRY.register(d)
    return defs


# Register default definitions
register_temporal_features()


def compute_temporal_features(local_time: datetime) -> dict[str, Any]:
    """Compute stateless deterministic temporal coordinates and cyclical encodings."""
    hour = local_time.hour
    minute = local_time.minute
    day_of_week = local_time.weekday()  # 0=Monday, 6=Sunday
    month = local_time.month

    # Continuous hour in [0.0, 24.0)
    hour_cont = hour + minute / 60.0
    hour_angle = 2.0 * math.pi * hour_cont / 24.0
    hour_sin = _r(math.sin(hour_angle))
    hour_cos = _r(math.cos(hour_angle))

    month_angle = 2.0 * math.pi * (month - 1) / 12.0
    month_sin = _r(math.sin(month_angle))
    month_cos = _r(math.cos(month_angle))

    dow_angle = 2.0 * math.pi * day_of_week / 7.0
    dow_sin = _r(math.sin(dow_angle))
    dow_cos = _r(math.cos(dow_angle))

    is_weekend = 1 if day_of_week in (5, 6) else 0

    return {
        "time_hour": hour,
        "time_minute": minute,
        "time_day_of_week": day_of_week,
        "time_month": month,
        "time_hour_sin": hour_sin,
        "time_hour_cos": hour_cos,
        "time_month_sin": month_sin,
        "time_month_cos": month_cos,
        "time_day_of_week_sin": dow_sin,
        "time_day_of_week_cos": dow_cos,
        "time_is_weekend": is_weekend,
    }
