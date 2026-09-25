"""Persistence/rule baseline, metrics, and horizon-independence tests (Phase 5 task 1)."""

from __future__ import annotations

import pytest

from floodguard.modeling import NOT_EVALUABLE
from floodguard.modeling.baselines import (
    RuleConfig,
    persistence_forecast_for_row,
    rule_predict_row,
)
from floodguard.modeling.metrics import (
    average_precision_score_safe,
    classification_metrics,
    confusion_matrix,
    regression_metrics,
)
from floodguard.modeling.synthetic import make_synthetic_joined_rows

pytestmark = pytest.mark.usefixtures("no_network")


def test_persistence_uses_origin_level_per_horizon() -> None:
    rows = make_synthetic_joined_rows(n_origins=30, include_missing_tail=False)
    row = rows[0]
    for horizon in (30, 60, 120):
        result = persistence_forecast_for_row(row, horizon)
        assert result.status == "TARGET_EVALUATED"
        assert result.predicted_level_m == result.origin_level_m
        assert result.actual_level_m is not None


def test_persistence_missing_target_excluded_not_zero() -> None:
    rows = make_synthetic_joined_rows(n_origins=30, include_missing_tail=True)
    tail = rows[-1]
    for horizon in (30, 60, 120):
        result = persistence_forecast_for_row(tail, horizon)
        assert result.status == "MISSING_FUTURE_TARGET"
        assert result.actual_level_m is None


def test_rule_uses_only_origin_info() -> None:
    positive = {
        "wl_rate_30m_m_per_h": 1.0,
        "rf_roll_60m_sum_mm": 50.0,
        "wl_dist_to_waspada_m": 5.0,  # must not trigger without opt-in
    }
    assert rule_predict_row(positive, RuleConfig()) == 1
    negative = {"wl_rate_30m_m_per_h": 0.0, "rf_roll_60m_sum_mm": 0.0}
    assert rule_predict_row(negative, RuleConfig()) == 0
    unevaluable = {"wl_rate_30m_m_per_h": None, "rf_roll_60m_sum_mm": None}
    assert rule_predict_row(unevaluable, RuleConfig()) is None


def test_rule_threshold_reference_opt_in() -> None:
    row = {
        "wl_rate_30m_m_per_h": 0.0,
        "rf_roll_60m_sum_mm": 0.0,
        "wl_dist_to_waspada_m": 0.5,
    }
    assert rule_predict_row(row, RuleConfig(allow_threshold_reference=False)) == 0
    assert rule_predict_row(row, RuleConfig(allow_threshold_reference=True)) == 1


def test_horizon_independence_plus30_vs_plus120() -> None:
    rows = make_synthetic_joined_rows(n_origins=40, include_missing_tail=False)
    # Corrupt +120 labels; +30 evaluation must be unaffected.
    for row in rows:
        row["target_plus_120m_exceed_waspada"] = 1 - int(row["target_plus_120m_exceed_waspada"])
    y30 = [int(r["target_plus_30m_exceed_waspada"]) for r in rows]
    assert set(y30) == {0, 1}


def test_confusion_and_undefined_metrics() -> None:
    cm = confusion_matrix([1, 0, 1, 0], [1, 1, 0, 0])
    assert (cm.tp, cm.fp, cm.tn, cm.fn) == (1, 1, 1, 1)
    result = classification_metrics([0, 0, 0], [0, 0, 0], [0.1, 0.2, 0.3], 30)
    assert result.recall == NOT_EVALUABLE
    assert result.f1 == NOT_EVALUABLE
    assert result.pr_auc == NOT_EVALUABLE
    # Accuracy is reported but never primary; all-negative accuracy is high yet meaningless.
    assert result.accuracy == 1.0
    assert "zero positive" in " ".join(result.notes)


def test_pr_auc_single_class_not_evaluable() -> None:
    assert average_precision_score_safe([0, 0], [0.1, 0.2]) == NOT_EVALUABLE
    assert average_precision_score_safe([], []) == NOT_EVALUABLE


def test_regression_empty_not_evaluable() -> None:
    result = regression_metrics([], [], 30)
    assert result.mae_m == NOT_EVALUABLE
    assert result.rmse_m == NOT_EVALUABLE
