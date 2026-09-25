"""Gradient-boosting regression with lag features (Phase 6 task 3).

Per-station XGBoost regressors over exact lag levels plus backward deltas.
CPU only (``tree_method="hist"``, ``device="cpu"``; non-CPU rejected).
Deterministic seed; small defaults for synthetic tests. Fitted on training
origins only. No LightGBM (same single-family policy as Phase 5).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import pairwise
from typing import Any, Final

GBM_SCHEMA_VERSION: Final[str] = "forecast_gbm/v1"
MODEL_FAMILY: Final[str] = "xgboost_regressor"
XGBOOST_VERSION: Final[str] = "3.2.0"


@dataclass(frozen=True)
class GradientBoostingConfig:
    """Deterministic CPU XGBoost regression configuration."""

    n_estimators: int = 100
    max_depth: int = 3
    learning_rate: float = 0.1
    subsample: float = 1.0
    colsample_bytree: float = 1.0
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
            raise ValueError("Phase 6 XGBoost device must be 'cpu'")


def lag_delta_feature_names(lag_offsets: tuple[int, ...]) -> list[str]:
    """Lag levels plus consecutive backward deltas (deterministic order)."""
    names = [f"wl_lag_{lag}m_m" for lag in lag_offsets]
    names.extend(f"wl_delta_lag_{b}m_minus_{a}m_m" for a, b in pairwise(lag_offsets))
    return names


def build_lag_delta_matrix(
    levels_by_time: dict[str, float],
    ordered_times: list[str],
    lag_offsets: tuple[int, ...],
) -> tuple[list[list[float]], list[str]]:
    """Lag + delta rows for origins with a complete lag set (no fill)."""
    from datetime import datetime as _datetime
    from datetime import timedelta as _timedelta

    matrix: list[list[float]] = []
    origins: list[str] = []
    for origin in ordered_times:
        base = _datetime.fromisoformat(origin)
        lags: list[float] = []
        complete = True
        for lag in lag_offsets:
            value = levels_by_time.get((base - _timedelta(minutes=lag)).isoformat())
            if value is None:
                complete = False
                break
            lags.append(value)
        if not complete:
            continue
        deltas = [later - earlier for earlier, later in pairwise(lags)]
        matrix.append([*lags, *deltas])
        origins.append(origin)
    return matrix, origins


def train_gbm_regressor(
    x_train: list[list[float]],
    y_train: list[float],
    config: GradientBoostingConfig | None = None,
    *,
    fg_sensor_id: str,
    horizon_minutes: int,
) -> tuple[Any, dict[str, Any]]:
    """Train a deterministic CPU XGBoost regressor (per station)."""
    cfg = config or GradientBoostingConfig()
    if not x_train:
        raise ValueError(f"station {fg_sensor_id}: empty training matrix")
    try:
        from xgboost import XGBRegressor
    except ImportError as exc:
        raise ValueError(f"xgboost is not installed: {exc}") from exc
    estimator = XGBRegressor(
        n_estimators=cfg.n_estimators,
        max_depth=cfg.max_depth,
        learning_rate=cfg.learning_rate,
        subsample=cfg.subsample,
        colsample_bytree=cfg.colsample_bytree,
        reg_lambda=cfg.reg_lambda,
        random_state=cfg.random_state,
        n_jobs=cfg.n_jobs,
        tree_method="hist",
        device="cpu",
    )
    estimator.fit(x_train, y_train)
    metadata: dict[str, Any] = {
        "schema_version": GBM_SCHEMA_VERSION,
        "model_family": MODEL_FAMILY,
        "fg_sensor_id": fg_sensor_id,
        "horizon_minutes": horizon_minutes,
        "config": asdict(cfg),
        "n_train": len(y_train),
        "n_features": len(x_train[0]),
        "device": "cpu",
        "library": f"xgboost=={XGBOOST_VERSION}",
    }
    return estimator, metadata
