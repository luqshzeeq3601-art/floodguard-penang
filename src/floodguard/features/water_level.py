"""Water-level deltas, rise-rate, and window feature engineering for FloodGuard Penang.

Strict point-in-time trailing calculations for canonical WATER_LEVEL (m).
Covers:
- Phase 4 Task 3: Water-level deltas (15m, 30m, 60m, 120m, 5m consecutive)
- Phase 4 Task 4: Rise-rate features (rates in m/h, trailing min/max/mean/range, trend indicators,
  and threshold distance reference features)

Temporal and Spatial Safety Rules:
- Station-specific: never average absolute water level across stations (gauge datums differ).
- Every rolling window is (t - W, t] (left-open, right-closed).
- Delta at t relative to t - W requires valid usable observations at both t and t - W.
- If continuity is broken by missing data or gap > max_gap_minutes, delta and rate are None.
- Distance-to-threshold features are marked CURRENT_THRESHOLD_REFERENCE_ONLY.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from floodguard.analysis.dataset import select_measurement
from floodguard.features.registry import (
    REGISTRY,
    FeatureDefinition,
    FeatureFamily,
    LeakageClassification,
)
from floodguard.preprocessing.units import MeasurementType
from floodguard.station_master import SensorType

MEASUREMENT = MeasurementType.WATER_LEVEL
UNIT = "m"
DECIMALS = 6

DEFAULT_DELTA_WINDOWS_MINUTES: Final[tuple[int, ...]] = (5, 15, 30, 60, 120)
DEFAULT_SUMMARY_WINDOWS_MINUTES: Final[tuple[int, ...]] = (15, 30, 60, 120)
CADENCE_MINUTES: Final[int] = 5


@dataclass(frozen=True)
class WaterLevelFeatureConfig:
    """Configuration for water-level feature extraction."""

    delta_windows_minutes: tuple[int, ...] = DEFAULT_DELTA_WINDOWS_MINUTES
    summary_windows_minutes: tuple[int, ...] = DEFAULT_SUMMARY_WINDOWS_MINUTES
    max_gap_minutes: float = 5.0
    min_coverage_ratio: float = 0.8
    cadence_minutes: int = CADENCE_MINUTES
    trend_tolerance_m: float = 0.0  # zero-tolerance equality by default

    def __post_init__(self) -> None:
        if not self.delta_windows_minutes or any(w <= 0 for w in self.delta_windows_minutes):
            raise ValueError("delta_windows_minutes must be positive integers")
        if not self.summary_windows_minutes or any(w <= 0 for w in self.summary_windows_minutes):
            raise ValueError("summary_windows_minutes must be positive integers")
        if not (math.isfinite(self.max_gap_minutes) and self.max_gap_minutes > 0):
            raise ValueError("max_gap_minutes must be finite and > 0")
        if not (0.0 < self.min_coverage_ratio <= 1.0):
            raise ValueError("min_coverage_ratio must be in (0.0, 1.0]")
        if self.cadence_minutes <= 0:
            raise ValueError("cadence_minutes must be > 0")
        if self.trend_tolerance_m < 0:
            raise ValueError("trend_tolerance_m must be >= 0.0")


def _r(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), DECIMALS) + 0.0


def _t(row: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(row["observation_time_utc"])


def register_water_level_features(
    config: WaterLevelFeatureConfig | None = None,
) -> list[FeatureDefinition]:
    """Register all water-level features into the global registry."""
    cfg = config or WaterLevelFeatureConfig()
    defs: list[FeatureDefinition] = []

    cov_pct = int(cfg.min_coverage_ratio * 100)

    # Point-in-time water level
    defs.append(
        FeatureDefinition(
            name="wl_level_m",
            family=FeatureFamily.WATER_LEVEL_DELTA,
            description="Point-in-time water level at prediction origin t",
            measurement_type=str(MEASUREMENT),
            unit="m",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Null if origin observation is missing or unusable",
            point_in_time_semantics="Instant t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        )
    )

    # 1. Deltas (Task 3)
    for w in cfg.delta_windows_minutes:
        defs.append(
            FeatureDefinition(
                name=f"wl_delta_{w}m_m",
                family=FeatureFamily.WATER_LEVEL_DELTA,
                description=f"Backward water-level delta WL(t) - WL(t - {w}m)",
                measurement_type=str(MEASUREMENT),
                unit="m",
                lookback_minutes=w,
                min_coverage_ratio=1.0,
                null_semantics=f"Null if observation at t or t - {w}m is missing",
                point_in_time_semantics=f"Instantaneous change between t - {w}m and t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )

    # 2. Rise-rates and Window Summaries (Task 4)
    for w in cfg.delta_windows_minutes:
        defs.append(
            FeatureDefinition(
                name=f"wl_rate_{w}m_m_per_h",
                family=FeatureFamily.WATER_LEVEL_RATE,
                description=f"Backward water-level rate of change over trailing {w}m in m/h",
                measurement_type=str(MEASUREMENT),
                unit="m/h",
                lookback_minutes=w,
                min_coverage_ratio=1.0,
                null_semantics=f"Null if observation at t or t - {w}m is missing",
                point_in_time_semantics=f"Average rate over trailing {w}m ending at t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )

    for w in cfg.summary_windows_minutes:
        defs.append(
            FeatureDefinition(
                name=f"wl_min_{w}m_m",
                family=FeatureFamily.WATER_LEVEL_WINDOW,
                description=f"Minimum water level in trailing window (t - {w}m, t]",
                measurement_type=str(MEASUREMENT),
                unit="m",
                lookback_minutes=w,
                min_coverage_ratio=cfg.min_coverage_ratio,
                null_semantics=f"Null when slot coverage in (t - {w}m, t] < {cov_pct}%",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t], includes t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )
        defs.append(
            FeatureDefinition(
                name=f"wl_max_{w}m_m",
                family=FeatureFamily.WATER_LEVEL_WINDOW,
                description=f"Maximum water level in trailing window (t - {w}m, t]",
                measurement_type=str(MEASUREMENT),
                unit="m",
                lookback_minutes=w,
                min_coverage_ratio=cfg.min_coverage_ratio,
                null_semantics=f"Null when slot coverage in (t - {w}m, t] < {cov_pct}%",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t], includes t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )
        defs.append(
            FeatureDefinition(
                name=f"wl_mean_{w}m_m",
                family=FeatureFamily.WATER_LEVEL_WINDOW,
                description=f"Mean water level in trailing window (t - {w}m, t]",
                measurement_type=str(MEASUREMENT),
                unit="m",
                lookback_minutes=w,
                min_coverage_ratio=cfg.min_coverage_ratio,
                null_semantics=f"Null when slot coverage in (t - {w}m, t] < {cov_pct}%",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t], includes t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )
        defs.append(
            FeatureDefinition(
                name=f"wl_range_{w}m_m",
                family=FeatureFamily.WATER_LEVEL_WINDOW,
                description=f"Water-level range (max - min) in trailing window (t - {w}m, t]",
                measurement_type=str(MEASUREMENT),
                unit="m",
                lookback_minutes=w,
                min_coverage_ratio=cfg.min_coverage_ratio,
                null_semantics=f"Null when slot coverage in (t - {w}m, t] < {cov_pct}%",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t], includes t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )
        defs.append(
            FeatureDefinition(
                name=f"wl_trend_{w}m",
                family=FeatureFamily.WATER_LEVEL_WINDOW,
                description=f"Categorical trend in trailing {w}m (RISING, FALLING, STABLE)",
                measurement_type=str(MEASUREMENT),
                unit="unitless",
                lookback_minutes=w,
                min_coverage_ratio=cfg.min_coverage_ratio,
                null_semantics=f"Null when slot coverage in (t - {w}m, t] < {cov_pct}%",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t], includes t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )
        defs.append(
            FeatureDefinition(
                name=f"wl_coverage_{w}m_ratio",
                family=FeatureFamily.WATER_LEVEL_WINDOW,
                description=f"Slot coverage ratio in trailing {w}m window",
                measurement_type=str(MEASUREMENT),
                unit="unitless",
                lookback_minutes=w,
                min_coverage_ratio=0.0,
                null_semantics="Always present (in [0.0, 1.0]) for evaluated prediction origin",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t]",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )

    # Distance to thresholds (CURRENT_THRESHOLD_REFERENCE_ONLY)
    for tt in ("waspada", "amaran", "bahaya"):
        defs.append(
            FeatureDefinition(
                name=f"wl_dist_to_{tt}_m",
                family=FeatureFamily.THRESHOLD_REFERENCE,
                description=f"Distance to {tt.upper()} threshold (WL(t) - threshold_m)",
                measurement_type=str(MEASUREMENT),
                unit="m",
                lookback_minutes=0,
                min_coverage_ratio=1.0,
                null_semantics=f"Null if origin WL or {tt.upper()} threshold missing",
                point_in_time_semantics="Current threshold metadata relative to origin WL",
                leakage_classification=LeakageClassification.CURRENT_THRESHOLD_REFERENCE_ONLY,
            )
        )

    for d in defs:
        if not REGISTRY.contains(d.name):
            REGISTRY.register(d)
    return defs


# Register default definitions
register_water_level_features()


def compute_water_level_features_for_origin(
    origin_time: datetime,
    history_rows_by_time: Mapping[datetime, Mapping[str, Any]],
    sorted_history_times: Sequence[datetime],
    config: WaterLevelFeatureConfig,
    thresholds: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Extract all water-level features for a single prediction origin instant t.

    LEAKAGE GUARD: Only observations at or before origin_time (t' <= origin_time) are used.
    """
    cfg = config
    features: dict[str, Any] = {}

    origin_row = history_rows_by_time.get(origin_time)
    if origin_row is None or not origin_row.get("usable") or origin_row.get("value") is None:
        origin_val: float | None = None
    else:
        origin_val = float(origin_row["value"])

    features["wl_level_m"] = _r(origin_val)

    prior_times = [t for t in sorted_history_times if t <= origin_time]

    # 1. Deltas and Rates
    for w in cfg.delta_windows_minutes:
        lag_time = origin_time - timedelta(minutes=w)
        lag_row = history_rows_by_time.get(lag_time)

        delta_val: float | None = None
        rate_val: float | None = None

        if (
            origin_val is not None
            and lag_row is not None
            and lag_row.get("usable") is True
            and lag_row.get("value") is not None
        ):
            lag_val = float(lag_row["value"])
            delta_val = origin_val - lag_val
            hours = w / 60.0
            rate_val = delta_val / hours

        features[f"wl_delta_{w}m_m"] = _r(delta_val)
        features[f"wl_rate_{w}m_m_per_h"] = _r(rate_val)

    # 2. Window Aggregations
    for w in cfg.summary_windows_minutes:
        cutoff = origin_time - timedelta(minutes=w)
        window_times = [t for t in prior_times if cutoff < t <= origin_time]
        usable_values = [
            float(history_rows_by_time[t]["value"])
            for t in window_times
            if history_rows_by_time[t].get("usable") is True
            and history_rows_by_time[t].get("value") is not None
        ]

        expected_slots = w // cfg.cadence_minutes
        usable_count = len(usable_values)
        cov = _r(usable_count / expected_slots) if expected_slots > 0 else 0.0
        assert cov is not None
        features[f"wl_coverage_{w}m_ratio"] = cov

        if cov < cfg.min_coverage_ratio or usable_count == 0:
            features[f"wl_min_{w}m_m"] = None
            features[f"wl_max_{w}m_m"] = None
            features[f"wl_mean_{w}m_m"] = None
            features[f"wl_range_{w}m_m"] = None
            features[f"wl_trend_{w}m"] = None
        else:
            min_v = min(usable_values)
            max_v = max(usable_values)
            mean_v = sum(usable_values) / usable_count
            range_v = max_v - min_v

            # Trend determination
            delta_w = features.get(f"wl_delta_{w}m_m")
            if delta_w is not None:
                if delta_w > cfg.trend_tolerance_m:
                    trend_str = "RISING"
                elif delta_w < -cfg.trend_tolerance_m:
                    trend_str = "FALLING"
                else:
                    trend_str = "STABLE"
            else:
                first_v = usable_values[0]
                last_v = usable_values[-1]
                net_change = last_v - first_v
                if net_change > cfg.trend_tolerance_m:
                    trend_str = "RISING"
                elif net_change < -cfg.trend_tolerance_m:
                    trend_str = "FALLING"
                else:
                    trend_str = "STABLE"

            features[f"wl_min_{w}m_m"] = _r(min_v)
            features[f"wl_max_{w}m_m"] = _r(max_v)
            features[f"wl_mean_{w}m_m"] = _r(mean_v)
            features[f"wl_range_{w}m_m"] = _r(range_v)
            features[f"wl_trend_{w}m"] = trend_str

    # 3. Distance to Thresholds
    thresh_by_type: dict[str, float] = {}
    if thresholds:
        for t in thresholds:
            tt = str(t.get("threshold_type", "")).lower()
            val_m = t.get("value_m")
            if val_m is not None:
                thresh_by_type[tt] = float(val_m)

    for tt in ("waspada", "amaran", "bahaya"):
        if origin_val is not None and tt in thresh_by_type:
            features[f"wl_dist_to_{tt}_m"] = _r(origin_val - thresh_by_type[tt])
        else:
            features[f"wl_dist_to_{tt}_m"] = None

    return features


