"""Normalise the station IDs of ONE raw batch file into a separate derived JSONL, report, exit.

Reads a ``<sha256>.records.jsonl`` or ``<sha256>.quarantine.jsonl`` from the raw store
(read-only), checks it against its SUCCEEDED manifest entry (``records_sha256`` /
``quarantine_sha256``), re-resolves every row with the station master and writes
``<sha256>.[quarantine.]station_ids.jsonl`` under the derived root at the same relative path.
Write-once (``floodguard.ingestion.storage``): a rerun with the same inputs is a no-op; different
content at that path (e.g. a rebuilt station master) is refused. No network. Policy:
docs/STATION_MASTER_DESIGN.md section 12.

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\normalize_station_ids.py --records PATH_TO_JSONL

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
from floodguard.ingestion.station_mapping import (
    DEFAULT_SENSORS_CSV,
    SensorMapper,
    StationMappingError,
)
from floodguard.preprocessing.station_ids import normalize_record, raw_mapping_conflict

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = ROOT / "data" / "raw"
DEFAULT_OUT_ROOT = ROOT / "data" / "interim" / "station_ids" / "v1"
DEFAULT_STATION_MASTER = ROOT / DEFAULT_SENSORS_CSV
# input suffix -> (manifest path key, manifest hash key, output suffix)
KINDS = {
    ".records.jsonl": ("records_path", "records_sha256", ".station_ids.jsonl"),
    ".quarantine.jsonl": ("quarantine_path", "quarantine_sha256", ".quarantine.station_ids.jsonl"),
}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Normalise station IDs of one raw batch (offline).")
    ap.add_argument("--records", type=Path, required=True, help="<sha256>.records|quarantine.jsonl")
    ap.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    ap.add_argument("--station-master", type=Path, default=DEFAULT_STATION_MASTER)
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
        mapper = SensorMapper.from_csv(args.station_master)
        data = storage.fs_path(args.records).read_bytes()
        entry = next(
            (
                e
                for e in manifest.read_entries(raw_root)
                if e.get("status") == BatchStatus.SUCCEEDED and e.get(path_key) == str(rel)
            ),
            None,
        )
    except (OSError, StationMappingError, manifest.ManifestError) as e:
        return reject(f"{type(e).__name__}: {e}")
    if entry is None:
        return reject(f"no SUCCEEDED manifest entry for {rel}")
    if sha256_hex(data) != entry.get(hash_key):
        return reject(f"{rel} does not match its manifest {hash_key}")
    if entry.get("source") not in mapper.sources:
        return reject(f"no station master for source {entry.get('source')!r}")

    try:
        rows = [normalize_record(json.loads(x), mapper) for x in data.decode("utf-8").splitlines()]
    except (ValueError, KeyError) as e:
        return reject(f"{type(e).__name__}: {e}")
    conflicts = [r["source_row_index"] for r in rows if raw_mapping_conflict(r)]
    if conflicts:  # impossible under one ID recipe: fail closed instead of writing either value
        return reject(f"raw and derived fg_sensor_id conflict at source rows {conflicts}")
    out_rel = rel.with_name(rel.name.removesuffix(suffix) + out_suffix)
    try:
        written = storage.write_artifacts(
            args.out_root, [storage.Artifact(out_rel, jsonl_bytes(rows))]
        )
    except OSError as e:  # incl. ImmutableArtifactError: existing output differs
        return reject(f"{type(e).__name__}: {e}")

    report = {
        "input_path": str(rel),
        "output_path": str(out_rel),
        "written": bool(written),
        "station_master_origin": mapper.origin,
        "rows": len(rows),
        "status": dict(sorted(Counter(r["station_id_mapping_status"] for r in rows).items())),
        "raw_mapping_changed": sum(r["raw_fg_sensor_id"] != r["fg_sensor_id"] for r in rows),
        "distinct_fg_site_id": len({r["fg_site_id"] for r in rows} - {None}),
        "distinct_fg_sensor_id": len({r["fg_sensor_id"] for r in rows} - {None}),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
