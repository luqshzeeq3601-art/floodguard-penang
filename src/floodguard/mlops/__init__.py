"""Phase 7 MLOps for FloodGuard Penang: experiments, registry, lineage, cards, gates.

Local-first and server-free: experiment runs, model versions, lineage
manifests, cards, acceptance checks and promotion verdicts are deterministic
JSON/Markdown artifacts under a gitignored store root (``artifacts/mlops/``).
No MLflow server, no DVC remote, no network, no Docker, no GPU is required;
normal tests never touch them. A future MLflow server or DVC remote can
consume these records unchanged (see ``docs/PHASE7_MLOPS.md``).

Hard rules preserved from Phases 5/6:

- ``NO_ELIGIBLE_MODEL`` / ``NO_ELIGIBLE_FORECAST_MODEL`` stand until real
  evidence supports otherwise; the registry and promotion gate enforce this.
- Synthetic results are never real performance (evidence levels enforced).
- Artifact digests are verified before loading; lineage is never rewritten.
"""

from __future__ import annotations

from typing import Final

MLOPS_SCHEMA_VERSION: Final[str] = "mlops/v1"

EVIDENCE_SYNTHETIC: Final[str] = "SYNTHETIC_SOFTWARE_VALIDATION"
EVIDENCE_LOCAL_DIAGNOSTIC: Final[str] = "LOCAL_REAL_DATA_DIAGNOSTIC"
EVIDENCE_REAL: Final[str] = "REAL_PREDICTIVE_EVALUATION"

STAGE_NONE: Final[str] = "none"
STAGE_STAGING: Final[str] = "staging"
STAGE_PRODUCTION: Final[str] = "production"
STAGE_ARCHIVED: Final[str] = "archived"
STAGES: Final[tuple[str, ...]] = (STAGE_NONE, STAGE_STAGING, STAGE_PRODUCTION, STAGE_ARCHIVED)

GATE_PROMOTE: Final[str] = "PROMOTE"
GATE_BLOCK: Final[str] = "BLOCK"

_FILENAME_RE: Final[str] = r"[A-Za-z0-9][A-Za-z0-9._-]*"


def validate_segment(value: str, *, field: str) -> str:
    """Reject path-unsafe registry/lineage/card name segments.

    Allows letters, digits, ``.``, ``_``, ``-`` (never leading-dot); rejects
    ``..``, ``.``, separators, drive syntax, and NUL. Raises ``ValueError``.
    """
    import re

    if not value or value in (".", "..") or "\x00" in value:
        raise ValueError(f"invalid {field}: {value!r}")
    if "/" in value or "\\" in value or ":" in value:
        raise ValueError(f"invalid {field}: {value!r}")
    if re.fullmatch(_FILENAME_RE, value) is None:
        raise ValueError(f"invalid {field}: {value!r}")
    return value


def resolve_within_root(path: str, *, root: str, field: str) -> str:
    """Resolve an operator-supplied artifact path, confining it under root.

    Returns the resolved absolute path as a string. Absolute paths, ``..``
    escapes, and non-existent directories are rejected with ``ValueError``,
    so CLI pickle loading cannot be pointed at arbitrary system paths.
    """
    from pathlib import Path

    root_path = Path(root).resolve()
    raw = Path(path)
    candidate = raw.resolve() if raw.is_absolute() else (root_path / raw).resolve()
    try:
        candidate.relative_to(root_path)
    except ValueError:
        raise ValueError(f"{field} escapes allowed root {root_path}: {path!r}") from None
    if not candidate.is_dir():
        raise ValueError(f"{field} is not a directory: {path!r}")
    return str(candidate)
