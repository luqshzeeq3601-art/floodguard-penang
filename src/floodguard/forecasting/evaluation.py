"""Horizon-specific forecast evaluation (Phase 6 task 6): MAE/RMSE + skill.

- Each horizon (+30/+60/+120) evaluated independently; never pooled.
- Per-station metrics primary (datums differ); overall metrics state their
  sample weighting explicitly.
- Persistence skill: ``skill = 1 - model_MAE / persistence_MAE`` iff the
  denominator is positive; otherwise UNDEFINED (never divide by zero).
- No MAPE (levels can approach zero or go negative).
- Eligibility gate: same dataset/version, target, horizon, split and period,
  plus minimum target counts and station coverage; otherwise
  ``NO_ELIGIBLE_FORECAST_MODEL``. No champion on one or two station-days.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

from floodguard.forecasting import (
    EVIDENCE_SYNTHETIC,
    HORIZONS_MINUTES,
    NO_ELIGIBLE_FORECAST_MODEL,
    NOT_EVALUABLE,
)

EVALUATION_SCHEMA_VERSION: Final[str] = "forecast_evaluation/v1"


@dataclass(frozen=True)
class HorizonScore:
    """One model on one station and horizon."""

    fg_sensor_id: str
    model_family: str
    horizon_minutes: int
    n: int
    mae_m: float | str
    rmse_m: float | str
    bias_m: float | str
    evidence_level: str = EVIDENCE_SYNTHETIC

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "fg_sensor_id": self.fg_sensor_id,
            "model_family": self.model_family,
            "horizon_minutes": self.horizon_minutes,
            "n": self.n,
            "mae_m": self.mae_m,
            "rmse_m": self.rmse_m,
            "bias_m": self.bias_m,
            "evidence_level": self.evidence_level,
        }


def score_predictions(
    y_true_m: list[float],
    y_pred_m: list[float],
    *,
    fg_sensor_id: str,
    model_family: str,
    horizon_minutes: int,
    evidence_level: str = EVIDENCE_SYNTHETIC,
) -> HorizonScore:
    """MAE/RMSE/bias for one station and horizon (empty → NOT_EVALUABLE)."""
    if horizon_minutes not in HORIZONS_MINUTES:
        raise ValueError(f"unsupported horizon: {horizon_minutes}")
    if len(y_true_m) != len(y_pred_m):
        raise ValueError("y_true_m and y_pred_m must have equal length")
    if not y_true_m:
        return HorizonScore(
            fg_sensor_id=fg_sensor_id,
            model_family=model_family,
            horizon_minutes=horizon_minutes,
            n=0,
            mae_m=NOT_EVALUABLE,
            rmse_m=NOT_EVALUABLE,
            bias_m=NOT_EVALUABLE,
            evidence_level=evidence_level,
        )
    errors = [p - a for a, p in zip(y_true_m, y_pred_m, strict=True)]
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    bias = sum(errors) / len(errors)
    return HorizonScore(
        fg_sensor_id=fg_sensor_id,
        model_family=model_family,
        horizon_minutes=horizon_minutes,
        n=len(y_true_m),
        mae_m=mae,
        rmse_m=rmse,
        bias_m=bias,
        evidence_level=evidence_level,
    )


def persistence_skill(model_mae_m: float | str, persistence_mae_m: float | str) -> float | str:
    """MAE skill vs persistence; UNDEFINED when the denominator is not positive."""
    if isinstance(model_mae_m, str) or isinstance(persistence_mae_m, str):
        return NOT_EVALUABLE
    if persistence_mae_m <= 0:
        return NOT_EVALUABLE
    return 1.0 - model_mae_m / persistence_mae_m


@dataclass(frozen=True)
class EligibilityConfig:
    """Minimum real evidence for forecast-model selection."""

    min_targets_per_horizon: int = 30
    min_stations: int = 2
    min_covered_days_per_station: int = 30

    def __post_init__(self) -> None:
        if self.min_targets_per_horizon < 1:
            raise ValueError("min_targets_per_horizon must be >= 1")


@dataclass(frozen=True)
class CandidateRun:
    """One evaluated forecasting run with comparability identity."""

    dataset_version: str
    sequence_config: str
    target_definition: str
    horizon_minutes: int
    split_definition: str
    evaluation_period: str
    model_family: str
    run_id: str
    n_targets: int
    stations: int
    stations_meeting_coverage: int
    mae_m: float | str

    def comparability_key(self) -> tuple[str, ...]:
        return (
            self.dataset_version,
            self.sequence_config,
            self.target_definition,
            str(self.horizon_minutes),
            self.split_definition,
            self.evaluation_period,
        )


def select_forecast_candidate(
    runs: list[CandidateRun],
    *,
    config: EligibilityConfig | None = None,
) -> dict[str, Any]:
    """Select a forecasting candidate only with sufficient real evidence."""
    cfg = config or EligibilityConfig()
    if not runs:
        return {
            "status": NO_ELIGIBLE_FORECAST_MODEL,
            "reason": "no runs to compare.",
            "schema_version": EVALUATION_SCHEMA_VERSION,
        }
    keys = {r.comparability_key() for r in runs}
    if len(keys) != 1:
        return {
            "status": NO_ELIGIBLE_FORECAST_MODEL,
            "reason": f"runs span {len(keys)} distinct evaluation contexts; not comparable.",
            "schema_version": EVALUATION_SCHEMA_VERSION,
        }
    eligible = [
        r
        for r in runs
        if r.n_targets >= cfg.min_targets_per_horizon
        and r.stations >= cfg.min_stations
        and r.stations_meeting_coverage >= cfg.min_stations
        and not isinstance(r.mae_m, str)
    ]
    if not eligible:
        return {
            "status": NO_ELIGIBLE_FORECAST_MODEL,
            "reason": (
                "no candidate meets minimum real evidence "
                f"(>= {cfg.min_targets_per_horizon} targets, >= {cfg.min_stations} "
                f"stations with >= {cfg.min_covered_days_per_station} covered days); "
                "NO PHASE 6 MODEL HAS BEEN VALIDATED AS A "
                "GENERALIZABLE PENANG WATER-LEVEL FORECASTER."
            ),
            "schema_version": EVALUATION_SCHEMA_VERSION,
            "n_runs": len(runs),
        }
    champion = min(eligible, key=lambda r: (float(r.mae_m), r.run_id))
    return {
        "status": "CANDIDATE_SELECTED",
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "champion_run_id": champion.run_id,
        "champion_model_family": champion.model_family,
        "n_runs": len(runs),
        "n_eligible": len(eligible),
    }
