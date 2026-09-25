"""Random Forest baseline (Phase 5 task 3).

- Deterministic ``random_state``; small default forest for synthetic tests.
- Chronological split semantics preserved by callers; this module never sees
  validation/test data during fitting.
- Validation/test data never determine preprocessing or hyperparameters.
- Feature importance is reported as contribution, never causality.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final

from sklearn.ensemble import RandomForestClassifier  # type: ignore[import-untyped]

from floodguard.modeling.logistic import InfeasibleTraining, check_binary_support

FOREST_SCHEMA_VERSION: Final[str] = "random_forest/v1"
MODEL_FAMILY: Final[str] = "random_forest"


@dataclass(frozen=True)
class ForestConfig:
    """Deterministic Random Forest configuration."""

    n_estimators: int = 100
    max_depth: int | None = None
    min_samples_leaf: int = 1
    random_state: int = 42
    class_weight: str | None = None  # None | "balanced" | "balanced_subsample"

    def __post_init__(self) -> None:
        if self.n_estimators < 1:
            raise ValueError("n_estimators must be >= 1")
        if self.min_samples_leaf < 1:
            raise ValueError("min_samples_leaf must be >= 1")
        if self.class_weight not in (None, "balanced", "balanced_subsample"):
            raise ValueError("invalid class_weight")


def train_forest(
    x_train: list[list[float]],
    y_train: list[int],
    config: ForestConfig | None = None,
    *,
    horizon_minutes: int = 30,
) -> tuple[Any, dict[str, Any] | InfeasibleTraining]:
    """Train a deterministic Random Forest on CPU."""
    cfg = config or ForestConfig()
    blocked = check_binary_support(y_train, horizon_minutes)
    if blocked is not None:
        return None, InfeasibleTraining(
            status=blocked.status, reason=blocked.reason, horizon_minutes=horizon_minutes
        )
    if not x_train:
        return None, InfeasibleTraining(
            status="INFEASIBLE_NO_ROWS",
            reason="empty training matrix.",
            horizon_minutes=horizon_minutes,
        )
    estimator = RandomForestClassifier(
        n_estimators=cfg.n_estimators,
        max_depth=cfg.max_depth,
        min_samples_leaf=cfg.min_samples_leaf,
        random_state=cfg.random_state,
        class_weight=cfg.class_weight,
        n_jobs=1,
    )
    estimator.fit(x_train, y_train)
    metadata: dict[str, Any] = {
        "schema_version": FOREST_SCHEMA_VERSION,
        "model_family": MODEL_FAMILY,
        "horizon_minutes": horizon_minutes,
        "config": asdict(cfg),
        "n_train": len(y_train),
        "n_features": len(x_train[0]) if x_train else 0,
        "device": "cpu",
        "library": "scikit-learn",
    }
    return estimator, metadata
