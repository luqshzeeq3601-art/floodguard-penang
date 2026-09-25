"""Forecasting artifact lineage, digest verification, and round-trip tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from floodguard.forecasting import EVIDENCE_SYNTHETIC
from floodguard.forecasting.artifacts import (
    ForecastArtifactMetadata,
    forecast_artifact_dir,
    load_forecast_artifact_trusted,
    save_forecast_artifact,
)
from floodguard.forecasting.dataset import ForecastDatasetConfig, build_forecast_samples
from floodguard.forecasting.preprocessing import fit_preprocessor
from floodguard.forecasting.statistical import StatisticalConfig, train_linear_ar
from floodguard.forecasting.synthetic import make_rise_series

pytestmark = pytest.mark.usefixtures("no_network")


def _trained() -> tuple[Any, ForecastArtifactMetadata, list[list[float]]]:
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
        run_id="test-run",
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
        library_versions={"scikit-learn": "test"},
        train_partition="train",
        validation_partition="val",
        test_partition="test",
        evidence_level=EVIDENCE_SYNTHETIC,
        metrics_eligibility="synthetic validation only",
    )
    return est, meta, x_train


def test_artifact_layout_and_lineage(tmp_path: Path) -> None:
    est, meta, _ = _trained()
    saved = save_forecast_artifact(tmp_path, est, meta)
    assert saved == forecast_artifact_dir(tmp_path, "syn", 30, "linear_ar")
    stored = json.loads((saved / "metadata.json").read_text(encoding="utf-8"))
    assert stored["lookback_minutes"] == 120
    assert stored["station_scope"] == ["SYN_WL_A"]
    assert stored["evidence_level"] == EVIDENCE_SYNTHETIC
    assert len(stored["model_sha256"]) == 64


def test_artifact_roundtrip_deterministic(tmp_path: Path) -> None:
    est, meta, x_train = _trained()
    saved = save_forecast_artifact(tmp_path, est, meta)
    reloaded, reloaded_meta = load_forecast_artifact_trusted(saved)
    assert reloaded_meta["run_id"] == "test-run"
    assert list(reloaded.predict(x_train)) == list(est.predict(x_train))


def test_tampered_model_file_refuses_load(tmp_path: Path) -> None:
    est, meta, _ = _trained()
    saved = save_forecast_artifact(tmp_path, est, meta)
    (saved / "model.joblib").write_bytes(b"tampered-bytes")
    with pytest.raises(ValueError, match="integrity mismatch"):
        load_forecast_artifact_trusted(saved)


def test_missing_digests_refuse_load(tmp_path: Path) -> None:
    """Final-audit N2: absent model or metadata digests must raise."""
    est, meta, _ = _trained()
    saved = save_forecast_artifact(tmp_path, est, meta)
    (saved / "metadata.sha256").unlink()
    with pytest.raises(ValueError, match="integrity mismatch"):
        load_forecast_artifact_trusted(saved)


def test_tampered_metadata_refuses_load(tmp_path: Path) -> None:
    """Final-audit N2: edited lineage must fail the metadata digest check."""
    est, meta, _ = _trained()
    saved = save_forecast_artifact(tmp_path, est, meta)
    text = (saved / "metadata.json").read_text(encoding="utf-8")
    (saved / "metadata.json").write_text(text.replace("linear_ar", "linear_ax"), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity mismatch"):
        load_forecast_artifact_trusted(saved)
