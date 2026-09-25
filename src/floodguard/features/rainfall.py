"""Rainfall rolling and antecedent feature engineering for FloodGuard Penang.

Strict point-in-time trailing calculations for canonical RAINFALL_INTERVAL (mm).
Covers:
- Phase 4 Task 1: Rainfall rolling features (15m, 30m, 60m, 120m, 180m)
- Phase 4 Task 2: Antecedent rainfall (exact lags 0m, 5m, 10m, 15m, 30m, 60m; extended 6h, 12h, 24h)

Temporal convention:
- Every rolling window is (t - W, t] (left-open, right-closed).
- Includes the observation at prediction origin t.
- Never includes t + 5m or any future observation.
- Missing intervals are NOT imputed as zero; coverage ratio is strictly tracked.
- If coverage ratio < min_coverage_ratio (default 0.8), feature value is None.
- Exact lag features require usable observation at exact instant t - lag (no interpolation).
"""

from __future__ import annotations

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

MEASUREMENT = MeasurementType.RAINFALL_INTERVAL
UNIT = "mm"
DECIMALS = 6

DEFAULT_ROLLING_WINDOWS_MINUTES: Final[tuple[int, ...]] = (15, 30, 60, 120, 180)
DEFAULT_ANTECEDENT_WINDOWS_MINUTES: Final[tuple[int, ...]] = (360, 720, 1440)  # 6h, 12h, 24h
DEFAULT_LAGS_MINUTES: Final[tuple[int, ...]] = (0, 5, 10, 15, 30, 60)
CADENCE_MINUTES: Final[int] = 5


@dataclass(frozen=True)
class RainfallFeatureConfig:
    """Configuration for rainfall feature extraction."""

    rolling_windows_minutes: tuple[int, ...] = DEFAULT_ROLLING_WINDOWS_MINUTES
    antecedent_windows_minutes: tuple[int, ...] = DEFAULT_ANTECEDENT_WINDOWS_MINUTES
    lags_minutes: tuple[int, ...] = DEFAULT_LAGS_MINUTES
    min_coverage_ratio: float = 0.8
    cadence_minutes: int = CADENCE_MINUTES
    wet_threshold_mm: float = 0.0

    def __post_init__(self) -> None:
        if not self.rolling_windows_minutes or any(w <= 0 for w in self.rolling_windows_minutes):
            raise ValueError("rolling_windows_minutes must be positive integers")
        if not self.antecedent_windows_minutes or any(
            w <= 0 for w in self.antecedent_windows_minutes
        ):
            raise ValueError("antecedent_windows_minutes must be positive integers")
        if any(lag < 0 for lag in self.lags_minutes):
            raise ValueError("lags_minutes must be non-negative integers")
        if not (0.0 < self.min_coverage_ratio <= 1.0):
            raise ValueError("min_coverage_ratio must be in (0.0, 1.0]")
        if self.cadence_minutes <= 0:
            raise ValueError("cadence_minutes must be > 0")
        if self.wet_threshold_mm < 0:
            raise ValueError("wet_threshold_mm must be >= 0.0")


def _r(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), DECIMALS) + 0.0


