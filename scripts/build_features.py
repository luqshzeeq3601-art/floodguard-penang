"""Build feature tables from one Phase 2 processed dataset in ONE offline run: print JSON, exit.

Reads processed/observations/v1/<dataset_version>/, extracts point-in-time rainfall, water-level,
weather, temporal and spatial features, and writes:
    <output_root>/<dataset_version>/v1/
        rainfall_features.jsonl
        water_level_features.jsonl
        paired_site_features.jsonl
        feature_manifest.json

Every output is write-once (rerunning with identical inputs is a no-op).
No network, no loop, no scheduler.
Design: docs/FEATURE_ENGINEERING.md.

Outputs derived from JPS data are PERMISSION REQUIRED and stay local (git-ignored data/features/).

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\build_features.py --dataset DIR

Exit codes: 0 built or already present, 2 rejected (contract violation, unreadable input,
existing output with different content).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from floodguard.analysis.dataset import (
    AnalysisContractError,
    load_processed_dataset,
    load_station_context,
    sha256,
)
from floodguard.features.pipeline import run_feature_pipeline

ROOT = Path(__file__).resolve().parents[1]


def load_threshold_reference(
    station_master_dir: Path,
) -> tuple[dict[str, list[dict[str, Any]]], str]:
    thresh_file = station_master_dir / "thresholds.csv"
    if not thresh_file.is_file():
        return {}, ""
    raw = thresh_file.read_bytes()
    digest = sha256(raw)
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    by_sensor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        val_str = r.get("value_m", "")
        if val_str and val_str.strip():
            by_sensor[r["fg_sensor_id"]].append(
                {
                    "threshold_type": r["threshold_type"],
                    "value_m": float(val_str),
                    "threshold_source": r.get("threshold_source"),
                    "captured_at": r.get("captured_at"),
                }
            )
    return dict(by_sensor), digest


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build feature tables (offline, one run).")
    ap.add_argument("--dataset", type=Path, required=True, help="processed dataset dir/manifest")
    ap.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "data" / "features",
        help="output root directory (git-ignored)",
    )
    ap.add_argument(
        "--station-master-dir",
        type=Path,
        default=ROOT / "data" / "local" / "station_master",
        help="station master directory (sensors.csv, sites.csv, thresholds.csv)",
    )
    args = ap.parse_args(argv)

    try:
        ds = load_processed_dataset(args.dataset)
        meta, master_sha = load_station_context(ds.manifest, args.station_master_dir)
        thresh_map, thresh_sha = load_threshold_reference(args.station_master_dir)

        result = run_feature_pipeline(
            ds,
            args.output_root,
            station_metadata=meta,
            station_master_sha256=master_sha,
            threshold_reference=thresh_map,
            threshold_reference_sha256=thresh_sha,
        )
    except (AnalysisContractError, OSError, KeyError, ValueError) as e:
        print(f"REJECTED: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    art = result.manifest["artifacts"]
    print(
        json.dumps(
            {
                "dataset_version": result.dataset_version,
                "feature_schema_version": result.feature_schema_version,
                "output_dir": str(result.output_dir),
                "files_written": len(result.written),
                "rainfall_feature_rows": art["rainfall_features"]["rows"],
                "water_level_feature_rows": art["water_level_features"]["rows"],
                "paired_site_feature_rows": art["paired_site_features"]["rows"],
                "feature_count": result.manifest["feature_registry"]["feature_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
