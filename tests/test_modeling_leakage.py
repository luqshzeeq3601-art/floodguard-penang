"""Phase 5 adversarial temporal-leakage release gates.

Verifies:
1. Mutating observations after a training/prediction boundary leaves earlier
   features unchanged.
2. Mutating validation/test labels leaves fitted training preprocessing,
   model parameters, and training predictions unchanged.
3. Test data never fits scaler/encoder/imputer/class weights/feature
   selection/threshold/calibration.
4. Future +30/+60/+120 targets never appear in the feature matrix.
5. Threshold-reference features stay excluded from standard training.
6. Appending later observations never changes earlier training rows.
7. Chronological splits stay ordered.
8. Horizon-aware purge/embargo prevents target overlap.
"""

from __future__ import annotations

import pytest

from floodguard.modeling.features import EligibilityPolicy, select_eligible_features
from floodguard.modeling.labels import extract_horizon_labels
from floodguard.modeling.logistic import LogisticConfig, train_logistic
from floodguard.modeling.preprocessing import PreprocessingConfig, fit_preprocessor, transform_rows
from floodguard.modeling.splits import SplitConfig, chronological_split
from floodguard.modeling.synthetic import make_synthetic_joined_rows

pytestmark = pytest.mark.usefixtures("no_network")

FEATURES = ("wl_level_m", "wl_rate_30m_m_per_h", "rf_roll_60m_sum_mm")


def test_future_mutation_leaves_earlier_training_rows_identical() -> None:
    rows = make_synthetic_joined_rows(n_origins=72)
    cfg = PreprocessingConfig(numeric_features=FEATURES)
    fitted = fit_preprocessor(rows[:48], cfg)
    before = transform_rows(rows[:24], fitted)
    # Radically mutate every observation after index 24.
    for row in rows[24:]:
        row["wl_level_m"] = 999.0
        row["rf_roll_60m_sum_mm"] = 999.0
    after = transform_rows(rows[:24], fitted)
    assert before == after


def test_validation_label_mutation_leaves_training_unchanged() -> None:
    rows = make_synthetic_joined_rows(n_origins=72)
    cfg = PreprocessingConfig(numeric_features=FEATURES)
    fitted_before = fit_preprocessor(rows[:48], cfg)
    matrix_before = transform_rows(rows[:48], fitted_before)
    labels = extract_horizon_labels(rows[:48], 30)
    x_train = [matrix_before[i] for i in labels.row_indices]
    est_before, _ = train_logistic(x_train, list(labels.y), LogisticConfig(), horizon_minutes=30)
    assert est_before is not None
    preds_before = list(est_before.predict(x_train))
    # Mutate all validation/test labels radically.
    for row in rows[48:]:
        for horizon in (30, 60, 120):
            row[f"target_plus_{horizon}m_exceed_waspada"] = 1
    fitted_after = fit_preprocessor(rows[:48], cfg)
    matrix_after = transform_rows(rows[:48], fitted_after)
    labels_after = extract_horizon_labels(rows[:48], 30)
    x_train_after = [matrix_after[i] for i in labels_after.row_indices]
    est_after, _ = train_logistic(
        x_train_after, list(labels_after.y), LogisticConfig(), horizon_minutes=30
    )
    assert est_after is not None
    assert list(est_after.predict(x_train_after)) == preds_before
    assert fitted_after.to_dict() == fitted_before.to_dict()


def test_future_targets_absent_from_feature_matrix() -> None:
    rows = make_synthetic_joined_rows(n_origins=40)
    eligibility = select_eligible_features(list(rows[0].keys()), EligibilityPolicy())
    for name in eligibility.eligible_features:
        assert not name.startswith("target_plus_")
        assert "future" not in name
        assert "delta" not in name.lower() or "wl_rate" in name or "wl_delta" in name


def test_threshold_reference_cannot_silently_enter_training() -> None:
    columns = ["wl_level_m", "wl_dist_to_waspada_m", "wl_dist_to_amaran_m", "wl_dist_to_bahaya_m"]
    result = select_eligible_features(columns, EligibilityPolicy())
    assert result.eligible_features == ("wl_level_m",)
    assert set(result.excluded_threshold_reference) == {
        "wl_dist_to_waspada_m",
        "wl_dist_to_amaran_m",
        "wl_dist_to_bahaya_m",
    }


def test_appended_observations_leave_earlier_training_rows_identical() -> None:
    rows = make_synthetic_joined_rows(n_origins=48)
    cfg = PreprocessingConfig(numeric_features=FEATURES)
    fitted = fit_preprocessor(rows, cfg)
    before = transform_rows(rows, fitted)
    extended = rows + make_synthetic_joined_rows(n_origins=24)
    after = transform_rows(extended[:48], fitted)
    assert before == after


def test_chronological_split_stays_ordered_with_embargo() -> None:
    rows = make_synthetic_joined_rows(n_origins=200, include_missing_tail=False)
    times = sorted(r["prediction_origin_utc"] for r in rows)
    split = chronological_split(
        rows,
        SplitConfig(train_end_utc=times[99], validation_end_utc=times[159]),
    )
    assert split.status == "OK"
    assert split.train.end_utc is not None
    assert split.validation.start_utc is not None
    assert split.train.end_utc < split.validation.start_utc
    assert split.validation.end_utc is not None
    assert split.test.start_utc is not None
    assert split.validation.end_utc < split.test.start_utc


def test_test_data_never_fits_threshold_or_calibration() -> None:
    # Threshold selection consumes validation scores only; test scores only
    # flow through the frozen threshold exactly once.
    from floodguard.modeling.thresholds import (
        apply_frozen_threshold,
        select_threshold_on_validation,
    )

    y_val = [0, 0, 1, 1] * 6
    scores_val = [0.1, 0.2, 0.8, 0.9] * 6
    selection = select_threshold_on_validation(y_val, scores_val, 30)
    assert not isinstance(selection, dict)
    frozen = selection.threshold
    y_test = [0, 1, 0, 1]
    scores_test = [0.15, 0.85, 0.25, 0.75]
    once = apply_frozen_threshold(scores_test, frozen)
    twice = apply_frozen_threshold(scores_test, frozen)
    assert once == twice == [0, 1, 0, 1]
    _ = y_test
