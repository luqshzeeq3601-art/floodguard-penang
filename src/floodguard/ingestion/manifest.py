"""Central append-only JSON Lines manifest of raw batches.

Path: ``<raw_root>/_manifest/raw_batches.jsonl``. One line per ingestion attempt (SUCCEEDED,
FAILED or DUPLICATE). Appends are atomic: the existing bytes plus the new line are written to a
temp file and swapped in with ``os.replace``, after checking that the existing content is
unchanged (earlier lines are never rewritten).
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from floodguard.ingestion.contracts import MANIFEST_SCHEMA_VERSION, BatchStatus
from floodguard.ingestion.hashing import canonical_json
from floodguard.ingestion.storage import fs_path

MANIFEST_RELPATH = Path("_manifest") / "raw_batches.jsonl"

MANIFEST_FIELDS = (
    "manifest_schema_version",
    "run_id",
    "batch_id",
    "status",
    "source",
    "dataset",
    "partition",
    "source_reference",
    "retrieved_at",
    "ingested_at",
    "payload_sha256",
    "payload_bytes",
    "payload_path",
    "records_path",
    "quarantine_path",
    "records_sha256",
    "quarantine_sha256",
    "input_rows",
    "accepted_rows",
    "quarantined_rows",
    "source_duplicates_observed",
    "parser_name",
    "parser_version",
    "record_schema_version",
    "duplicate_of_run_id",
    "error_reason",
)


class ManifestError(RuntimeError):
    """The manifest is unreadable or was modified concurrently."""


def manifest_path(raw_root: Path) -> Path:
    return fs_path(raw_root / MANIFEST_RELPATH)


def read_entries(raw_root: Path) -> list[dict[str, Any]]:
    path = manifest_path(raw_root)
    if not path.exists():
        return []
    entries = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            raise ManifestError(f"{path}:{n}: unreadable manifest line") from e
        if not isinstance(entry, dict):
            raise ManifestError(f"{path}:{n}: manifest line is not an object")
        entries.append(entry)
    return entries


def find_succeeded(
    raw_root: Path, source: str, dataset: str, partition: str | None, payload_sha256: str
) -> dict[str, Any] | None:
    """The SUCCEEDED entry for this exact payload of this source dataset (+ partition), if any."""
    for e in read_entries(raw_root):
        if (
            e.get("status") == BatchStatus.SUCCEEDED
            and e.get("source") == source
            and e.get("dataset") == dataset
            and e.get("partition") == partition
            and e.get("payload_sha256") == payload_sha256
        ):
            return e
    return None


def append_entry(raw_root: Path, entry: dict[str, Any]) -> None:
    unknown = set(entry) - set(MANIFEST_FIELDS)
    if unknown:
        raise ManifestError(f"unknown manifest fields: {sorted(unknown)}")
    full = {k: entry.get(k) for k in MANIFEST_FIELDS}
    full["manifest_schema_version"] = MANIFEST_SCHEMA_VERSION
    path = manifest_path(raw_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    before = path.read_bytes() if path.exists() else b""
    if before and not before.endswith(b"\n"):
        raise ManifestError(f"{path}: last line is incomplete; refusing to append")
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with tmp.open("xb") as f:
            f.write(before + (canonical_json(full) + "\n").encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        current = path.read_bytes() if path.exists() else b""
        if current != before:
            raise ManifestError(f"{path} changed during append (concurrent writer?)")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
