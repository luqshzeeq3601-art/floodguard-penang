"""Train-only scaling for forecasting (per-station, never global).

Gauge datums differ by station, so scaling is per ``fg_sensor_id`` and fit on
training origins only; the frozen scaler applies unchanged to validation and
test. A global scaler across stations is explicitly unsupported in Phase 6
(it would mix incomparable datums). Unseen stations at inference are
rejected with a structured error, never silently pooled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

PREPROCESSING_SCHEMA_VERSION: Final[str] = "forecast_preprocessing/v1"


@dataclass(frozen=True)
class StationScaler:
    """Frozen per-station mean/std (fit on training origins only)."""

    fg_sensor_id: str
    mean_m: float
    std_m: float

    def transform(self, value: float) -> float:
        return (value - self.mean_m) / self.std_m

    def inverse(self, value: float) -> float:
        return value * self.std_m + self.mean_m

    def to_dict(self) -> dict[str, Any]:
        return {
            "fg_sensor_id": self.fg_sensor_id,
            "mean_m": self.mean_m,
            "std_m": self.std_m,
        }


@dataclass
class ForecastPreprocessor:
    """Per-station scalers fitted on training samples only."""

    scalers: dict[str, StationScaler]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PREPROCESSING_SCHEMA_VERSION,
            "scalers": {k: v.to_dict() for k, v in sorted(self.scalers.items())},
        }


def fit_preprocessor(train_levels_by_station: dict[str, list[float]]) -> ForecastPreprocessor:
    """Fit one scaler per station on training levels only."""
    scalers: dict[str, StationScaler] = {}
    for sensor_id in sorted(train_levels_by_station):
        values = train_levels_by_station[sensor_id]
        if not values:
            raise ValueError(f"station {sensor_id}: no training levels")
        mean = sum(values) / len(values)
        var = sum((v - mean) ** 2 for v in values) / len(values)
        std = var**0.5 if var > 0 else 1.0
        scalers[sensor_id] = StationScaler(
            fg_sensor_id=sensor_id, mean_m=mean, std_m=std if std > 0 else 1.0
        )
    return ForecastPreprocessor(scalers=scalers)


def require_station(preprocessor: ForecastPreprocessor, sensor_id: str) -> StationScaler:
    """Fetch a station scaler; unseen stations are rejected, never pooled."""
    scaler = preprocessor.scalers.get(sensor_id)
    if scaler is None:
        raise ValueError(
            f"unseen station {sensor_id!r}: no training scaler; refusing to pool datums"
        )
    return scaler
