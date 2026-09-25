"""Validate the units of ONE raw batch file into a separate derived JSONL, print a report, exit.

Reads a ``<sha256>.records.jsonl`` or ``<sha256>.quarantine.jsonl`` from the raw store
(read-only), checks it against its SUCCEEDED manifest entry (``records_sha256`` /
``quarantine_sha256``) and writes ``<sha256>.[quarantine.]units.jsonl`` under the derived root at
the same relative path: one row per validated field (primary value, thresholds, other fields the
unit policy names). Rows join to other derived layers on ``ingestion_batch_id`` +
``source_row_index``. Write-once (``floodguard.ingestion.storage``): a rerun with the same inputs
is a no-op; different content at that path is refused. No network. Policy: docs/UNIT_POLICY.md.

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\validate_units.py --records PATH_TO_JSONL

Exit codes: 0 written or already present, 2 rejected (nothing written).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from floodguard.ingestion import manifest, storage
from floodguard.ingestion.contracts import BatchStatus
from floodguard.ingestion.hashing import jsonl_bytes, sha256_hex
from floodguard.preprocessing.units import POLICY_VERSION, validate_record

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = ROOT / "data" / "raw"
DEFAULT_OUT_ROOT = ROOT / "data" / "interim" / "units" / "v1"
# input suffix -> (manifest path key, manifest hash key, output suffix)
KINDS = {
    ".records.jsonl": ("records_path", "records_sha256", ".units.jsonl"),
    ".quarantine.jsonl": ("quarantine_path", "quarantine_sha256", ".quarantine.units.jsonl"),
}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate units of one raw batch (offline).")
    ap.add_argument("--records", type=Path, required=True, help="<sha256>.records|quarantine.jsonl")
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
    suffix = next((s for s in KINDS if rel.name.endswith(s)), None)
    if suffix is None:
        return reject(f"not a records or quarantine file: {rel.name}")
    path_key, hash_key, out_suffix = KINDS[suffix]
    try:
        data = storage.fs_path(args.records).read_bytes()
        entry = next(
            (
                e
                for e in manifest.read_entries(raw_root)
                if e.get("status") == BatchStatus.SUCCEEDED and e.get(path_key) == str(rel)
            ),
            None,
        )
    except (OSError, manifest.ManifestError) as e:
        return reject(f"{type(e).__name__}: {e}")
    if entry is None:
        return reject(f"no SUCCEEDED manifest entry for {rel}")
    if sha256_hex(data) != entry.get(hash_key):
        return reject(f"{rel} does not match its manifest {hash_key}")

    try:
        records = [json.loads(x) for x in data.decode("utf-8").splitlines()]
        rows = [row for rec in records for row in validate_record(rec)]
    except (ValueError, KeyError) as e:
        return reject(f"{type(e).__name__}: {e}")
    out_rel = rel.with_name(rel.name.removesuffix(suffix) + out_suffix)
    try:
        written = storage.write_artifacts(
            args.out_root, [storage.Artifact(out_rel, jsonl_bytes(rows))]
        )
    except OSError as e:  # incl. ImmutableArtifactError: existing output differs
        return reject(f"{type(e).__name__}: {e}")

    def count(key: str, subset: list[dict[str, object]] = rows) -> dict[str, int]:
        return dict(sorted(Counter(str(r[key]) for r in subset).items()))

    report = {
        "input_path": str(rel),
        "output_path": str(out_rel),
        "written": bool(written),
        "unit_policy_version": POLICY_VERSION,
        "records": len(records),
        "rows": len(rows),
        "unit_validation_status": count("unit_validation_status"),
        "measurement_type": count("measurement_type"),
        "value_parse_status": count("value_parse_status"),
        "not_promoted_fields": count(
            "source_field",
            [r for r in rows if r["unit_validation_status"] == "UNKNOWN_MEASUREMENT_SEMANTICS"],
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
