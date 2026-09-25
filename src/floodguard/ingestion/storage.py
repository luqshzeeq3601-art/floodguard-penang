"""Immutable, content-addressed local raw store.

Layout (relative to the raw root)::

    <source_dir>/<dataset>[/<partition>]/<YYYY>/<MM>/<DD>/
        <payload_sha256>.<ext>                payload, byte-for-byte as received
        <payload_sha256>.records.jsonl        accepted raw records
        <payload_sha256>.quarantine.jsonl     quarantined rows (with reasons)

``partition`` is set only when the payload does not identify its own scope (JPS history: the
whitespace-stripped station key).

``source_dir`` is a short slug (``jps``, ``data_gov_my``); the full source name is in every record
and manifest entry. On Windows every file operation uses the extended-length form of the
absolute path (see ``fs_path``), so deep raw roots are not limited to 260 characters. The date
is the UTC date of ``retrieved_at``.

Writes are temp-file-then-``os.replace`` in the same directory; an existing artifact is never
overwritten (identical bytes are a no-op, different bytes raise ``ImmutableArtifactError``). A
batch's files are placed all-or-nothing: on any error, files this call placed are removed again
and temp files are deleted. Single-writer assumption: one ingestion process per raw root at a time
(no cross-process locking).
"""

from __future__ import annotations

import contextlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

SOURCE_DIRS = {"JPS_PUBLIC_INFOBANJIR": "jps", "DATA_GOV_MY_WEATHER_API": "data_gov_my"}


class ImmutableArtifactError(OSError):
    """An artifact already exists at the target path with different content."""


@dataclass(frozen=True)
class Artifact:
    relpath: PurePosixPath  # relative to the raw root, forward slashes
    data: bytes


def fs_path(path: Path) -> Path:
    """Absolute, normalised path; on Windows in extended-length form (no MAX_PATH limit)."""
    s = os.path.abspath(path)
    if os.name != "nt" or s.startswith("\\\\?\\"):
        return Path(s)
    return Path("\\\\?\\UNC\\" + s[2:] if s.startswith("\\\\") else "\\\\?\\" + s)


def batch_dir(
    source: str, dataset: str, partition: str | None, retrieved_at_utc: datetime
) -> PurePosixPath:
    d = retrieved_at_utc
    parts = (SOURCE_DIRS[source], dataset, *([partition] if partition else []))
    return PurePosixPath(*parts, f"{d:%Y}", f"{d:%m}", f"{d:%d}")


def _write_temp(target: Path, data: bytes) -> Path:
    tmp = target.with_name(f".{uuid.uuid4().hex[:12]}.tmp")  # never longer than the target
    with tmp.open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    return tmp


def write_artifacts(raw_root: Path, artifacts: list[Artifact]) -> list[PurePosixPath]:
    """Place all artifacts or none. Returns the relpaths newly written (identical ones skipped)."""
    temps: list[tuple[Path, Path]] = []
    placed: list[Path] = []
    written: list[PurePosixPath] = []
    try:
        for a in artifacts:
            target = fs_path(raw_root.joinpath(*a.relpath.parts))
            if target.exists():
                if target.read_bytes() != a.data:
                    raise ImmutableArtifactError(
                        f"refusing to overwrite existing artifact with different content: "
                        f"{a.relpath}"
                    )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temps.append((_write_temp(target, a.data), target))
            written.append(a.relpath)
        for tmp, target in temps:
            if target.exists():  # appeared since the check: another writer; do not clobber
                raise ImmutableArtifactError(f"artifact appeared during write: {target}")
            os.replace(tmp, target)
            placed.append(target)
    except BaseException:
        for target in placed:
            with contextlib.suppress(OSError):
                target.unlink()
        raise
    finally:
        for tmp, _ in temps:
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
    return written
