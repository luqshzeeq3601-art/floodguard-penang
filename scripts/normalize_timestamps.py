"""Normalise the timestamps of ONE raw batch into a separate derived JSONL, print a report, exit.

Reads ``<sha256>.records.jsonl`` from the raw store (read-only), checks it against its SUCCEEDED
manifest entry (``records_sha256``), and writes ``<sha256>.timestamps.jsonl`` under the derived
root at the same relative path. Write-once (``floodguard.ingestion.storage``): a rerun with the
same input is a no-op; different content at that path is refused. Policy: docs/TIMESTAMP_POLICY.md.

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\normalize_timestamps.py --records PATH_TO_RECORDS_JSONL

Exit codes: 0 written or already present, 2 rejected (nothing written).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from floodguard.ingestion import manifest, storage
from floodguard.ingestion.contracts import BatchStatus
from floodguard.ingestion.hashing import jsonl_bytes, sha256_hex
from floodguard.preprocessing.timestamps import check_monotonic, normalize_record

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = ROOT / "data" / "raw"
DEFAULT_OUT_ROOT = ROOT / "data" / "interim" / "timestamps" / "v1"
RECORDS_SUFFIX = ".records.jsonl"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normalise timestamps of one raw batch (offline).")
    ap.add_argument("--records", type=Path, required=True, help="<sha256>.records.jsonl")
    ap.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    args = ap.parse_args(argv)

    def reject(msg: str) -> int:
        print(f"REJECTED: {msg}", file=sys.stderr)
        return 2

    raw_root = args.raw_root.resolve()
    if args.out_root.resolve().is_relative_to(raw_root):
        return reject("--out-root must be outside the raw root (raw data is immutable)")
    try:
        rel = PurePosixPath(args.records.resolve().relative_to(raw_root).as_posix())
    except ValueError:
        return reject(f"{args.records} is not under raw root {raw_root}")
    if not rel.name.endswith(RECORDS_SUFFIX):
        return reject(f"not a records file: {rel.name}")
    try:
        data = storage.fs_path(args.records).read_bytes()
        entry = next(
            (
                e
                for e in manifest.read_entries(raw_root)
                if e.get("status") == BatchStatus.SUCCEEDED and e.get("records_path") == str(rel)
            ),
            None,
        )
    except (OSError, manifest.ManifestError) as e:
        return reject(f"{type(e).__name__}: {e}")
    if entry is None:
        return reject(f"no SUCCEEDED manifest entry for {rel}")
    if sha256_hex(data) != entry.get("records_sha256"):
        return reject(f"{rel} does not match its manifest records_sha256")

    try:
        rows = [normalize_record(json.loads(x)) for x in data.decode("utf-8").splitlines()]
    except (ValueError, KeyError) as e:
        return reject(f"{type(e).__name__}: {e}")
    out_rel = rel.with_name(rel.name.removesuffix(RECORDS_SUFFIX) + ".timestamps.jsonl")
    try:
        written = storage.write_artifacts(
            args.out_root, [storage.Artifact(out_rel, jsonl_bytes(rows))]
        )
    except OSError as e:  # incl. ImmutableArtifactError: existing output differs
        return reject(f"{type(e).__name__}: {e}")

    report = {
        "records_path": str(rel),
        "output_path": str(out_rel),
        "written": bool(written),
        "rows": len(rows),
        "flags": dict(Counter(r["timestamp_quality_flag"] for r in rows)),
        "timezone_status": dict(Counter(str(r["timezone_status"]) for r in rows)),
        "monotonicity": (
            asdict(
                check_monotonic([(r["source_row_index"], r["observation_time_utc"]) for r in rows])
            )
            if entry.get("dataset", "").endswith("_history")  # one station, one time series
            else None
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
