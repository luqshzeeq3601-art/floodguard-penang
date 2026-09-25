"""Evaluate the forecasting persistence baseline in ONE offline CPU run.

Reads canonical WATER_LEVEL rows (JSONL, one observation per line) or
``--synthetic`` deterministic fixtures. Builds point-in-time samples and
scores ``WL(t+h) = WL(t)`` per station and horizon (+30/+60/+120) with
sample counts. Missing targets are excluded, never interpolated.

Usage (repo root):
    .\\.venv\\Scripts\\python.exe scripts\\train_forecast_baseline.py --synthetic
    .\\.venv\\Scripts\\python.exe scripts\\train_forecast_baseline.py --input observations.jsonl

No network, no Docker, no CUDA. CPU only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from floodguard.forecasting import EVIDENCE_LOCAL_DIAGNOSTIC, EVIDENCE_SYNTHETIC
from floodguard.forecasting.dataset import ForecastDatasetConfig, build_forecast_samples
from floodguard.forecasting.persistence import score_all_stations


def _load_rows(path: Path | None, synthetic: bool) -> list[dict[str, Any]]:
    if synthetic:
        from floodguard.forecasting.synthetic import make_rise_series

        return make_rise_series(n=200)
    if path is None:
        raise ValueError("--input is required unless --synthetic is given")
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Persistence forecasting baseline (offline).")
    ap.add_argument("--input", type=Path, default=None, help="canonical rows JSONL")
    ap.add_argument("--synthetic", action="store_true", help="use SYNTHETIC_TEST_ONLY rows")
    ap.add_argument("--lookback", type=int, default=120, choices=(60, 120, 180))
    ap.add_argument("--dataset-version", default="synthetic-forecast-v1")
    args = ap.parse_args(argv)

    try:
        rows = _load_rows(args.input, args.synthetic)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    per_horizon, reports = build_forecast_samples(
        rows,
        ForecastDatasetConfig(lookback_minutes=args.lookback, dataset_version=args.dataset_version),
    )
    evidence = EVIDENCE_SYNTHETIC if args.synthetic else EVIDENCE_LOCAL_DIAGNOSTIC
    # Partitioned scoring with the centralized embargo rule so baseline
    # partitions match the learned-model partitions exactly.
    from floodguard.forecasting.dataset import ForecastSample
    from floodguard.modeling.splits import SplitConfig, chronological_split, partition_rows

    partitioned: dict[str, dict[int, list[ForecastSample]]] = {}
    split_report: dict[str, Any] | None = None
    horizon_key = 30
    if per_horizon.get(horizon_key):
        units = sorted({s.origin_utc for s in per_horizon[horizon_key]})
        train_end = units[len(units) * 2 // 3]
        val_end = units[len(units) * 5 // 6]
        config = SplitConfig(train_end_utc=train_end, validation_end_utc=val_end)
        proxy = [{"prediction_origin_utc": s.origin_utc} for s in per_horizon[horizon_key]]
        split_report = chronological_split(proxy, config).to_dict()
        part_rows, part_val, part_test, _, _ = partition_rows(proxy, config)
        keep = (
            {r["prediction_origin_utc"] for r in part_rows},
            {r["prediction_origin_utc"] for r in part_val},
            {r["prediction_origin_utc"] for r in part_test},
        )
        for name, allowed in zip(("train", "validation", "test"), keep, strict=True):
            partitioned[name] = {
                h: [s for s in samples if s.origin_utc in allowed]
                for h, samples in per_horizon.items()
            }
    partitioned["all"] = per_horizon
    scored_partitions = {
        name: score_all_stations(table, evidence_level=evidence)
        for name, table in partitioned.items()
    }
    report = score_all_stations(per_horizon, evidence_level=evidence)
    print(
        json.dumps(
            {
                "status": "BASELINE_EVALUATED",
                "model_family": "persistence",
                "lookback_minutes": args.lookback,
                "dataset_version": args.dataset_version,
                "device": "cpu",
                "build_reports": [r.to_dict() for r in reports],
                "split": split_report,
                "partitions": scored_partitions,
                **report,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
