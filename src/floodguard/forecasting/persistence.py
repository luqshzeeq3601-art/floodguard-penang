"""Forecasting persistence baseline (Phase 6 task 1).

``predicted_water_level(t+h) = water_level(t)`` evaluated independently per
horizon (+30/+60/+120) and per station. Origins need a valid point-in-time
level and an exact usable target at the required horizon (built by
``forecasting.dataset``); anything else is excluded and counted, never
interpolated. Stations are never pooled: per-station metrics are primary;
any overall metric states its sample weighting explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from floodguard.forecasting import (
    EVIDENCE_SYNTHETIC,
    HORIZONS_MINUTES,
    NOT_EVALUABLE,
)
from floodguard.forecasting.dataset import ForecastSample

PERSISTENCE_SCHEMA_VERSION: Final[str] = "forecast_persistence/v1"


@dataclass(frozen=True)
class StationHorizonScore:
    """Persistence score for one station and horizon."""

    fg_sensor_id: str
    horizon_minutes: int
    n: int
    mae_m: float | str
    rmse_m: float | str
    bias_m: float | str
    evidence_level: str = EVIDENCE_SYNTHETIC

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PERSISTENCE_SCHEMA_VERSION,
            "fg_sensor_id": self.fg_sensor_id,
            "horizon_minutes": self.horizon_minutes,
            "n": self.n,
            "mae_m": self.mae_m,
            "rmse_m": self.rmse_m,
            "bias_m": self.bias_m,
            "evidence_level": self.evidence_level,
        }


def _mean(values: list[float]) -> float | str:
    if not values:
        return NOT_EVALUABLE
    return sum(values) / len(values)


def score_station_horizon(
    samples: list[ForecastSample],
    horizon_minutes: int,
    *,
    evidence_level: str = EVIDENCE_SYNTHETIC,
) -> StationHorizonScore:
    """Score persistence on one station's samples for one horizon."""
    if horizon_minutes not in HORIZONS_MINUTES:
        raise ValueError(f"unsupported horizon: {horizon_minutes}")
    relevant = [s for s in samples if s.horizon_minutes == horizon_minutes]
    if not relevant:
        return StationHorizonScore(
            fg_sensor_id=samples[0].fg_sensor_id if samples else "unknown",
            horizon_minutes=horizon_minutes,
            n=0,
            mae_m=NOT_EVALUABLE,
            rmse_m=NOT_EVALUABLE,
            bias_m=NOT_EVALUABLE,
            evidence_level=evidence_level,
        )
    sensor = relevant[0].fg_sensor_id
    errors = [s.origin_level_m - s.target_level_m for s in relevant]
    mae = _mean([abs(e) for e in errors])
    mse = _mean([e * e for e in errors])
    rmse: float | str
    if isinstance(mse, str):
        rmse = NOT_EVALUABLE
    else:
        import math

        rmse = math.sqrt(mse)
    return StationHorizonScore(
        fg_sensor_id=sensor,
        horizon_minutes=horizon_minutes,
        n=len(relevant),
        mae_m=mae,
        rmse_m=rmse,
        bias_m=_mean(errors),
        evidence_level=evidence_level,
    )


def score_all_stations(
    per_horizon: dict[int, list[ForecastSample]],
    *,
    evidence_level: str = EVIDENCE_SYNTHETIC,
) -> dict[str, Any]:
    """Per-station scores plus an explicitly sample-weighted overall summary."""
    stations: dict[str, dict[str, Any]] = {}
    for horizon, samples in per_horizon.items():
        by_sensor: dict[str, list[ForecastSample]] = {}
        for sample in samples:
            by_sensor.setdefault(sample.fg_sensor_id, []).append(sample)
        for sensor_id in sorted(by_sensor):
            entry = score_station_horizon(
                by_sensor[sensor_id], horizon, evidence_level=evidence_level
            )
            stations.setdefault(sensor_id, {})[str(horizon)] = entry.to_dict()

    overall: dict[str, Any] = {}
    for horizon in HORIZONS_MINUTES:
        scored = [
            score_station_horizon(
                [s for s in per_horizon.get(horizon, []) if s.fg_sensor_id == sid],
                horizon,
                evidence_level=evidence_level,
            )
            for sid in stations
        ]
        scored = [s for s in scored if s.n > 0 and not isinstance(s.mae_m, str)]
        total = sum(s.n for s in scored)
        if not total:
            overall[str(horizon)] = {
                "n": 0,
                "mae_m": NOT_EVALUABLE,
                "rmse_m": NOT_EVALUABLE,
                "weighting": "sample-weighted mean across stations (no evaluable samples)",
            }
            continue
        mae = sum(float(s.mae_m) * s.n for s in scored) / total
        rmse = sum(float(s.rmse_m) * s.n for s in scored) / total
        overall[str(horizon)] = {
            "n": total,
            "mae_m": mae,
            "rmse_m": rmse,
            "rmse_aggregation": "mean of station RMSEs (not pooled RMSE)",
            "weighting": "sample-weighted mean across stations; per-station results primary",
            "stations": len(scored),
        }
    return {
        "schema_version": PERSISTENCE_SCHEMA_VERSION,
        "per_station": stations,
        "overall": overall,
        "evidence_level": evidence_level,
    }
