"""Regression tests for independent reviewer findings (Phase 5 audit).

Each test pins one HIGH/MEDIUM/LOW finding so the defect cannot regress:
H1, M1, M2, M4, L4, L7, L8.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from floodguard.modeling import NOT_EVALUABLE
from floodguard.modeling.artifacts import ArtifactMetadata, load_artifact_trusted, save_artifact
from floodguard.modeling.feasibility import FeasibilityConfig, assess_feasibility
from floodguard.modeling.features import EligibilityPolicy, select_eligible_features
from floodguard.modeling.logistic import LogisticConfig, train_logistic
from floodguard.modeling.metrics import classification_metrics
from floodguard.modeling.preprocessing import PreprocessingConfig, fit_preprocessor, transform_rows
from floodguard.modeling.splits import walk_forward_folds
from floodguard.modeling.synthetic import make_synthetic_joined_rows

pytestmark = pytest.mark.usefixtures("no_network")


def test_h1_partitions_respect_embargo_and_keep_duplicate_times() -> None:
    """H1: training partitions must apply the embargo; shared timestamps kept."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("train_model_mod", Path("scripts/train_model.py"))
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    start = datetime(2030, 1, 1, tzinfo=UTC)
    rows: list[dict[str, object]] = []
    for i in range(60):
        origin = (start + timedelta(minutes=5 * i)).isoformat()
        # Two stations share every origin timestamp.
        for station in ("SYN_A", "SYN_B"):
            rows.append(
                {
                    "prediction_origin_utc": origin,
                    "wl_level_m": 1.0,
                    "station": station,
                }
            )
    times = sorted(str(r["prediction_origin_utc"]) for r in rows)
    train_end = times[len(times) * 2 // 3]
    val_end = times[len(times) * 5 // 6]
    train, val, test, purged_train, purged_val = module._partition_by_time(
        rows,
        train_end,
        val_end,
    )
    # No timestamp collapsed: partitions cover every input row exactly once
    # (trained or purged).
    assert len(train) + len(val) + len(test) + purged_train + purged_val == len(rows)
    # Embargo purges exist on both boundaries for this span.
    assert purged_train > 0
    assert purged_val > 0
    # Multi-station duplicates preserved (even counts).
    assert len(train) % 2 == 0
    assert len(val) % 2 == 0


def test_m1_minima_apply_per_horizon_not_summed() -> None:
    """M1: 12 positives on one horizon must not pass a min_positives=30 gate."""
    rows = make_synthetic_joined_rows(
        n_origins=60, positive_blocks=((10, 22),), include_missing_tail=False
    )
    # +30/+60/+120 each carry the same 12 positives; summed totals would be 36.
    result = assess_feasibility(rows, FeasibilityConfig(min_positives=30, min_positive_episodes=1))
    assert not result.feasible
    assert "per horizon" in result.reason


def test_m2_first_fold_validates_outside_embargo() -> None:
    """M2: fold-0 validation must exclude (boundary - embargo, boundary]."""
    start = datetime(2030, 1, 1, tzinfo=UTC)
    rows = [
        {"prediction_origin_utc": (start + timedelta(minutes=5 * i)).isoformat()}
        for i in range(100)
    ]
    boundary = (start + timedelta(minutes=5 * 60)).isoformat()
    folds = walk_forward_folds(rows, [boundary], embargo_minutes=120)
    assert len(folds) == 1
    fold = folds[0]
    # Boundary at index 60 (300 min); cutoff at 180 min (index 36):
    # train = indices 0..36 (37 rows), embargo zone = indices 37..60 (24 rows).
    assert fold.purged_train_rows == 24
    assert fold.train_rows == 37
    assert fold.validation_rows == fold.train_rows  # first-fold scope is all non-purged


def test_m4_station_coordinates_excluded_by_default() -> None:
    """M4: lat/lon must not enter standard historical training."""
    result = select_eligible_features(
        ["wl_level_m", "station_latitude", "station_longitude"], EligibilityPolicy()
    )
    assert result.eligible_features == ("wl_level_m",)
    assert "station_latitude" in result.excluded_identifiers
    assert "station_longitude" in result.excluded_identifiers


def test_l4_defined_zero_f1_and_empty_accuracy() -> None:
    """L4: all-wrong predictions give F1=0.0; empty sets give NOT_EVALUABLE."""
    wrong = classification_metrics([1, 1, 0, 0], [0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9], 30)
    assert wrong.f1 == 0.0
    assert wrong.recall == 0.0
    assert wrong.precision == 0.0
    empty = classification_metrics([], [], None, 30)
    assert empty.accuracy == NOT_EVALUABLE
    assert empty.recall == NOT_EVALUABLE


def test_l7_tampered_model_file_refuses_load(tmp_path: Path) -> None:
    """L7: digest mismatch on the model file must fail loudly."""
    rows = make_synthetic_joined_rows(n_origins=40, include_missing_tail=False)
    cfg = PreprocessingConfig(numeric_features=("wl_level_m",))
    fitted = fit_preprocessor(rows, cfg)
    matrix = transform_rows(rows, fitted)
    from floodguard.modeling.labels import extract_horizon_labels

    labels = extract_horizon_labels(rows, 30)
    x_train = [matrix[i] for i in labels.row_indices]
    estimator, _ = train_logistic(x_train, list(labels.y), LogisticConfig(), horizon_minutes=30)
    assert estimator is not None
    meta = ArtifactMetadata(
        model_family="logistic_regression",
        run_id="tamper-test",
        horizon_minutes=30,
        dataset_version="synthetic-test-v1",
        observations_hash="synthetic",
        feature_schema_version="features/v1",
        label_version="labels/v1",
        split_definition="test",
        training_timestamp_utc=None,
        random_seed=42,
        feature_names=("wl_level_m",),
        feature_eligibility_policy="standard",
        preprocessing=fitted.to_dict(),
        class_weighting=None,
        hyperparameters={},
        library_versions={},
        device="cpu",
        evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
    )
    saved = save_artifact(tmp_path, estimator, meta)
    (saved / "model.joblib").write_bytes(b"tampered-bytes")
    with pytest.raises(ValueError, match="integrity mismatch"):
        load_artifact_trusted(saved)


def test_l8_synthetic_tails_differ_per_horizon() -> None:
    """L8: +30/+60/+120 truncation tails must differ (6/12/24 slots)."""
    rows = make_synthetic_joined_rows(n_origins=60, include_missing_tail=True)
    missing_30 = sum(1 for r in rows if r["target_plus_30m_status"] == "MISSING_FUTURE_TARGET")
    missing_60 = sum(1 for r in rows if r["target_plus_60m_status"] == "MISSING_FUTURE_TARGET")
    missing_120 = sum(1 for r in rows if r["target_plus_120m_status"] == "MISSING_FUTURE_TARGET")
    assert (missing_30, missing_60, missing_120) == (6, 12, 24)


def test_metadata_records_model_digest(tmp_path: Path) -> None:
    """Artifact metadata must record the model file digest."""
    rows = make_synthetic_joined_rows(n_origins=40, include_missing_tail=False)
    cfg = PreprocessingConfig(numeric_features=("wl_level_m",))
    fitted = fit_preprocessor(rows, cfg)
    matrix = transform_rows(rows, fitted)
    from floodguard.modeling.labels import extract_horizon_labels

    labels = extract_horizon_labels(rows, 30)
    x_train = [matrix[i] for i in labels.row_indices]
    estimator, _ = train_logistic(x_train, list(labels.y), LogisticConfig(), horizon_minutes=30)
    assert estimator is not None
    meta = ArtifactMetadata(
        model_family="logistic_regression",
        run_id="digest-test",
        horizon_minutes=30,
        dataset_version="synthetic-test-v1",
        observations_hash="synthetic",
        feature_schema_version="features/v1",
        label_version="labels/v1",
        split_definition="test",
        training_timestamp_utc=None,
        random_seed=42,
        feature_names=("wl_level_m",),
        feature_eligibility_policy="standard",
        preprocessing=fitted.to_dict(),
        class_weighting=None,
        hyperparameters={},
        library_versions={},
        device="cpu",
        evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
    )
    saved = save_artifact(tmp_path, estimator, meta)
    stored = json.loads((saved / "metadata.json").read_text(encoding="utf-8"))
    assert len(stored["model_sha256"]) == 64
