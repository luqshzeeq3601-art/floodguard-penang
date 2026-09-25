"""Produce baseline EDA figures for rainfall, water level, missingness, and threshold events.

Design: docs/BASELINE_EDA_FIGURES.md.

Reads machine-readable analysis outputs from:
- data/analysis/rainfall/<dataset_version>/rainfall_distribution.json
- data/analysis/water_level/<dataset_version>/water_level_trends.json
- data/analysis/missingness/<dataset_version>/missingness.json
- data/analysis/events/<dataset_version>/threshold_events.json

Plotting rules:
- Factual and professional styling.
- Gaps in water level are NEVER bridged with interpolated lines; missing periods are shown as gaps.
- Threshold lines are explicitly labeled as CURRENT_REFERENCE_ONLY.
- Outputs are saved to git-ignored data/analysis/figures/<dataset_version>/ (PNG format).

Pure offline script.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from floodguard.analysis.figures import produce_all_figures

ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Produce baseline EDA figures (offline).")
    ap.add_argument("--dataset", type=Path, required=True, help="processed dataset dir/manifest")
    ap.add_argument("--analysis-root", type=Path, default=ROOT / "data" / "analysis")
    ap.add_argument("--output-root", type=Path, default=ROOT / "data" / "analysis" / "figures")
    args = ap.parse_args(argv)

    ds_dir = args.dataset.parent if args.dataset.name == "dataset_manifest.json" else args.dataset
    try:
        manifest = json.loads((ds_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
        d_ver = manifest["dataset_version"]
        target_dir = args.output_root / d_ver
        res = produce_all_figures(args.analysis_root, ds_dir, target_dir)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
