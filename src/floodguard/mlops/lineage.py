"""Dataset/model lineage strategy (Phase 7 task 3: DVC/lineage strategy).

No ``dvc`` package is installed and no DVC remote is required: lineage is
expressed as deterministic, content-hashed manifests built from the Phase
2-6 contracts (dataset versions, observation hashes, schema versions, code
versions, artifact digests). These manifests are exactly the files a future
DVC setup would track - the adoption plan in ``docs/PHASE7_MLOPS.md``
shows the corresponding ``dvc.yaml`` stages without executing them.

A lineage chain verifies backward: a model record must reference the exact
digest of its dataset manifest, and the dataset manifest must reference the
exact input hashes it was built from. Any mismatch fails loudly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

from floodguard.mlops import validate_segment

LINEAGE_SCHEMA_VERSION: Final[str] = "mlops_lineage/v1"
LINEAGE_DIRNAME: Final[str] = "lineage"


@dataclass(frozen=True)
class DatasetLineage:
    """Content-hashed record of one training/evaluation dataset."""

    dataset_version: str
    observations_hash: str
    source: str
    station_scope: tuple[str, ...]
    schema_versions: dict[str, str]
    code_version: str
    notes: str = ""

    def digest(self) -> str:
        canonical = json.dumps(self.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = asdict(self)
        payload["schema_version"] = LINEAGE_SCHEMA_VERSION
        payload["station_scope"] = list(self.station_scope)
        return payload


@dataclass(frozen=True)
class ModelLineage:
    """Link from a model run back to its exact dataset lineage digest."""

    run_id: str
    model_family: str
    dataset_digest: str
    dataset_version: str
    artifact_digest: str | None
    parent_run_ids: tuple[str, ...] = ()
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = asdict(self)
        payload["schema_version"] = LINEAGE_SCHEMA_VERSION
        payload["parent_run_ids"] = list(self.parent_run_ids)
        return payload


def _lineage_dir(store_root: Path) -> Path:
    return store_root / LINEAGE_DIRNAME


def write_dataset_lineage(store_root: Path, lineage: DatasetLineage) -> Path:
    """Persist one dataset lineage manifest (write-once, digest-named)."""
    validate_segment(lineage.dataset_version, field="dataset version")
    target_dir = _lineage_dir(store_root) / "datasets"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{lineage.dataset_version}-{lineage.digest()[:16]}.json"
    payload = json.dumps(lineage.to_dict(), indent=2, sort_keys=True).encode("utf-8")
    if path.is_file() and path.read_bytes() != payload:
        raise ValueError(f"conflicting dataset lineage at {path}")
    path.write_bytes(payload)
    return path


def write_model_lineage(store_root: Path, lineage: ModelLineage) -> Path:
    """Persist one model lineage record (write-once per run)."""
    validate_segment(lineage.run_id, field="run id")
    target_dir = _lineage_dir(store_root) / "models"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{lineage.run_id}.json"
    payload = json.dumps(lineage.to_dict(), indent=2, sort_keys=True).encode("utf-8")
    if path.is_file() and path.read_bytes() != payload:
        raise ValueError(f"conflicting model lineage for run {lineage.run_id}")
    path.write_bytes(payload)
    return path


def verify_model_lineage(
    store_root: Path,
    lineage: ModelLineage,
    *,
    dataset_manifest: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Check a model record against its dataset manifest digest."""
    if dataset_manifest is None:
        candidates = sorted((_lineage_dir(store_root) / "datasets").glob("*.json"))
        match = None
        for candidate in candidates:
            manifest: dict[str, Any] = json.loads(candidate.read_text(encoding="utf-8"))
            record = DatasetLineage(
                dataset_version=str(manifest["dataset_version"]),
                observations_hash=str(manifest["observations_hash"]),
                source=str(manifest["source"]),
                station_scope=tuple(manifest.get("station_scope", [])),
                schema_versions=dict(manifest.get("schema_versions", {})),
                code_version=str(manifest.get("code_version", "")),
                notes=str(manifest.get("notes", "")),
            )
            if record.digest() == lineage.dataset_digest:
                match = manifest
                break
        if match is None:
            return False, "no dataset manifest matches the recorded dataset digest"
        return True, "dataset digest matches a stored manifest"
    record = DatasetLineage(
        dataset_version=str(dataset_manifest["dataset_version"]),
        observations_hash=str(dataset_manifest["observations_hash"]),
        source=str(dataset_manifest["source"]),
        station_scope=tuple(dataset_manifest.get("station_scope", [])),
        schema_versions=dict(dataset_manifest.get("schema_versions", {})),
        code_version=str(dataset_manifest.get("code_version", "")),
        notes=str(dataset_manifest.get("notes", "")),
    )
    if record.digest() != lineage.dataset_digest:
        return False, "dataset manifest digest differs from the recorded digest"
    return True, "dataset digest matches the provided manifest"
