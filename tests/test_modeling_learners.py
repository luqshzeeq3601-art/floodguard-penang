"""Learned-model training tests: logistic, forest, XGBoost (synthetic only)."""

from __future__ import annotations

import pytest

from floodguard.modeling.forest import ForestConfig, train_forest
from floodguard.modeling.gradient_boosting import GradientBoostingConfig, train_gradient_boosting
from floodguard.modeling.labels import extract_horizon_labels
from floodguard.modeling.logistic import LogisticConfig, train_logistic
from floodguard.modeling.preprocessing import PreprocessingConfig, fit_preprocessor, transform_rows
from floodguard.modeling.synthetic import (
    make_all_negative_rows,
    make_synthetic_joined_rows,
)

pytestmark = pytest.mark.usefixtures("no_network")

FEATURES = ("wl_level_m", "wl_rate_30m_m_per_h", "rf_roll_60m_sum_mm")


def _matrix(rows: list[dict[str, object]]) -> tuple[list[list[float]], list[int]]:
    cfg = PreprocessingConfig(numeric_features=FEATURES)
    fitted = fit_preprocessor(rows, cfg)  # train==all rows for fixture plumbing
    matrix = transform_rows(rows, fitted)
    labels = extract_horizon_labels(rows, 30)
    x_train = [matrix[i] for i in labels.row_indices]
    return x_train, list(labels.y)


def test_synthetic_logistic_trains_and_repeats() -> None:
    rows = make_synthetic_joined_rows(n_origins=72)
    x_train, y_train = _matrix(rows)
    est1, meta1 = train_logistic(x_train, y_train, LogisticConfig(), horizon_minutes=30)
    est2, _ = train_logistic(x_train, y_train, LogisticConfig(), horizon_minutes=30)
    assert est1 is not None
    assert est2 is not None
    assert isinstance(meta1, dict)
    assert meta1["device"] == "cpu"
    assert list(est1.predict(x_train)) == list(est2.predict(x_train))


def test_synthetic_forest_trains_small_and_deterministic() -> None:
    rows = make_synthetic_joined_rows(n_origins=72)
    x_train, y_train = _matrix(rows)
    cfg = ForestConfig(n_estimators=10, random_state=42)
    est1, meta1 = train_forest(x_train, y_train, cfg, horizon_minutes=30)
    est2, _ = train_forest(x_train, y_train, cfg, horizon_minutes=30)
    assert est1 is not None
    assert isinstance(meta1, dict)
    assert meta1["device"] == "cpu"
    assert list(est1.predict(x_train)) == list(est2.predict(x_train))


def test_synthetic_xgboost_cpu_trains() -> None:
    rows = make_synthetic_joined_rows(n_origins=72)
    x_train, y_train = _matrix(rows)
    cfg = GradientBoostingConfig(n_estimators=10, random_state=42, device="cpu")
    est, meta = train_gradient_boosting(x_train, y_train, cfg, horizon_minutes=30)
    assert est is not None
    assert isinstance(meta, dict)
    assert meta["device"] == "cpu"
    assert len(est.predict(x_train)) == len(y_train)


def test_zero_positive_training_refuses_all_families() -> None:
    rows = make_all_negative_rows(n_origins=30)
    x_train, y_train = _matrix(rows)
    assert sum(y_train) == 0
    est_lr, meta_lr = train_logistic(x_train, y_train, horizon_minutes=30)
    est_rf, _ = train_forest(x_train, y_train, horizon_minutes=30)
    est_xgb, _ = train_gradient_boosting(x_train, y_train, horizon_minutes=30)
    assert est_lr is None
    assert est_rf is None
    assert est_xgb is None
    assert hasattr(meta_lr, "status")


def test_xgboost_rejects_non_cpu_device() -> None:
    with pytest.raises(ValueError, match="must be 'cpu'"):
        GradientBoostingConfig(device="cuda")
