"""Automated acceptance + promotion-gate tests (synthetic artifacts only)."""

from __future__ import annotations

from pathlib import Path

import pytest

from floodguard.forecasting.artifacts import ForecastArtifactMetadata, save_forecast_artifact
from floodguard.forecasting.dataset import ForecastDatasetConfig, build_forecast_samples
from floodguard.forecasting.preprocessing import fit_preprocessor
from floodguard.forecasting.statistical import StatisticalConfig, train_linear_ar
from floodguard.forecasting.synthetic import make_rise_series
from floodguard.mlops import EVIDENCE_REAL, EVIDENCE_SYNTHETIC, GATE_BLOCK, GATE_PROMOTE
from floodguard.mlops.promotion import PromotionInput, decide_promotion
from floodguard.mlops.validation import run_acceptance_checks

pytestmark = pytest.mark.usefixtures("no_network")


def _forecast_artifact(tmp_path: Path, evidence: str = EVIDENCE_SYNTHETIC) -> Path:
    rows = make_rise_series(n=150)
    per_horizon, _ = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=120, dataset_version="syn")
    )
    samples = per_horizon[30][:60]
    preprocessor = fit_preprocessor({"SYN_WL_A": [s.origin_level_m for s in samples]})
    cfg = StatisticalConfig()
    seqs = [[s.origin_level_m - i * 0.01 for i in range(24)] for s in samples]
    x_train = [[seq[-lag // 5] for lag in cfg.lag_offsets_minutes] for seq in seqs]
    y_train = [s.target_level_m for s in samples]
    est, _ = train_linear_ar(x_train, y_train, cfg, fg_sensor_id="SYN_WL_A", horizon_minutes=30)
    meta = ForecastArtifactMetadata(
        model_family="linear_ar",
        run_id="acceptance-run",
        horizon_minutes=30,
        dataset_version="syn",
        observations_hash="synthetic",
        feature_schema_version="features/v1",
        sequence_schema_version="forecast_dataset/v1",
        target_definition="exact water level at t+h",
        station_scope=("SYN_WL_A",),
        lookback_minutes=120,
        preprocessing=preprocessor.to_dict(),
        scaler_lineage="per-station mean/std fit on training origins only",
        model_architecture={"lags": list(cfg.lag_offsets_minutes)},
        random_seed=42,
        device="cpu",
        library_versions={},
        train_partition="train",
        validation_partition="val",
        test_partition="test",
        evidence_level=evidence,
        metrics_eligibility="synthetic validation only",
    )
    return save_forecast_artifact(tmp_path, est, meta)


def _candidate(**overrides: object) -> PromotionInput:
    fields: dict[str, object] = {
        "run_id": "r1",
        "model_family": "linear_ar",
        "evidence_level": EVIDENCE_REAL,
        "acceptance_passed": True,
        "baseline_comparison": "favors_candidate",
        "baseline_metrics_reviewed": ("mae_m", "rmse_m", "bias_m"),
        "eligibility_status": "ELIGIBLE",
        "leakage_audit_ref": "tests/test_forecasting_leakage.py",
        "model_card_ref": "artifacts/mlops/cards/model-card-r1.md",
    }
    fields.update(overrides)
    return PromotionInput(**fields)  # type: ignore[arg-type]


def test_acceptance_passes_on_valid_artifact(tmp_path: Path) -> None:
    saved = _forecast_artifact(tmp_path)
    report = run_acceptance_checks(saved, kind="forecasting", baseline_family="persistence")
    assert report.passed
    assert {c.name for c in report.checks} >= {
        "digest_verification",
        "metadata_schema",
        "evidence_label",
        "load_and_predict",
        "inference_latency",
        "baseline_reference",
    }


def test_latency_is_measured_not_necessarily_fast(tmp_path: Path) -> None:
    """The latency probe records timing; CI asserts measurement, not speed."""
    saved = _forecast_artifact(tmp_path)
    report = run_acceptance_checks(saved, kind="forecasting", baseline_family="persistence")
    latency = [c for c in report.checks if c.name == "inference_latency"]
    assert len(latency) == 1
    assert "s for one prediction" in latency[0].detail


def test_acceptance_fails_without_baseline(tmp_path: Path) -> None:
    saved = _forecast_artifact(tmp_path)
    report = run_acceptance_checks(saved, kind="forecasting", baseline_family=None)
    assert not report.passed
    assert any(c.name == "baseline_reference" and not c.passed for c in report.checks)


def test_acceptance_fails_on_tampered_artifact(tmp_path: Path) -> None:
    saved = _forecast_artifact(tmp_path)
    (saved / "model.joblib").write_bytes(b"tampered")
    report = run_acceptance_checks(saved, kind="forecasting", baseline_family="persistence")
    assert not report.passed


def test_promotion_blocks_synthetic_despite_passing_checks() -> None:
    verdict = decide_promotion(_candidate(evidence_level=EVIDENCE_SYNTHETIC))
    assert verdict.verdict == GATE_BLOCK
    assert any("staging at best" in reason for reason in verdict.reasons)


def test_promotion_blocks_without_baseline_or_audit() -> None:
    assert decide_promotion(_candidate(baseline_comparison="absent")).verdict == GATE_BLOCK
    assert decide_promotion(_candidate(leakage_audit_ref="")).verdict == GATE_BLOCK
    assert decide_promotion(_candidate(model_card_ref="")).verdict == GATE_BLOCK
    assert (
        decide_promotion(_candidate(eligibility_status="NO_ELIGIBLE_FORECAST_MODEL")).verdict
        == GATE_BLOCK
    )


def test_promotion_blocks_accuracy_only_review() -> None:
    verdict = decide_promotion(
        _candidate(baseline_comparison="favors_candidate", baseline_metrics_reviewed=("accuracy",))
    )
    assert verdict.verdict == GATE_BLOCK
    assert any("misses required" in reason for reason in verdict.reasons)


def test_promotion_requires_classification_metrics() -> None:
    incomplete = decide_promotion(
        _candidate(
            task="classification",
            model_family="logistic_regression",
            baseline_metrics_reviewed=("recall", "precision"),
        )
    )
    assert incomplete.verdict == GATE_BLOCK
    complete = decide_promotion(
        _candidate(
            task="classification",
            model_family="logistic_regression",
            baseline_metrics_reviewed=("recall", "false_negative_rate", "pr_auc", "f1"),
        )
    )
    assert complete.verdict == GATE_PROMOTE


def test_promote_requires_everything() -> None:
    assert decide_promotion(_candidate()).verdict == GATE_PROMOTE


def test_unknown_task_blocks() -> None:
    assert decide_promotion(_candidate(task="baseline")).verdict == GATE_BLOCK
    assert decide_promotion(_candidate(task="")).verdict == GATE_BLOCK
