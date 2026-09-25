"""Persistence and rule baselines (Phase 5 task 1).

Persistence regression: predicted WL(t+h) = WL(t), evaluated independently
per horizon (+30, +60, +120). Missing future targets are excluded, never
zero-filled. The origin at t must be usable and point-in-time available.

Rule classifier: uses only information available at or before origin t
(current level, backward rise rate, trailing rainfall features, legitimate
static station metadata). It never inspects WL(t+h). Threshold distances may
be used only when ``allow_threshold_reference`` is explicitly True, and then
only as CURRENT_THRESHOLD_REFERENCE_ONLY inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from floodguard.modeling import HORIZONS_MINUTES, MISSING_FUTURE_TARGET, TARGET_EVALUATED

BASELINES_SCHEMA_VERSION: Final[str] = "baselines/v1"


@dataclass(frozen=True)
class PersistenceResult:
    """Persistence forecast for one origin and horizon."""

    origin_utc: str
    horizon_minutes: int
    origin_level_m: float | None
    predicted_level_m: float | None
    actual_level_m: float | None
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin_utc": self.origin_utc,
            "horizon_minutes": self.horizon_minutes,
            "origin_level_m": self.origin_level_m,
            "predicted_level_m": self.predicted_level_m,
            "actual_level_m": self.actual_level_m,
            "status": self.status,
        }


def persistence_forecast_for_row(
    joined_row: dict[str, Any], horizon_minutes: int
) -> PersistenceResult:
    """Persistence forecast predicted WL(t+h) = WL(t) for one joined row."""
    if horizon_minutes not in HORIZONS_MINUTES:
        raise ValueError(f"unsupported horizon: {horizon_minutes}")
    origin_utc = str(joined_row.get("prediction_origin_utc", ""))
    origin_level = joined_row.get("wl_level_m")
    status = joined_row.get(f"target_plus_{horizon_minutes}m_status")
    actual = joined_row.get(f"target_plus_{horizon_minutes}m_future_level_m")
    if origin_level is None:
        return PersistenceResult(
            origin_utc=origin_utc,
            horizon_minutes=horizon_minutes,
            origin_level_m=None,
            predicted_level_m=None,
            actual_level_m=None,
            status=MISSING_FUTURE_TARGET,
        )
    if status != TARGET_EVALUATED or actual is None:
        return PersistenceResult(
            origin_utc=origin_utc,
            horizon_minutes=horizon_minutes,
            origin_level_m=float(origin_level),
            predicted_level_m=float(origin_level),
            actual_level_m=None,
            status=MISSING_FUTURE_TARGET,
        )
    return PersistenceResult(
        origin_utc=origin_utc,
        horizon_minutes=horizon_minutes,
        origin_level_m=float(origin_level),
        predicted_level_m=float(origin_level),
        actual_level_m=float(str(actual)),
        status=TARGET_EVALUATED,
    )


@dataclass(frozen=True)
class RuleConfig:
    """Deterministic rule-classifier configuration (all point-in-time)."""

    rise_rate_threshold_m_per_h: float = 0.30
    rainfall_sum_threshold_mm: float = 10.0
    rainfall_feature: str = "rf_roll_60m_sum_mm"
    rate_feature: str = "wl_rate_30m_m_per_h"
    allow_threshold_reference: bool = False

    def __post_init__(self) -> None:
        if self.rise_rate_threshold_m_per_h < 0:
            raise ValueError("rise_rate_threshold_m_per_h must be >= 0")
        if self.rainfall_sum_threshold_mm < 0:
            raise ValueError("rainfall_sum_threshold_mm must be >= 0")


def rule_predict_row(feature_row: dict[str, Any], config: RuleConfig | None = None) -> int | None:
    """Rule prediction from origin-t features only (1/0/None when unevaluable).

    Fires when EITHER the backward rise rate OR the trailing rainfall sum
    exceeds its configured threshold. Returns None when both driving
    features are missing (never guess).
    """
    cfg = config or RuleConfig()
    rate = feature_row.get(cfg.rate_feature)
    rainfall = feature_row.get(cfg.rainfall_feature)
    triggers: list[bool] = []
    if isinstance(rate, (int, float)):
        triggers.append(float(rate) >= cfg.rise_rate_threshold_m_per_h)
    if isinstance(rainfall, (int, float)):
        triggers.append(float(rainfall) >= cfg.rainfall_sum_threshold_mm)
    if cfg.allow_threshold_reference:
        # Threshold distances are CURRENT_THRESHOLD_REFERENCE_ONLY inputs:
        # they describe proximity at origin t, never the future outcome.
        dist = feature_row.get("wl_dist_to_waspada_m")
        if isinstance(dist, (int, float)) and float(dist) >= 0:
            triggers.append(True)
    if not triggers:
        return None
    return 1 if any(triggers) else 0


def rule_predict_proba_row(
    feature_row: dict[str, Any], config: RuleConfig | None = None
) -> float | None:
    """Deterministic rule score in {0.0, 1.0} for PR-AUC plumbing."""
    label = rule_predict_row(feature_row, config)
    return None if label is None else float(label)
