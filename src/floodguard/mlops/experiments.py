"""Local experiment tracking (Phase 7 task 1: MLflow experiments).

MLflow-concept-compatible run records (params, metrics, tags, artifact
references) in a local write-once JSON store. No ``mlflow`` package, no
tracking server, no network: tests stay offline and deterministic.

Migration path: :meth:`ExperimentRun.to_mlflow_tags` flattens lineage into
the string-tag mapping a future ``mlflow.start_run`` call would log, so
adoption of a real MLflow server later requires no record redesign
(see ``docs/PHASE7_MLOPS.md``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

EXPERIMENTS_SCHEMA_VERSION: Final[str] = "mlops_experiments/v1"
RUNS_DIRNAME: Final[str] = "experiments"


@dataclass(frozen=True)
class ExperimentRun:
    """One deterministic training/evaluation experiment record."""

    run_id: str
    task: str  # "classification" | "forecasting" | "baseline"
    model_family: str
    horizon_minutes: int
    dataset_version: str
    schema_versions: dict[str, str]
    split_definition: str
    random_seed: int
    device: str
    library_versions: dict[str, str]
    params: dict[str, Any]
    metrics: dict[str, Any]
    tags: dict[str, str]
    artifact_ref: dict[str, Any]
    evidence_level: str
    status: str = "FINISHED"

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = asdict(self)
        payload["schema_version"] = EXPERIMENTS_SCHEMA_VERSION
        return payload

    def to_mlflow_tags(self) -> dict[str, str]:
        """Flatten lineage into MLflow-compatible string tags."""
        tags = dict(self.tags)
        tags.update(
            {
                "floodguard.task": self.task,
                "floodguard.model_family": self.model_family,
                "floodguard.horizon_minutes": str(self.horizon_minutes),
                "floodguard.dataset_version": self.dataset_version,
                "floodguard.split": self.split_definition,
                "floodguard.seed": str(self.random_seed),
                "floodguard.device": self.device,
                "floodguard.evidence_level": self.evidence_level,
                "floodguard.run_id": self.run_id,
            }
        )
        for key, value in self.schema_versions.items():
            tags[f"floodguard.schema.{key}"] = str(value)
        return tags


def deterministic_run_id(
    *,
    task: str,
    model_family: str,
    horizon_minutes: int,
    dataset_version: str,
    params: dict[str, Any],
    random_seed: int,
) -> str:
    """Stable run identity from the experiment definition (no wall-clock)."""
    canonical = json.dumps(
        {
            "task": task,
            "model_family": model_family,
            "horizon_minutes": horizon_minutes,
            "dataset_version": dataset_version,
            "params": params,
            "random_seed": random_seed,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _runs_dir(store_root: Path) -> Path:
    return store_root / RUNS_DIRNAME


def log_run(store_root: Path, run: ExperimentRun) -> Path:
    """Persist one run record write-once; reruns with identical content are no-ops."""
    target_dir = _runs_dir(store_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(run.to_dict(), indent=2, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    path = target_dir / f"{run.run_id}.json"
    if path.is_file():
        existing = path.read_bytes()
        if existing != payload:
            raise ValueError(f"run {run.run_id}: conflicting record already stored")
        return path
    path.write_bytes(payload)
    (target_dir / f"{run.run_id}.sha256").write_text(f"{digest}\n", encoding="utf-8")
    return path


def get_run(store_root: Path, run_id: str) -> dict[str, Any]:
    """Load one stored run record (digest-verified)."""
    from floodguard.mlops import validate_segment

    validate_segment(run_id, field="run id")
    path = _runs_dir(store_root) / f"{run_id}.json"
    if not path.is_file():
        raise ValueError(f"unknown run_id: {run_id}")
    raw = path.read_bytes()
    digest_path = _runs_dir(store_root) / f"{run_id}.sha256"
    if not digest_path.is_file():
        raise ValueError(f"run {run_id}: digest file missing")
    if hashlib.sha256(raw).hexdigest() != digest_path.read_text(encoding="utf-8").strip():
        raise ValueError(f"run {run_id}: digest mismatch")
    loaded: dict[str, Any] = json.loads(raw.decode("utf-8"))
    return loaded


def find_runs(
    store_root: Path,
    *,
    task: str | None = None,
    model_family: str | None = None,
    horizon_minutes: int | None = None,
    evidence_level: str | None = None,
) -> list[dict[str, Any]]:
    """Filter stored runs by exact field matches (deterministic order).

    Unreadable or digest-invalid files are skipped (listing is not a store
    integrity audit; see :func:`audit_store`). Returned records always pass
    through the verified loader.
    """
    run_dir = _runs_dir(store_root)
    if not run_dir.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(run_dir.glob("*.json")):
        try:
            record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if task is not None and record.get("task") != task:
            continue
        if model_family is not None and record.get("model_family") != model_family:
            continue
        if horizon_minutes is not None and record.get("horizon_minutes") != horizon_minutes:
            continue
        if evidence_level is not None and record.get("evidence_level") != evidence_level:
            continue
        run_id = record.get("run_id")
        if not isinstance(run_id, str):
            continue
        try:
            results.append(get_run(store_root, run_id))
        except (OSError, ValueError):
            continue
    return results


def audit_store(store_root: Path) -> dict[str, Any]:
    """Verify every stored run record; report verified vs skipped files."""
    run_dir = _runs_dir(store_root)
    verified: list[str] = []
    skipped: list[dict[str, str]] = []
    if run_dir.is_dir():
        for path in sorted(run_dir.glob("*.json")):
            try:
                record: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
                run_id = record.get("run_id")
                if not isinstance(run_id, str):
                    raise ValueError("record lacks a string run_id")
                get_run(store_root, run_id)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                skipped.append({"file": path.name, "error": f"{type(exc).__name__}: {exc}"})
                continue
            verified.append(path.name)
    return {
        "schema_version": EXPERIMENTS_SCHEMA_VERSION,
        "verified": verified,
        "skipped": skipped,
    }


@dataclass
class ExperimentInput:
    """Caller-supplied fields for a new run (run_id derived)."""

    task: str
    model_family: str
    horizon_minutes: int
    dataset_version: str
    schema_versions: dict[str, str] = field(default_factory=dict)
    split_definition: str = ""
    random_seed: int = 42
    device: str = "cpu"
    library_versions: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    tags: dict[str, str] = field(default_factory=dict)
    artifact_ref: dict[str, Any] = field(default_factory=dict)
    evidence_level: str = "SYNTHETIC_SOFTWARE_VALIDATION"
    status: str = "FINISHED"

    def to_run(self) -> ExperimentRun:
        # Strict JSON-native params keep run IDs free of str() artifacts
        # such as memory addresses in exotic objects.
        try:
            canonical_params = json.loads(json.dumps(self.params))
            canonical_metrics = json.loads(json.dumps(self.metrics))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"params/metrics must be JSON-native: {exc}") from exc
        return ExperimentRun(
            run_id=deterministic_run_id(
                task=self.task,
                model_family=self.model_family,
                horizon_minutes=self.horizon_minutes,
                dataset_version=self.dataset_version,
                params=canonical_params,
                random_seed=self.random_seed,
            ),
            task=self.task,
            model_family=self.model_family,
            horizon_minutes=self.horizon_minutes,
            dataset_version=self.dataset_version,
            schema_versions=dict(self.schema_versions),
            split_definition=self.split_definition,
            random_seed=self.random_seed,
            device=self.device,
            library_versions=dict(self.library_versions),
            params=canonical_params,
            metrics=canonical_metrics,
            tags=dict(self.tags),
            artifact_ref=dict(self.artifact_ref),
            evidence_level=self.evidence_level,
            status=self.status,
        )