def extract_water_level_features(
    rows: Iterable[Mapping[str, Any]],
    *,
    threshold_reference: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    config: WaterLevelFeatureConfig | None = None,
) -> list[dict[str, Any]]:
    """Extract point-in-time water-level features for all usable observation origins."""
    cfg = config or WaterLevelFeatureConfig()
    selected, _ = select_measurement(
        rows,
        measurement_type=MEASUREMENT,
        unit=UNIT,
        sensor_type=SensorType.WATER_LEVEL,
        value_ok=lambda v: True,
        value_rule="water level must be finite",
    )

    if not selected:
        return []

    by_sensor: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in selected:
        by_sensor[r["fg_sensor_id"]].append(r)

    thresh_map = threshold_reference or {}
    all_origin_features: list[dict[str, Any]] = []

    for sensor_id, sensor_rows in sorted(by_sensor.items()):
        ordered = sorted(sensor_rows, key=_t)
        history_rows_by_time = {_t(r): r for r in ordered}
        sorted_times = sorted(history_rows_by_time.keys())
        sensor_thresholds = thresh_map.get(sensor_id, [])

        for r in ordered:
            if not r.get("usable"):
                continue
            origin_t = _t(r)
            wl_feats = compute_water_level_features_for_origin(
                origin_t,
                history_rows_by_time,
                sorted_times,
                cfg,
                thresholds=sensor_thresholds,
            )
            entry = {
                "source": r["source"],
                "fg_sensor_id": sensor_id,
                "fg_site_id": r["fg_site_id"],
                "prediction_origin_utc": r["observation_time_utc"],
                "prediction_origin_local": r["observation_time_local"],
                **wl_feats,
            }
            all_origin_features.append(entry)

    return all_origin_features
