"""Statistical forecasting baseline (Phase 6 task 2): per-station linear AR.

A deterministic ordinary-least-squares autoregression over exact lag levels.
Per-station models only (gauge datums are incomparable). Fitted on training
origins only; validation/test never influence coefficients. Small,
CPU-only, seed-free (closed-form OLS via scikit-learn).

Lag offsets are project configuration recorded in every artifact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final

from sklearn.linear_model import LinearRegression  # type: ignore[import-untyped]

STATISTICAL_SCHEMA_VERSION: Final[str] = "forecast_statistical/v1"
MODEL_FAMILY: Final[str] = "linear_ar"
DEFAULT_LAG_OFFSETS_MINUTES: Final[tuple[int, ...]] = (5, 10, 15, 30, 60, 120)


@dataclass(frozen=True)
class StatisticalConfig:
    """Linear AR configuration (lags must divide the 5-min cadence)."""

    lag_offsets_minutes: tuple[int, ...] = DEFAULT_LAG_OFFSETS_MINUTES
    fit_intercept: bool = True

    def __post_init__(self) -> None:
        if not self.lag_offsets_minutes or any(
            lag <= 0 or lag % 5 != 0 for lag in self.lag_offsets_minutes
        ):
            raise ValueError("lag offsets must be positive multiples of 5 minutes")


def lag_feature_names(config: StatisticalConfig) -> list[str]:
    """Deterministic lag feature names for lineage."""
    return [f"wl_lag_{lag}m_m" for lag in config.lag_offsets_minutes]


def build_lag_matrix(
    levels_by_time: dict[str, float],
    ordered_times: list[str],
    config: StatisticalConfig,
) -> tuple[list[list[float]], list[str]]:
    """Build lag rows for origins whose full lag set is present (no fill)."""
    from datetime import datetime as _datetime
    from datetime import timedelta as _timedelta

    matrix: list[list[float]] = []
    origins: list[str] = []
    for origin in ordered_times:
        base = _datetime.fromisoformat(origin)
        lags: list[float] = []
        complete = True
        for lag in config.lag_offsets_minutes:
            key = (base - _timedelta(minutes=lag)).isoformat()
            value = levels_by_time.get(key)
            if value is None:
                complete = False
                break
            lags.append(value)
        if complete:
            matrix.append(lags)
            origins.append(origin)
    return matrix, origins


def train_linear_ar(
    x_train: list[list[float]],
    y_train: list[float],
    config: StatisticalConfig | None = None,
    *,
    fg_sensor_id: str,
    horizon_minutes: int,
) -> tuple[Any, dict[str, Any]]:
    """Fit closed-form OLS on training rows only (per station)."""
    cfg = config or StatisticalConfig()
    if not x_train:
        raise ValueError(f"station {fg_sensor_id}: empty training matrix")
    estimator = LinearRegression(fit_intercept=cfg.fit_intercept)
    estimator.fit(x_train, y_train)
    metadata: dict[str, Any] = {
        "schema_version": STATISTICAL_SCHEMA_VERSION,
        "model_family": MODEL_FAMILY,
        "fg_sensor_id": fg_sensor_id,
        "horizon_minutes": horizon_minutes,
        "config": asdict(cfg),
        "n_train": len(y_train),
        "n_features": len(x_train[0]),
        "device": "cpu",
        "library": "scikit-learn",
    }
    return estimator, metadata
