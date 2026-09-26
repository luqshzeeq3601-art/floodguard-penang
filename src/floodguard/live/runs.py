"""Scheduled run state (Phase 10).

One record per poll attempt per source/dataset. Stores run ID, source,
start/end, status, records fetched/accepted, quarantined/duplicate counts,
error category and payload lineage. No secrets. Incomplete runs (started but
never closed, e.g. crash between placement and manifest append) are
detectable via ``find_incomplete``.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

RUN_SCHEMA_VERSION: Final[str] = "live_run/v1"


class RunStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"
    BLOCKED_PERMISSION = "BLOCKED_PERMISSION"
    SKIPPED_OVERLAP = "SKIPPED_OVERLAP"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    source: str
    dataset: str
    started_at: str
    ended_at: str | None
    status: RunStatus
    records_fetched: int = 0
    records_accepted: int = 0
    quarantined_count: int = 0
    duplicate_count: int = 0
    error_category: str | None = None
    payload_sha256: str | None = None
    batch_id: str | None = None
    duration_seconds: float | None = None
    schema_version: str = RUN_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = str(self.status)
        return d


def new_run_id() -> str:
    return str(uuid.uuid4())


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _atomic_append(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (path.read_bytes() if path.exists() else b"") + (line + "\n").encode("utf-8")
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


class RunStore:
    """Append-only JSONL run history (restart-safe, replayable)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def append(self, record: RunRecord) -> None:
        _atomic_append(self._path, json.dumps(record.to_json_dict(), sort_keys=True))

    def read_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        out = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                doc = json.loads(line)
                if isinstance(doc, dict):
                    out.append(doc)
        return out

    def find_incomplete(self) -> list[dict[str, Any]]:
        """Runs with no end state (crashed before close)."""
        return [r for r in self.read_all() if not r.get("ended_at")]

    def last_successful_retrieval(self, source: str | None = None) -> str | None:
        """Latest ended SUCCEEDED/PARTIAL/DUP retrieval time for factual reporting."""
        candidates = [
            r
            for r in self.read_all()
            if r.get("status") in ("SUCCEEDED", "PARTIAL", "DUPLICATE")
            and r.get("ended_at")
            and (source is None or r.get("source") == source)
        ]
        if not candidates:
            return None
        return str(sorted(c["ended_at"] for c in candidates)[-1])
