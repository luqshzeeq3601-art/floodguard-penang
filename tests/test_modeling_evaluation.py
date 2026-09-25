"""Thresholds, calibration, comparison/selection, artifacts, SHAP tests."""

from __future__ import annotations

import pytest

from floodguard.modeling import NO_ELIGIBLE_MODEL, NOT_EVALUABLE
from floodguard.modeling.artifacts import ArtifactMetadata, load_artifact_trusted, save_artifact
from floodguard.modeling.calibration import apply_calibration, fit_calibration
from floodguard.modeling.comparison import RunIdentity, ScoredRun, check_comparable, select_champion
from floodguard.modeling.logistic import LogisticConfig, train_logistic
from floodguard.modeling.preprocessing import PreprocessingConfig, fit_preprocessor, transform_rows
from floodguard.modeling.shap_analysis import permutation_contributions, shap_contributions
from floodguard.modeling.synthetic import make_synthetic_joined_rows
from floodguard.modeling.thresholds import apply_frozen_threshold, select_threshold_on_validation

pytestmark = pytest.mark.usefixtures("no_network")


def test_threshold_selected_on_validation_only() -> None:
    rows = make_synthetic_joined_rows(n_origins=72)
    scores = [0.9 if r["wl_level_m"] == 2.5 else 0.1 for r in rows]
    y_true = [1 if r["wl_level_m"] == 2.5 else 0 for r in rows]
    selection = select_threshold_on_validation(y_true[:48], scores[:48], 30)
    assert not isinstance(selection, dict)
    assert 0.0 < selection.threshold < 1.0
    # Frozen threshold applies once to held-out scores; test never re-tunes.
    preds = apply_frozen_threshold(scores[48:], selection.threshold)
    assert len(preds) == len(scores[48:])


def test_threshold_single_class_not_evaluable() -> None:
    result = select_threshold_on_validation([0, 0, 0], [0.1, 0.2, 0.3], 30)
    assert isinstance(result, dict)
    assert result["status"] == NOT_EVALUABLE


def test_calibration_fit_never_on_test() -> None:
    y_fit = [0] * 20 + [1] * 20
    scores_fit = [0.2] * 20 + [0.8] * 20
    estimator, result = fit_calibration(scores_fit, y_fit, 30, method="sigmoid")
    assert estimator is not None
    assert not isinstance(result, dict)
    calibrated = apply_calibration(estimator, "sigmoid", [0.2, 0.8])
    assert len(calibrated) == 2
    # Zero-positive fit is infeasible, not a silent zero.
    est_none, blocked = fit_calibration([0.1] * 10, [0] * 10, 30)
    assert est_none is None
    assert isinstance(blocked, dict)
    assert blocked["status"] == NOT_EVALUABLE


def _identity(run_id: str) -> RunIdentity:
    return RunIdentity(
        dataset_version="v1",
        feature_schema_version="features/v1",
        label_version="labels/v1",
        horizon_minutes=30,
        split_definition="s1",
        evaluation_period="p1",
        model_family="logistic_regression",
        run_id=run_id,
    )


def test_comparison_requires_identical_context() -> None:
    runs = [
        ScoredRun(_identity("a"), 0.8, 0.7, 0.7, 0.2, 15, True),
        ScoredRun(
            RunIdentity(
                "v2", "features/v1", "labels/v1", 30, "s1", "p1", "logistic_regression", "b"
            ),
            0.9,
            0.8,
            0.8,
            0.1,
            15,
            True,
        ),
    ]
    ok, _ = check_comparable(runs)
    assert not ok


def test_no_champion_when_event_support_fails() -> None:
    runs = [
        ScoredRun(_identity("a"), 0.8, 0.7, 0.7, 0.2, 0, False, "zero positives"),
        ScoredRun(_identity("b"), 0.9, 0.8, 0.8, 0.1, 0, False, "zero positives"),
    ]
    decision = select_champion(runs)
    assert decision["status"] == NO_ELIGIBLE_MODEL


