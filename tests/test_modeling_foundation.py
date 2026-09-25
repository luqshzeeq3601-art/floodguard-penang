"""Eligibility, preprocessing, labels, feasibility, and determinism tests."""

from __future__ import annotations

import pytest

from floodguard.modeling import INSUFFICIENT_EVENT_SUPPORT
from floodguard.modeling.feasibility import FeasibilityConfig, assess_feasibility
from floodguard.modeling.features import EligibilityPolicy, select_eligible_features
from floodguard.modeling.labels import extract_horizon_labels
from floodguard.modeling.preprocessing import (
    PreprocessingConfig,
    fit_preprocessor,
    train_class_weights,
    transform_rows,
)
from floodguard.modeling.synthetic import (
    make_all_negative_rows,
    make_all_positive_rows,
    make_synthetic_joined_rows,
)

pytestmark = pytest.mark.usefixtures("no_network")


def test_threshold_reference_excluded_by_default() -> None:
    columns = ["wl_level_m", "wl_dist_to_waspada_m", "rf_roll_60m_sum_mm", "fg_sensor_id"]
    standard = select_eligible_features(columns, EligibilityPolicy())
    assert "wl_level_m" in standard.eligible_features
    assert "wl_dist_to_waspada_m" in standard.excluded_threshold_reference
    assert "fg_sensor_id" in standard.excluded_identifiers
    # Explicit opt-in experiment documents the exception.
    opted = select_eligible_features(
        columns, EligibilityPolicy(include_threshold_reference=True, experiment_note="ablation")
    )
    assert "wl_dist_to_waspada_m" in opted.eligible_features


def test_source_ids_and_targets_never_eligible() -> None:
    columns = [
        "jps_internal_id",
        "dataset_hash",
        "paired_rainfall_sensor_id",
        "target_plus_30m_exceed_waspada",
        "target_plus_30m_status",
        "wl_level_m",
    ]
    result = select_eligible_features(columns, EligibilityPolicy())
    assert result.eligible_features == ("wl_level_m",)
    assert "jps_internal_id" in result.excluded_identifiers
    assert "target_plus_30m_exceed_waspada" in result.excluded_targets


def test_train_only_preprocessing_and_unseen_categories() -> None:
    train = [
        {"num": 1.0, "cat": "a"},
        {"num": 2.0, "cat": "b"},
        {"num": 3.0, "cat": "a"},
    ]
    cfg = PreprocessingConfig(numeric_features=("num",), categorical_features=("cat",))
    fitted = fit_preprocessor(train, cfg)
    # Mutating validation data must not change fitted training statistics.
    before = dict(fitted.numeric_means)
    _ = transform_rows([{"num": 999.0, "cat": "z-unseen"}], fitted)
    assert fitted.numeric_means == before
    vectors = transform_rows([{"num": 2.0, "cat": "z-unseen"}], fitted)
    # One-hot for {a, b} plus unknown bucket: unseen maps to unknown only.
    assert vectors[0][-3:] == [0.0, 0.0, 1.0]


def test_missing_numeric_uses_training_median() -> None:
    train = [{"num": 1.0}, {"num": 3.0}]
    cfg = PreprocessingConfig(numeric_features=("num",), scale_numeric=False)
    fitted = fit_preprocessor(train, cfg)
    assert fitted.numeric_medians["num"] == 2.0
    assert transform_rows([{"num": None}], fitted) == [[2.0]]


def test_class_weights_train_only_and_single_class() -> None:
    assert train_class_weights([0, 0, 1, 1]) == {0: 1.0, 1: 1.0}
    # Single-class training has no valid binary weighting.
    assert train_class_weights([0, 0, 0]) is None
    assert train_class_weights([]) is None


def test_missing_future_targets_excluded_from_labels() -> None:
    rows = make_synthetic_joined_rows(n_origins=40, include_missing_tail=True)
    labels = extract_horizon_labels(rows, 30)
    assert labels.missing_count > 0
    assert labels.positive_count + labels.negative_count + labels.missing_count == 40


def test_all_positive_training_edge_case_labels() -> None:
    rows = make_all_positive_rows(n_origins=20)
    labels = extract_horizon_labels(rows, 30)
    assert labels.positive_count == 20
    assert labels.negative_count == 0


def test_zero_positive_feasibility_gate() -> None:
    rows = make_all_negative_rows(n_origins=40)
    result = assess_feasibility(rows, FeasibilityConfig(min_positives=2, min_positive_episodes=1))
    assert not result.feasible
    assert result.status == INSUFFICIENT_EVENT_SUPPORT
    assert result.total_positives == 0


def test_episode_counting_not_row_counting() -> None:
    # One contiguous block of 8 positives = 1 episode, not 8 events.
    rows = make_synthetic_joined_rows(
        n_origins=40, positive_blocks=((10, 18),), include_missing_tail=False
    )
    result = assess_feasibility(rows, FeasibilityConfig(min_positives=2, min_positive_episodes=1))
    horizon30 = next(h for h in result.horizons if h.horizon_minutes == 30)
    assert horizon30.episodes == 1
    assert horizon30.positives == 8
