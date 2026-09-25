"""Missingness analysis of ONE processed dataset, in one offline run: print, exit.

Reads processed/observations/v1/<dataset_version>/ (directory or its dataset_manifest.json),
verifies the Phase 2 contract (manifest hash, checks, schemas, station-master lineage), summarises
missing observations per sensor, measurement type and cadence window (history captures only;
listing rows as point-in-time counts) and writes
<output-root>/<dataset_version>/missingness.json (write-once; a rerun is a no-op).
No network access. Design: docs/MISSINGNESS_OUTAGE_ANALYSIS.md.

Outputs derived from JPS data are PERMISSION REQUIRED and stay local (git-ignored data/analysis/).

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\analyze_missingness.py --dataset DIR

Exit codes: 0 written or already present, 2 rejected (contract violation, unreadable input,
existing output with different content).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from floodguard.analysis.dataset import (
    AnalysisContractError,
    load_processed_dataset,
    load_station_context,
)
from floodguard.analysis.missingness import analyze, write_summary

ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Analyse missingness (offline, one run).")
    ap.add_argument("--dataset", type=Path, required=True, help="processed dataset dir/manifest")
    ap.add_argument("--output-root", type=Path, default=ROOT / "data" / "analysis" / "missingness")
    ap.add_argument(
        "--station-master-dir",
        type=Path,
        default=ROOT / "data" / "local" / "station_master",
        help="optional; adds source ID, district, basin; must be the dataset's station master",
    )
    args = ap.parse_args(argv)
    try:
        ds = load_processed_dataset(args.dataset)
        meta, master_sha = load_station_context(ds.manifest, args.station_master_dir)
        doc = analyze(
            ds.rows,
            dataset_version=ds.dataset_version,
            observations_sha256=ds.observations_sha256,
            quality_summary=ds.quality_summary,
            manifest=ds.manifest,
            station_metadata=meta,
            station_master_sha256=master_sha,
        )
        path, written = write_summary(doc, args.output_root)
    except (AnalysisContractError, OSError, KeyError, ValueError) as e:
        # OSError includes ImmutableArtifactError (existing output differs)
        print(f"REJECTED: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "dataset_version": doc["dataset_version"],
                "output": str(path),
                "written": written,
                "rows_by_measurement_type": doc["input"]["rows_by_measurement_type"],
                "evidence_levels_supported": doc["evidence_levels_supported"],
                "sufficiency": {
                    mt: {k: v["status"] for k, v in entries.items()}
                    for mt, entries in doc["sufficiency"].items()
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
