"""Water-level trend analysis of ONE processed dataset, in one offline run: print, exit.

Reads processed/observations/v1/<dataset_version>/ (directory or its dataset_manifest.json),
verifies the Phase 2 contract (manifest hash, checks, schemas), summarises WATER_LEVEL (m) rows
per station (levels, coverage, continuity, backward consecutive changes) and writes
<output-root>/<dataset_version>/water_level_trends.json (write-once; a rerun is a no-op).
No network access. Design: docs/WATER_LEVEL_TREND_ANALYSIS.md.

Outputs derived from JPS data are PERMISSION REQUIRED and stay local (git-ignored data/analysis/).

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\analyze_water_level.py --dataset DIR

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
from floodguard.analysis.water_level import analyze, load_threshold_reference, write_summary

ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Analyse water-level trends (offline, one run).")
    ap.add_argument("--dataset", type=Path, required=True, help="processed dataset dir/manifest")
    ap.add_argument("--output-root", type=Path, default=ROOT / "data" / "analysis" / "water_level")
    ap.add_argument(
        "--station-master-dir",
        type=Path,
        default=ROOT / "data" / "local" / "station_master",
        help="optional; adds source ID, district, basin and current thresholds (reference only)",
    )
    args = ap.parse_args(argv)
    sm = args.station_master_dir
    try:
        ds = load_processed_dataset(args.dataset)
        meta, master_sha = load_station_context(ds.manifest, sm)
        thresholds, thresholds_sha = (
            load_threshold_reference(sm) if (sm / "thresholds.csv").is_file() else (None, None)
        )
        doc = analyze(
            ds.rows,
            dataset_version=ds.dataset_version,
            observations_sha256=ds.observations_sha256,
            quality_summary=ds.quality_summary,
            station_metadata=meta,
            station_master_sha256=master_sha,
            threshold_reference=thresholds,
            threshold_reference_sha256=thresholds_sha,
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
                "stations_analysed": doc["network"]["stations_analysed"],
                "water_level_rows": doc["input"]["water_level_rows"],
                "evidence_levels_supported": doc["evidence_levels_supported"],
                "sufficiency": {k: v["status"] for k, v in doc["sufficiency"].items()},
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
