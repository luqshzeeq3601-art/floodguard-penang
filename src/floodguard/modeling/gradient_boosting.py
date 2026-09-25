"""XGBoost gradient-boosting candidate (Phase 5 task 4: XGBoost/LightGBM).

Only XGBoost is implemented (the TASKS.md entry is ``XGBoost/LightGBM``,
singular: one representative gradient-boosting family). LightGBM is
intentionally not added to keep dependencies minimal.

- CPU execution is the default (``tree_method="hist"``, ``device="cpu"``).
- GPU benchmarking is out of scope for Phase 5: the modeling bottleneck is
  data/event availability, not compute. No CUDA/GPU code path is required
  for normal tests or operation.
- Deterministic seed; small defaults for synthetic tests.
- Single-class training returns structured infeasibility (no meaningless fit).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final

from floodguard.modeling.logistic import InfeasibleTraining, check_binary_support

GBM_SCHEMA_VERSION: Final[str] = "xgboost/v1"
MODEL_FAMILY: Final[str] = "xgboost"
XGBOOST_VERSION: Final[str] = "3.2.0"


@dataclass(frozen=True)
class GradientBoostingConfig:
    """Deterministic CPU XGBoost configuration."""

    n_estimators: int = 100
    max_depth: int = 3
    learning_rate: float = 0.1
    subsample: float = 1.0
    colsample_bytree: float = 1.0
    min_child_weight: float = 1.0
    reg_lambda: float = 1.0
    random_state: int = 42
    n_jobs: int = 1
    device: str = "cpu"

    def __post_init__(self) -> None:
        if self.n_estimators < 1:
            raise ValueError("n_estimators must be >= 1")
        if self.max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        if not 0.0 < self.learning_rate <= 1.0:
            raise ValueError("learning_rate must be in (0, 1]")
        if not 0.0 < self.subsample <= 1.0:
            raise ValueError("subsample must be in (0, 1]")
        if self.device != "cpu":
            raise ValueError("Phase 5 XGBoost device must be 'cpu'")


def train_gradient_boosting(
    x_train: list[list[float]],
    y_train: list[int],
    config: GradientBoostingConfig | None = None,
    *,
    horizon_minutes: int = 30,
) -> tuple[Any, dict[str, Any] | InfeasibleTraining]:
    """Train a deterministic CPU XGBoost classifier."""
    cfg = config or GradientBoostingConfig()
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
    try:
        from xgboost import XGBClassifier
    except ImportError as exc:
        return None, InfeasibleTraining(
            status="INFEASIBLE_MISSING_DEPENDENCY",
            reason=f"xgboost is not installed: {exc}",
            horizon_minutes=horizon_minutes,
        )
    estimator = XGBClassifier(
        n_estimators=cfg.n_estimators,
        max_depth=cfg.max_depth,
        learning_rate=cfg.learning_rate,
        subsample=cfg.subsample,
        colsample_bytree=cfg.colsample_bytree,
        min_child_weight=cfg.min_child_weight,
        reg_lambda=cfg.reg_lambda,
        random_state=cfg.random_state,
        n_jobs=cfg.n_jobs,
        tree_method="hist",
        device="cpu",
        eval_metric="logloss",
    )
    estimator.fit(x_train, y_train)
    metadata: dict[str, Any] = {
        "schema_version": GBM_SCHEMA_VERSION,
        "model_family": MODEL_FAMILY,
        "horizon_minutes": horizon_minutes,
        "config": asdict(cfg),
        "n_train": len(y_train),
        "n_features": len(x_train[0]) if x_train else 0,
        "device": "cpu",
        "library": f"xgboost=={XGBOOST_VERSION}",
    }
    return estimator, metadata
