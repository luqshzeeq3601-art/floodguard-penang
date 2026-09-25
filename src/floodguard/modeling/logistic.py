"""Logistic Regression baseline (Phase 5 task 2).

- Scaling/imputation owned by FittedPreprocessor (fit on training only);
  this module fits the classifier only, with no second scaler (review L2).
- Missing numerics use training medians (via FittedPreprocessor).
- Deterministic configuration (fixed random_state, fixed solver).
- Class weighting from training data only, and only when both classes exist.
- Single-class training partitions raise a structured infeasibility result
  instead of fitting a meaningless binary classifier.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final

from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]

LOGISTIC_SCHEMA_VERSION: Final[str] = "logistic/v1"
MODEL_FAMILY: Final[str] = "logistic_regression"


@dataclass(frozen=True)
class LogisticConfig:
    """Deterministic Logistic Regression configuration."""

    c: float = 1.0
    max_iter: int = 1000
    random_state: int = 42
    class_weight: str | None = None  # None | "balanced" (training-only)

    def __post_init__(self) -> None:
        if not self.c > 0:
            raise ValueError("C must be > 0")
        if self.max_iter < 1:
            raise ValueError("max_iter must be >= 1")
        if self.class_weight not in (None, "balanced"):
            raise ValueError("class_weight must be None or 'balanced'")


@dataclass(frozen=True)
class InfeasibleTraining:
    """Structured infeasibility instead of a meaningless fit."""

    status: str
    reason: str
    horizon_minutes: int
    model_family: str = MODEL_FAMILY

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "horizon_minutes": self.horizon_minutes,
            "model_family": self.model_family,
        }


def check_binary_support(y_train: list[int], horizon_minutes: int) -> InfeasibleTraining | None:
    """Return infeasibility when training has zero positives or zero negatives."""
    positives = sum(y_train)
    negatives = len(y_train) - positives
    if positives == 0:
        return InfeasibleTraining(
            status="INFEASIBLE_SINGLE_CLASS",
            reason=(f"horizon +{horizon_minutes}m training has 0 positives; refuse to fit."),
            horizon_minutes=horizon_minutes,
        )
    if negatives == 0:
        return InfeasibleTraining(
            status="INFEASIBLE_SINGLE_CLASS",
            reason=(f"horizon +{horizon_minutes}m training has 0 negatives; refuse to fit."),
            horizon_minutes=horizon_minutes,
        )
    return None


def train_logistic(
    x_train: list[list[float]],
    y_train: list[int],
    config: LogisticConfig | None = None,
    *,
    horizon_minutes: int = 30,
) -> tuple[Any, dict[str, Any] | InfeasibleTraining]:
    """Train a deterministic Logistic Regression (CPU)."""
    cfg = config or LogisticConfig()
    blocked = check_binary_support(y_train, horizon_minutes)
    if blocked is not None:
        return None, blocked
    if not x_train:
        return None, InfeasibleTraining(
            status="INFEASIBLE_NO_ROWS",
            reason="empty training matrix.",
            horizon_minutes=horizon_minutes,
        )
    class_weight = "balanced" if cfg.class_weight == "balanced" else None
    estimator = LogisticRegression(
        C=cfg.c,
        max_iter=cfg.max_iter,
        random_state=cfg.random_state,
        class_weight=class_weight,
        solver="lbfgs",
    )
    estimator.fit(x_train, y_train)
    metadata: dict[str, Any] = {
        "schema_version": LOGISTIC_SCHEMA_VERSION,
        "model_family": MODEL_FAMILY,
        "horizon_minutes": horizon_minutes,
        "config": asdict(cfg),
        "n_train": len(y_train),
        "n_features": len(x_train[0]) if x_train else 0,
        "device": "cpu",
        "library": "scikit-learn",
    }
    return estimator, metadata
