"""Local model registry (Phase 7 task 2: Model registry).

File-based model versions with gated stage transitions. Allowed edges:
``none`` → ``staging`` → ``production``, plus any non-archived stage →
``archived`` (terminal). Demotions, skips, and same-stage rewrites are
rejected. Rules:

- Registration records caller claims (run_id, artifact digests, evidence
  level); it never implies quality. The blessed path is
  ``scripts/register_model.py``, which verifies artifact digests via the
  trusted loaders before recording.
- ``staging`` accepts any evidence level (synthetic/local/real).
- ``production`` requires a recorded ``PROMOTE`` gate verdict **and**
  ``REAL_PREDICTIVE_EVALUATION`` evidence. With current data this is
  unreachable, which preserves ``NO_ELIGIBLE_MODEL``.
- ``archived`` is always allowed and terminal (no transitions out).
- Every transition appends to ``transitions.jsonl`` (audit trail) and stamps
  ``updated_at`` (UTC now unless the caller supplies ``at``).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from floodguard.mlops import (
    EVIDENCE_REAL,
    GATE_PROMOTE,
    STAGE_ARCHIVED,
    STAGE_NONE,
    STAGE_PRODUCTION,
    STAGE_STAGING,
    STAGES,
    validate_segment,
)

REGISTRY_SCHEMA_VERSION: Final[str] = "mlops_registry/v1"
VERSIONS_DIRNAME: Final[str] = "registry"
TRANSITIONS_LOG: Final[str] = "transitions.jsonl"

_ALLOWED_EDGES: Final[dict[str, tuple[str, ...]]] = {
    STAGE_NONE: (STAGE_STAGING, STAGE_ARCHIVED),
    STAGE_STAGING: (STAGE_PRODUCTION, STAGE_ARCHIVED),
    STAGE_PRODUCTION: (STAGE_ARCHIVED,),
    STAGE_ARCHIVED: (),
}


@dataclass(frozen=True)
class ModelVersion:
    """One registered model version with stage and lineage."""

    name: str
    version: int
    run_id: str
    stage: str
    artifact_dir: str
    artifact_digest: str | None
    evidence_level: str
    gate_verdict: str | None
    reason: str
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = asdict(self)
        payload["schema_version"] = REGISTRY_SCHEMA_VERSION
        return payload


def _versions_dir(store_root: Path) -> Path:
    return store_root / VERSIONS_DIRNAME


def _version_path(store_root: Path, name: str, version: int) -> Path:
    return _versions_dir(store_root) / name / f"v{version}.json"


def list_versions(store_root: Path, name: str) -> list[dict[str, Any]]:
    """All registered versions of one model, oldest first."""
    import re

    validate_segment(name, field="model name")
    model_dir = _versions_dir(store_root) / name
    if not model_dir.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for path in sorted(model_dir.glob("v*.json"), key=lambda p: p.name):
        if re.fullmatch(r"v\d+\.json", path.name) is None:
            continue
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"corrupt registry file {path}: {exc}") from exc
    records.sort(key=lambda r: int(str(r.get("version", 0))))
    return records


def register(
    store_root: Path,
    *,
    name: str,
    run_id: str,
    artifact_dir: str,
    artifact_digest: str | None,
    evidence_level: str,
    reason: str,
    stage: str = STAGE_NONE,
) -> ModelVersion:
    """Register the next version of a model (stage defaults to ``none``).

    Trust note: ``run_id``, ``artifact_digest`` and ``evidence_level`` are
    recorded as caller claims; this function never implies quality. The
    blessed path is ``scripts/register_model.py``, which verifies artifact
    digests through the trusted loaders before recording.
    """
    validate_segment(name, field="model name")
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    if stage == STAGE_PRODUCTION:
        raise ValueError("register into staging first; production requires the promotion gate")
    existing = list_versions(store_root, name)
    version = len(existing) + 1
    record = ModelVersion(
        name=name,
        version=version,
        run_id=run_id,
        stage=stage,
        artifact_dir=artifact_dir,
        artifact_digest=artifact_digest,
        evidence_level=evidence_level,
        gate_verdict=None,
        reason=reason,
    )
    target = _version_path(store_root, name, version)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        raise ValueError(f"{name} v{version} is already registered")
    target.write_text(
        json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return record


def transition_stage(
    store_root: Path,
    *,
    name: str,
    version: int,
    to_stage: str,
    reason: str,
    gate_verdict: str | None = None,
    at: str | None = None,
) -> ModelVersion:
    """Move one version between stages along allowed edges, then log it."""
    validate_segment(name, field="model name")
    if to_stage not in STAGES:
        raise ValueError(f"unknown stage: {to_stage}")
    path = _version_path(store_root, name, version)
    if not path.is_file():
        raise ValueError(f"unknown model version: {name} v{version}")
    current = json.loads(path.read_text(encoding="utf-8"))
    from_stage = str(current.get("stage", STAGE_NONE))
    if from_stage == STAGE_ARCHIVED:
        raise ValueError(f"{name} v{version} is archived and terminal")
    if to_stage not in _ALLOWED_EDGES.get(from_stage, ()):
        raise ValueError(f"forbidden stage transition: {from_stage} -> {to_stage}")
    if to_stage == STAGE_PRODUCTION:
        if gate_verdict != GATE_PROMOTE:
            raise ValueError("production requires a recorded PROMOTE gate verdict")
        if str(current.get("evidence_level")) != EVIDENCE_REAL:
            raise ValueError("production requires REAL_PREDICTIVE_EVALUATION evidence")
    stamp = at if at is not None else datetime.now(UTC).isoformat()
    updated = ModelVersion(
        name=name,
        version=version,
        run_id=str(current.get("run_id", "")),
        stage=to_stage,
        artifact_dir=str(current.get("artifact_dir", "")),
        artifact_digest=current.get("artifact_digest"),
        evidence_level=str(current.get("evidence_level", "")),
        gate_verdict=gate_verdict,
        reason=reason,
        updated_at=stamp,
    )
    path.write_text(
        json.dumps(updated.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    log_path = _versions_dir(store_root) / TRANSITIONS_LOG
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "name": name,
                    "version": version,
                    "from_stage": from_stage,
                    "to_stage": to_stage,
                    "reason": reason,
                    "at": stamp,
                },
                sort_keys=True,
            )
            + "\n"
        )
    return updated