def test_champion_selected_among_eligible_synthetic() -> None:
    runs = [
        ScoredRun(_identity("a"), 0.7, 0.6, 0.65, 0.3, 15, True),
        ScoredRun(_identity("b"), 0.9, 0.8, 0.85, 0.1, 15, True),
    ]
    decision = select_champion(runs)
    assert decision["status"] == "CHAMPION_SELECTED"
    assert decision["champion"]["run_id"] == "b"


def test_artifact_lineage_roundtrip(tmp_path: object) -> None:
    from pathlib import Path

    root = Path(str(tmp_path))
    rows = make_synthetic_joined_rows(n_origins=60)
    cfg = PreprocessingConfig(numeric_features=("wl_level_m", "rf_roll_60m_sum_mm"))
    fitted = fit_preprocessor(rows, cfg)
    matrix = transform_rows(rows, fitted)
    from floodguard.modeling.labels import extract_horizon_labels

    labels = extract_horizon_labels(rows, 30)
    x_train = [matrix[i] for i in labels.row_indices]
    estimator, _ = train_logistic(x_train, list(labels.y), LogisticConfig(), horizon_minutes=30)
    assert estimator is not None
    meta = ArtifactMetadata(
        model_family="logistic_regression",
        run_id="test-run",
        horizon_minutes=30,
        dataset_version="synthetic-test-v1",
        observations_hash="synthetic",
        feature_schema_version="features/v1",
        label_version="labels/v1",
        split_definition="test-split",
        training_timestamp_utc=None,
        random_seed=42,
        feature_names=("wl_level_m", "rf_roll_60m_sum_mm"),
        feature_eligibility_policy="standard historical training",
        preprocessing=fitted.to_dict(),
        class_weighting=None,
        hyperparameters={"C": 1.0},
        library_versions={"scikit-learn": "test"},
        device="cpu",
        evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
    )
    saved = save_artifact(root, estimator, meta)
    reloaded, reloaded_meta = load_artifact_trusted(saved)
    assert reloaded is not None
    assert reloaded_meta["run_id"] == "test-run"
    assert reloaded_meta["horizon_minutes"] == 30
    # Repeated run determinism: same inputs produce identical predictions.
    assert list(reloaded.predict(x_train)) == list(estimator.predict(x_train))


def test_shap_fallback_deterministic_and_ranked() -> None:
    rows = make_synthetic_joined_rows(n_origins=60)
    cfg = PreprocessingConfig(numeric_features=("wl_level_m", "rf_roll_60m_sum_mm"))
    fitted = fit_preprocessor(rows, cfg)
    matrix = transform_rows(rows, fitted)
    from floodguard.modeling.labels import extract_horizon_labels

    labels = extract_horizon_labels(rows, 30)
    x_train = [matrix[i] for i in labels.row_indices]
    estimator, _ = train_logistic(x_train, list(labels.y), LogisticConfig(), horizon_minutes=30)
    assert estimator is not None
    result = permutation_contributions(
        estimator.predict_proba, x_train, ["wl_level_m", "rf_roll_60m_sum_mm"], seed=42
    )
    assert result.method == "permutation_fallback"
    assert set(result.rank) == {"wl_level_m", "rf_roll_60m_sum_mm"}
    repeat = permutation_contributions(
        estimator.predict_proba, x_train, ["wl_level_m", "rf_roll_60m_sum_mm"], seed=42
    )
    assert list(repeat.mean_abs_contribution) == list(result.mean_abs_contribution)


def test_shap_exact_or_structured_unavailable() -> None:
    rows = make_synthetic_joined_rows(n_origins=40)
    cfg = PreprocessingConfig(numeric_features=("wl_level_m",))
    fitted = fit_preprocessor(rows, cfg)
    matrix = transform_rows(rows, fitted)
    from floodguard.modeling.labels import extract_horizon_labels

    labels = extract_horizon_labels(rows, 30)
    x_train = [matrix[i] for i in labels.row_indices]
    estimator, _ = train_logistic(x_train, list(labels.y), LogisticConfig(), horizon_minutes=30)
    assert estimator is not None
    result = shap_contributions(estimator, x_train[:10], ["wl_level_m"])
    # Either exact SHAP (if optional dep installed) or a structured fallback state.
    assert hasattr(result, "method") or result["status"] == "SHAP_UNAVAILABLE"
