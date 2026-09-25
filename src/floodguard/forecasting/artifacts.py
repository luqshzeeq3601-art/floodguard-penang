"""Forecasting artifact lineage and trusted local serialization (Phase 6).

Layout: ``artifacts/forecasting/<dataset_version>/plus_<h>m/<model_family>/``
(gitignored). Lineage covers dataset, sequence config, lookback, scaler
lineage, station scope, splits and evidence level. Model-file digests are
verified before loading (same trust model as Phase 5). Local joblib for
sklearn/XGBoost estimators; no API loading; PyTorch state-dict policy is
documented for the (currently unjustified) neural path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

FORECAST_ARTIFACT_SCHEMA: Final[str] = "forecast_artifacts/v1"


@dataclass(frozen=True)
class ForecastArtifactMetadata:
    """Complete lineage for one saved forecasting artifact."""

    model_family: str
    run_id: str
    horizon_minutes: int
    dataset_version: str
    observations_hash: str
    feature_schema_version: str
    sequence_schema_version: str
    target_definition: str
    station_scope: tuple[str, ...]
    lookback_minutes: int
    preprocessing: dict[str, Any]
    scaler_lineage: str
    model_architecture: dict[str, Any]
    random_seed: int
    device: str
    library_versions: dict[str, str]
    train_partition: str
    validation_partition: str
    test_partition: str
    evidence_level: str
    metrics_eligibility: str

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = asdict(self)
        payload["schema_version"] = FORECAST_ARTIFACT_SCHEMA
        payload["station_scope"] = list(self.station_scope)
        return payload


def forecast_artifact_dir(
    root: Path, dataset_version: str, horizon_minutes: int, model_family: str
) -> Path:
    """Deterministic local directory for one forecasting model."""
    return root / dataset_version / f"plus_{horizon_minutes}m" / model_family


def save_forecast_artifact(
    root: Path,
    estimator: Any,
    metadata: ForecastArtifactMetadata,
    *,
    model_filename: str = "model.joblib",
) -> Path:
    """Persist estimator + lineage (joblib + digest-verified JSON)."""
    if (
        not model_filename
        or model_filename in (".", "..")
        or any(sep in model_filename for sep in ("/", "\\", ":"))
    ):
        raise ValueError(f"invalid model filename: {model_filename!r}")
    target = forecast_artifact_dir(
        root, metadata.dataset_version, metadata.horizon_minutes, metadata.model_family
    )
    target.mkdir(parents=True, exist_ok=True)
    import joblib  # type: ignore[import-untyped]

    joblib.dump(estimator, target / model_filename)
    model_digest = hashlib.sha256((target / model_filename).read_bytes()).hexdigest()
    payload = metadata.to_dict()
    payload["model_file"] = model_filename
    payload["model_sha256"] = model_digest
    meta_bytes = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    (target / "metadata.json").write_bytes(meta_bytes)
    digest = hashlib.sha256(meta_bytes).hexdigest()[:16]
    (target / "metadata.sha256").write_text(f"{digest}\n", encoding="utf-8")
    return target


def load_forecast_artifact_trusted(
    path: Path, *, model_filename: str = "model.joblib"
) -> tuple[Any, dict[str, Any]]:
    """Load a locally produced artifact after verifying its model digest.

    Trust model: ``path`` is a directory FloodGuard itself wrote via
    :func:`save_forecast_artifact` on this machine. Mismatched digests raise
    ``ValueError``. Never point it at untrusted files. ``model_filename``
    must be a plain file name (separators rejected).
    """
    import joblib

    if (
        not model_filename
        or model_filename in (".", "..")
        or any(sep in model_filename for sep in ("/", "\\", ":"))
    ):
        raise ValueError(f"invalid model filename: {model_filename!r}")
    meta_bytes = (path / "metadata.json").read_bytes()
    metadata = json.loads(meta_bytes.decode("utf-8"))
    digest_path = path / "metadata.sha256"
    if not digest_path.is_file():
        raise ValueError(f"artifact integrity mismatch in {path}: metadata digest missing")
    recorded = digest_path.read_text(encoding="utf-8").strip()
    actual_meta = hashlib.sha256(meta_bytes).hexdigest()[:16]
    if actual_meta != recorded:
        raise ValueError(f"artifact integrity mismatch in {path}: metadata digest differs")
    expected = metadata.get("model_sha256")
    actual = hashlib.sha256((path / model_filename).read_bytes()).hexdigest()
    if expected is None or actual != expected:
        raise ValueError(f"artifact integrity mismatch in {path}: model file digest differs")
    estimator = joblib.load(path / model_filename)
    return estimator, metadata