def _t(row: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(row["observation_time_utc"])


def register_rainfall_features(
    config: RainfallFeatureConfig | None = None,
) -> list[FeatureDefinition]:
    """Register all rainfall features into the global registry."""
    cfg = config or RainfallFeatureConfig()
    defs: list[FeatureDefinition] = []

    cov_pct = int(cfg.min_coverage_ratio * 100)

    # 1. Rolling window features (Task 1)
    for w in cfg.rolling_windows_minutes:
        defs.append(
            FeatureDefinition(
                name=f"rf_roll_{w}m_sum_mm",
                family=FeatureFamily.RAINFALL_ROLLING,
                description=f"Trailing {w}-minute rainfall accumulation in (t - {w}m, t]",
                measurement_type=str(MEASUREMENT),
                unit="mm",
                lookback_minutes=w,
                min_coverage_ratio=cfg.min_coverage_ratio,
                null_semantics=f"Null when slot coverage in (t - {w}m, t] < {cov_pct}%",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t], includes t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )
        defs.append(
            FeatureDefinition(
                name=f"rf_roll_{w}m_max_mm",
                family=FeatureFamily.RAINFALL_ROLLING,
                description=f"Trailing {w}-minute maximum 5-min interval rainfall in (t - {w}m, t]",
                measurement_type=str(MEASUREMENT),
                unit="mm",
                lookback_minutes=w,
                min_coverage_ratio=cfg.min_coverage_ratio,
                null_semantics=f"Null when slot coverage in (t - {w}m, t] < {cov_pct}%",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t], includes t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )
        defs.append(
            FeatureDefinition(
                name=f"rf_roll_{w}m_wet_count",
                family=FeatureFamily.RAINFALL_ROLLING,
                description=f"Count of wet intervals (> {cfg.wet_threshold_mm}mm) in trailing {w}m",
                measurement_type=str(MEASUREMENT),
                unit="count",
                lookback_minutes=w,
                min_coverage_ratio=cfg.min_coverage_ratio,
                null_semantics=f"Null when slot coverage in (t - {w}m, t] < {cov_pct}%",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t], includes t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )
        defs.append(
            FeatureDefinition(
                name=f"rf_roll_{w}m_coverage_ratio",
                family=FeatureFamily.RAINFALL_ROLLING,
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
        defs.append(
            FeatureDefinition(
                name=f"rf_roll_{w}m_is_wet",
                family=FeatureFamily.RAINFALL_ROLLING,
                description=f"Binary indicator whether any rainfall occurred in trailing {w}m",
                measurement_type=str(MEASUREMENT),
                unit="unitless",
                lookback_minutes=w,
                min_coverage_ratio=cfg.min_coverage_ratio,
                null_semantics=f"Null when slot coverage in (t - {w}m, t] < {cov_pct}%",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t], includes t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )

    # Point-in-time: minutes since last wet interval
    defs.append(
        FeatureDefinition(
            name="rf_minutes_since_last_wet",
            family=FeatureFamily.RAINFALL_ROLLING,
            description="Minutes elapsed since the most recent wet interval at or before t",
            measurement_type=str(MEASUREMENT),
            unit="minutes",
            lookback_minutes=0,
            min_coverage_ratio=0.0,
            null_semantics="Null if no wet interval observed in preceding history for sensor",
            point_in_time_semantics="Strictly backward-looking <= t",
            leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
        )
    )

    # 2. Discrete lags & antecedent windows (Task 2)
    for lag in cfg.lags_minutes:
        defs.append(
            FeatureDefinition(
                name=f"rf_lag_{lag}m_mm",
                family=FeatureFamily.ANTECEDENT_RAINFALL,
                description=f"Discrete 5-min interval rainfall at exact instant t - {lag}m",
                measurement_type=str(MEASUREMENT),
                unit="mm",
                lookback_minutes=lag,
                min_coverage_ratio=1.0,
                null_semantics=f"Null if observation at exact instant t - {lag}m is missing",
                point_in_time_semantics=f"Point-in-time at instant t - {lag}m",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )

    for w in cfg.antecedent_windows_minutes:
        hours = w // 60
        defs.append(
            FeatureDefinition(
                name=f"rf_antecedent_{hours}h_sum_mm",
                family=FeatureFamily.ANTECEDENT_RAINFALL,
                description=f"Trailing {hours}h ({w}m) antecedent accumulation in (t - {w}m, t]",
                measurement_type=str(MEASUREMENT),
                unit="mm",
                lookback_minutes=w,
                min_coverage_ratio=cfg.min_coverage_ratio,
                null_semantics=f"Null when slot coverage in (t - {w}m, t] < {cov_pct}%",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t], includes t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )
        defs.append(
            FeatureDefinition(
                name=f"rf_antecedent_{hours}h_coverage_ratio",
                family=FeatureFamily.ANTECEDENT_RAINFALL,
                description=f"Slot coverage ratio in trailing {hours}-hour window",
                measurement_type=str(MEASUREMENT),
                unit="unitless",
                lookback_minutes=w,
                min_coverage_ratio=0.0,
                null_semantics="Always present (in [0.0, 1.0]) for evaluated prediction origin",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t]",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )
        defs.append(
            FeatureDefinition(
                name=f"rf_antecedent_{hours}h_wet_count",
                family=FeatureFamily.ANTECEDENT_RAINFALL,
                description=f"Count of wet intervals in trailing {hours}-hour window",
                measurement_type=str(MEASUREMENT),
                unit="count",
                lookback_minutes=w,
                min_coverage_ratio=cfg.min_coverage_ratio,
                null_semantics=f"Null when slot coverage in (t - {w}m, t] < {cov_pct}%",
                point_in_time_semantics=f"Strictly backward-looking (t - {w}m, t], includes t",
                leakage_classification=LeakageClassification.STRICT_POINT_IN_TIME,
            )
        )

    for d in defs:
        if not REGISTRY.contains(d.name):
            REGISTRY.register(d)
    return defs


# Register default definitions
register_rainfall_features()


def compute_rainfall_window_metrics(
    values: Sequence[float],
    expected_slots: int,
    min_coverage_ratio: float,
    wet_threshold_mm: float = 0.0,
) -> dict[str, Any]:
    """Compute rolling aggregation over a window given observed usable values."""
    usable_count = len(values)
    coverage_ratio = _r(usable_count / expected_slots) if expected_slots > 0 else 0.0
    assert coverage_ratio is not None

    if coverage_ratio < min_coverage_ratio or usable_count == 0:
        return {
            "sum_mm": None,
            "max_mm": None,
            "wet_count": None,
            "coverage_ratio": coverage_ratio,
            "is_wet": None,
        }

    total_sum = sum(values)
    max_val = max(values)
    wet_cnt = sum(1 for v in values if v > wet_threshold_mm)
    is_wet = 1 if total_sum > wet_threshold_mm else 0

    return {
        "sum_mm": _r(total_sum),
        "max_mm": _r(max_val),
        "wet_count": wet_cnt,
        "coverage_ratio": coverage_ratio,
        "is_wet": is_wet,
    }


def compute_rainfall_features_for_origin(
    origin_time: datetime,
    history_rows_by_time: Mapping[datetime, Mapping[str, Any]],
    sorted_history_times: Sequence[datetime],
    config: RainfallFeatureConfig,
) -> dict[str, Any]:
    """Extract all rainfall features for a single prediction origin instant t.

    LEAKAGE GUARD: Only observations at or before origin_time (t' <= origin_time) are used.
    """
    cfg = config
    features: dict[str, Any] = {}

    prior_times = [t for t in sorted_history_times if t <= origin_time]

    # 1. Rolling window features (Task 1)
    for w in cfg.rolling_windows_minutes:
        cutoff = origin_time - timedelta(minutes=w)
        window_times = [t for t in prior_times if cutoff < t <= origin_time]
        usable_values = [
            float(history_rows_by_time[t]["value"])
            for t in window_times
            if history_rows_by_time[t].get("usable") is True
            and history_rows_by_time[t].get("value") is not None
        ]
        expected_slots = w // cfg.cadence_minutes
        metrics = compute_rainfall_window_metrics(
            usable_values,
            expected_slots=expected_slots,
            min_coverage_ratio=cfg.min_coverage_ratio,
            wet_threshold_mm=cfg.wet_threshold_mm,
        )

        features[f"rf_roll_{w}m_sum_mm"] = metrics["sum_mm"]
        features[f"rf_roll_{w}m_max_mm"] = metrics["max_mm"]
        features[f"rf_roll_{w}m_wet_count"] = metrics["wet_count"]
        features[f"rf_roll_{w}m_coverage_ratio"] = metrics["coverage_ratio"]
        features[f"rf_roll_{w}m_is_wet"] = metrics["is_wet"]

    # Minutes since last wet interval
    last_wet_time: datetime | None = None
    for t in reversed(prior_times):
        r = history_rows_by_time[t]
        if (
            r.get("usable") is True
            and r.get("value") is not None
            and float(r["value"]) > cfg.wet_threshold_mm
        ):
            last_wet_time = t
            break

    if last_wet_time is not None:
        elapsed_min = (origin_time - last_wet_time).total_seconds() / 60.0
        features["rf_minutes_since_last_wet"] = _r(elapsed_min)
    else:
        features["rf_minutes_since_last_wet"] = None

    # 2. Discrete lag features (Task 2)
    for lag in cfg.lags_minutes:
        lag_time = origin_time - timedelta(minutes=lag)
        lag_row = history_rows_by_time.get(lag_time)
        if (
            lag_row is not None
            and lag_row.get("usable") is True
            and lag_row.get("value") is not None
        ):
            features[f"rf_lag_{lag}m_mm"] = _r(float(lag_row["value"]))
        else:
            features[f"rf_lag_{lag}m_mm"] = None

    # 3. Extended antecedent accumulation windows (Task 2)
    for w in cfg.antecedent_windows_minutes:
        hours = w // 60
        cutoff = origin_time - timedelta(minutes=w)
        window_times = [t for t in prior_times if cutoff < t <= origin_time]
        usable_values = [
            float(history_rows_by_time[t]["value"])
            for t in window_times
            if history_rows_by_time[t].get("usable") is True
            and history_rows_by_time[t].get("value") is not None
        ]
        expected_slots = w // cfg.cadence_minutes
        metrics = compute_rainfall_window_metrics(
            usable_values,
            expected_slots=expected_slots,
            min_coverage_ratio=cfg.min_coverage_ratio,
            wet_threshold_mm=cfg.wet_threshold_mm,
        )

        features[f"rf_antecedent_{hours}h_sum_mm"] = metrics["sum_mm"]
        features[f"rf_antecedent_{hours}h_coverage_ratio"] = metrics["coverage_ratio"]
        features[f"rf_antecedent_{hours}h_wet_count"] = metrics["wet_count"]

    return features


def extract_rainfall_features(
    rows: Iterable[Mapping[str, Any]],
    *,
    config: RainfallFeatureConfig | None = None,
) -> list[dict[str, Any]]:
    """Extract point-in-time rainfall features for all usable observation origins."""
    cfg = config or RainfallFeatureConfig()
    selected, _ = select_measurement(
        rows,
        measurement_type=MEASUREMENT,
        unit=UNIT,
        sensor_type=SensorType.RAINFALL,
        value_ok=lambda v: True,
        value_rule="rainfall must be finite",
    )

    if not selected:
        return []

    by_sensor: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in selected:
        by_sensor[r["fg_sensor_id"]].append(r)

    all_origin_features: list[dict[str, Any]] = []

    for sensor_id, sensor_rows in sorted(by_sensor.items()):
        ordered = sorted(sensor_rows, key=_t)
        history_rows_by_time = {_t(r): r for r in ordered}
        sorted_times = sorted(history_rows_by_time.keys())

        for r in ordered:
            if not r.get("usable"):
                continue
            origin_t = _t(r)
            rf_feats = compute_rainfall_features_for_origin(
                origin_t,
                history_rows_by_time,
                sorted_times,
                cfg,
            )
            entry = {
                "source": r["source"],
                "fg_sensor_id": sensor_id,
                "fg_site_id": r["fg_site_id"],
                "prediction_origin_utc": r["observation_time_utc"],
                "prediction_origin_local": r["observation_time_local"],
                **rf_feats,
            }
            all_origin_features.append(entry)

    return all_origin_features
