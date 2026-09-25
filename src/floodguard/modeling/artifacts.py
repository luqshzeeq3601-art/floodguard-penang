"""Local model artifact lineage and trusted serialization (Phase 5).

Artifact layout (repository convention):

    artifacts/models/<dataset_version>/<label_version>/<horizon>/<model_family>/

Real JPS-derived artifacts stay gitignored (``/artifacts/``, ``*.joblib``).
Each artifact carries full lineage metadata (family, run ID, horizon,
dataset/feature/label versions, split, seed, features, preprocessing,
hyperparameters, library/device, evidence level).

Serialization uses joblib for locally produced trusted artifacts only. The
trust assumption is documented: artifacts are loaded only from the local
run directory FloodGuard itself wrote, and the model file digest recorded
at save time is verified at load (review L7). No general mechanism for
loading arbitrary untrusted pickle files is provided, and no model loading
is exposed through an API in Phase 5.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

ARTIFACTS_SCHEMA_VERSION: Final[str] = "artifacts/v1"


@dataclass(frozen=True)
class ArtifactMetadata:
    """Complete lineage for one saved model artifact."""

    model_family: str
    run_id: str
    horizon_minutes: int
    dataset_version: str
    observations_hash: str
    feature_schema_version: str
    label_version: str
    split_definition: str
    training_timestamp_utc: str | None
    random_seed: int
    feature_names: tuple[str, ...]
    feature_eligibility_policy: str
    preprocessing: dict[str, Any]
    class_weighting: str | None
    hyperparameters: dict[str, Any]
    library_versions: dict[str, str]
    device: str
    evidence_level: str

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = asdict(self)
        payload["schema_version"] = ARTIFACTS_SCHEMA_VERSION
        payload["feature_names"] = list(self.feature_names)
        return payload


def artifact_dir(
    root: Path, dataset_version: str, label_version: str, horizon_minutes: int, model_family: str
) -> Path:
    """Local artifact directory for one model (deterministic layout)."""
    return root / dataset_version / label_version / f"plus_{horizon_minutes}m" / model_family


def save_artifact(
    root: Path,
    estimator: Any,
    metadata: ArtifactMetadata,
    *,
    model_filename: str = "model.joblib",
) -> Path:
    """Persist a trusted local artifact (joblib + metadata JSON)."""
    if (
        not model_filename
        or model_filename in (".", "..")
        or any(sep in model_filename for sep in ("/", "\\", ":"))
    ):
        raise ValueError(f"invalid model filename: {model_filename!r}")
    target = artifact_dir(
        root,
        metadata.dataset_version,
        metadata.label_version,
        metadata.horizon_minutes,
        metadata.model_family,
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


def load_artifact_trusted(
    path: Path, *, model_filename: str = "model.joblib"
) -> tuple[Any, dict[str, Any]]:
    """Load a locally produced trusted artifact (same-run directory only).

    Trust assumption: ``path`` is a directory FloodGuard itself wrote via
    :func:`save_artifact` on this machine. The recorded ``model_sha256``
    digest is verified before loading; a mismatch raises ``ValueError``.
    Do not point it at untrusted files. ``model_filename`` must be a plain
    file name (separators rejected) so callers cannot escape the directory.
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
