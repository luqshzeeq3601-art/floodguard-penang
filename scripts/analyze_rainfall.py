"""Rainfall-distribution analysis of ONE processed dataset, in one offline run: print, exit.

Reads processed/observations/v1/<dataset_version>/ (directory or its dataset_manifest.json),
verifies the Phase 2 contract (manifest hash, checks, schemas), summarises RAINFALL_INTERVAL
(mm, usable) rows per station and writes
<output-root>/<dataset_version>/rainfall_distribution.json (write-once; a rerun is a no-op).
No network access. Design: docs/RAINFALL_DISTRIBUTION_ANALYSIS.md.

Outputs derived from JPS data are PERMISSION REQUIRED and stay local (git-ignored data/analysis/).

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\analyze_rainfall.py --dataset DIR

Exit codes: 0 written or already present, 2 rejected (contract violation, unreadable input,
existing output with different content).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from floodguard.analysis.dataset import load_processed_dataset, load_station_context
from floodguard.analysis.rainfall import RainfallContractError, analyze, write_summary

ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Analyse rainfall distributions (offline, one run).")
    ap.add_argument("--dataset", type=Path, required=True, help="processed dataset dir/manifest")
    ap.add_argument("--output-root", type=Path, default=ROOT / "data" / "analysis" / "rainfall")
    ap.add_argument(
        "--station-master-dir",
        type=Path,
        default=ROOT / "data" / "local" / "station_master",
        help="optional; adds source ID, district and basin; must be the dataset's station master",
    )
    args = ap.parse_args(argv)
    try:
        ds = load_processed_dataset(args.dataset)
        # only the station master the dataset was built with (shared Phase 3 lineage check)
        meta, master_sha = load_station_context(ds.manifest, args.station_master_dir)
        doc = analyze(
            ds.rows,
            dataset_version=ds.dataset_version,
            observations_sha256=ds.observations_sha256,
            quality_summary=ds.quality_summary,
            station_metadata=meta,
            station_master_sha256=master_sha,
        )
        path, written = write_summary(doc, args.output_root)
    except (RainfallContractError, OSError, KeyError, ValueError) as e:
        # OSError includes ImmutableArtifactError (existing output differs)
        print(f"REJECTED: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "dataset_version": doc["dataset_version"],
                "output": str(path),
                "written": written,
                "stations_analysed": doc["network"]["stations_analysed"],
                "rainfall_interval_rows": doc["input"]["rainfall_interval_rows"],
                "evidence_levels_supported": doc["evidence_levels_supported"],
                "sufficiency": {k: v["status"] for k, v in doc["sufficiency"].items()},
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
