"""Live inference pipeline (Phase 10, Task 6).

MLOps status is ``NO_ELIGIBLE_MODEL`` / ``NO_ELIGIBLE_FORECAST_MODEL`` (Phase 5/6
evidence: zero positive flood-proxy events; no validated forecaster). This
module implements the explicit no-model path so live ingestion stores
observations and updates dashboards WITHOUT predictions.

- Never invokes a nonexistent production model.
- Never substitutes a synthetic model.
- Returns ``SKIPPED_NO_ELIGIBLE_MODEL`` with lineage for every horizon.
- Architecture preserves the call site for a future eligible model (registry
  check first), but the gate stays closed on current evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Final

HORIZONS: Final[tuple[int, ...]] = (30, 60, 120)
SKIPPED_NO_MODEL: Final[str] = "SKIPPED_NO_ELIGIBLE_MODEL"
NO_MODEL: Final[str] = "NO_ELIGIBLE_MODEL"
NO_FORECAST_MODEL: Final[str] = "NO_ELIGIBLE_FORECAST_MODEL"
INFERENCE_SCHEMA_VERSION: Final[str] = "live_inference/v1"


class InferenceStatus(StrEnum):
    SKIPPED_NO_ELIGIBLE_MODEL = "SKIPPED_NO_ELIGIBLE_MODEL"
    PREDICTED = "PREDICTED"


@dataclass(frozen=True)
class HorizonOutcome:
    horizon_minutes: int
    status: InferenceStatus
    reason: str


@dataclass(frozen=True)
class LiveInferenceResult:
    run_id: str
    sensor_id: str
    origin_utc: str
    horizons: tuple[HorizonOutcome, ...]
    predictions: tuple[Mapping[str, Any], ...] = ()
    schema_version: str = INFERENCE_SCHEMA_VERSION


def check_model_eligibility(registry_state: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Current MLOps gate (closed on present evidence; registry-aware when supplied)."""
    state = dict(registry_state or {})
    production = state.get("production_model")
    if isinstance(production, str) and production:
        # A future eligible production model would be invoked here; none exists.
        return {"classification": NO_MODEL, "forecast": NO_FORECAST_MODEL}
    return {"classification": NO_MODEL, "forecast": NO_FORECAST_MODEL}


def run_live_inference(
    *,
    run_id: str,
    sensor_id: str,
    origin_utc: datetime,
    horizons: Sequence[int] = HORIZONS,
    registry_state: Mapping[str, Any] | None = None,
) -> LiveInferenceResult:
    """No-model path: record the skip per horizon, persist nothing."""
    eligibility = check_model_eligibility(registry_state)
    _ = eligibility
    origin = origin_utc if origin_utc.tzinfo is not None else origin_utc.replace(tzinfo=UTC)
    outcomes = tuple(
        HorizonOutcome(
            h,
            InferenceStatus.SKIPPED_NO_ELIGIBLE_MODEL,
            f"{SKIPPED_NO_MODEL}: {NO_MODEL}/{NO_FORECAST_MODEL}; "
            "observations stored without predictions",
        )
        for h in horizons
    )
    return LiveInferenceResult(
        run_id=run_id,
        sensor_id=sensor_id,
        origin_utc=origin.astimezone(UTC).isoformat(),
        horizons=outcomes,
        predictions=(),
    )


@dataclass
class InferenceCollector:
    """Counts inference skips vs predictions (factual, no performance claims)."""

    skipped: int = 0
    predicted: int = 0
    by_horizon: dict[int, dict[str, int]] = field(default_factory=dict)

    def record(self, result: LiveInferenceResult) -> None:
        for h in result.horizons:
            bucket = self.by_horizon.setdefault(h.horizon_minutes, {"skipped": 0, "predicted": 0})
            if h.status is InferenceStatus.SKIPPED_NO_ELIGIBLE_MODEL:
                self.skipped += 1
                bucket["skipped"] += 1
            else:
                self.predicted += 1
                bucket["predicted"] += 1
