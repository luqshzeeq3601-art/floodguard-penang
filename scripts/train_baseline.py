"""Evaluate persistence/rule baselines in ONE offline CPU run: print JSON, exit.

Reads a joined feature/label JSONL (one JSON object per row, as produced by
``join_features_and_labels``) or ``--synthetic`` deterministic fixture rows.
Evaluates persistence regression WL(t+h)=WL(t) and the rule classifier
independently per horizon (+30, +60, +120) inside chronological
train/validation/test partitions (same +120-minute embargo as the learned
models), so rule thresholds are frozen before test scoring (review M3).
Missing future targets are excluded, never zero-filled.

Usage (repo root):
    .\\.venv\\Scripts\\python.exe scripts\\train_baseline.py --synthetic
    .\\.venv\\Scripts\\python.exe scripts\\train_baseline.py --input joined.jsonl

No network, no Docker, no CUDA. CPU only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime as _datetime
from datetime import timedelta as _timedelta
from pathlib import Path
from typing import Any

from floodguard.modeling import HORIZONS_MINUTES
from floodguard.modeling.baselines import (
    RuleConfig,
    persistence_forecast_for_row,
    rule_predict_row,
)
from floodguard.modeling.metrics import classification_metrics, regression_metrics
from floodguard.modeling.splits import SplitConfig, chronological_split


def _load_rows(path: Path | None, synthetic: bool) -> list[dict[str, Any]]:
    if synthetic:
        from floodguard.modeling.synthetic import make_synthetic_joined_rows

        return make_synthetic_joined_rows()
    if path is None:
        raise ValueError("--input is required unless --synthetic is given")
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train persistence/rule baselines (offline).")
    ap.add_argument("--input", type=Path, default=None, help="joined feature/label JSONL")
    ap.add_argument("--synthetic", action="store_true", help="use SYNTHETIC_TEST_ONLY rows")
    ap.add_argument("--rise-rate-threshold", type=float, default=0.30)
    ap.add_argument("--rainfall-threshold", type=float, default=10.0)
    args = ap.parse_args(argv)

    try:
        rows = _load_rows(args.input, args.synthetic)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    rule_cfg = RuleConfig(
        rise_rate_threshold_m_per_h=args.rise_rate_threshold,
        rainfall_sum_threshold_mm=args.rainfall_threshold,
    )
    evidence = "SYNTHETIC_SOFTWARE_VALIDATION" if args.synthetic else "LOCAL_REAL_DATA_DIAGNOSTIC"
    report: dict[str, Any] = {
        "schema": "baseline_report/v1",
        "n_rows": len(rows),
        "synthetic": bool(args.synthetic),
        "device": "cpu",
        "evidence_level": evidence,
        "horizons": {},
    }
    # Chronological partitions with horizon embargo; rule thresholds are
    # configuration (frozen before scoring), evaluated per partition (M3).
    times = sorted(
        str(r.get("prediction_origin_utc", "")) for r in rows if r.get("prediction_origin_utc")
    )
    partitions: dict[str, list[dict[str, Any]]] = {"all": rows}
    split_dict: dict[str, Any] | None = None
    if times:
        train_end = times[len(times) * 2 // 3]
        val_end = times[len(times) * 5 // 6]
        split = chronological_split(
            rows, SplitConfig(train_end_utc=train_end, validation_end_utc=val_end)
        )
        split_dict = split.to_dict()
        train_end_dt = _datetime.fromisoformat(train_end)
        val_end_dt = _datetime.fromisoformat(val_end)
        embargo = _timedelta(minutes=120)
        train_cutoff = train_end_dt - embargo
        val_cutoff = val_end_dt - embargo
        train_p: list[dict[str, Any]] = []
        val_p: list[dict[str, Any]] = []
        test_p: list[dict[str, Any]] = []
        for row in rows:
            origin = _datetime.fromisoformat(str(row["prediction_origin_utc"]))
            if origin <= train_end_dt and origin <= train_cutoff:
                train_p.append(row)
            elif train_end_dt < origin <= val_end_dt and origin <= val_cutoff:
                val_p.append(row)
            elif origin > val_end_dt:
                test_p.append(row)
        partitions = {"train": train_p, "validation": val_p, "test": test_p, "all": rows}
    report["split"] = split_dict
    for horizon in HORIZONS_MINUTES:
        horizon_entry: dict[str, Any] = {}
        for part_name, part_rows in partitions.items():
            horizon_entry[part_name] = _evaluate_partition(part_rows, horizon, rule_cfg, evidence)
        report["horizons"][str(horizon)] = horizon_entry
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _evaluate_partition(
    rows: list[dict[str, Any]], horizon: int, rule_cfg: RuleConfig, evidence: str
) -> dict[str, Any]:
    """Evaluate persistence + rule on one partition (missing excluded)."""
    forecasts = [persistence_forecast_for_row(r, horizon) for r in rows]
    evaluable = [f for f in forecasts if f.status == "TARGET_EVALUATED"]
    y_true_m = [f.actual_level_m for f in evaluable if f.actual_level_m is not None]
    y_pred_m = [f.predicted_level_m for f in evaluable if f.predicted_level_m is not None]
    reg = regression_metrics(
        [float(v) for v in y_true_m],
        [float(v) for v in y_pred_m],
        horizon,
        evidence_level=evidence,
    )
    y_true: list[int] = []
    y_pred: list[int] = []
    y_score: list[float] = []
    unevaluable_rule = 0
    label_col = f"target_plus_{horizon}m_exceed_waspada"
    status_col = f"target_plus_{horizon}m_status"
    for row in rows:
        if row.get(status_col) != "TARGET_EVALUATED" or row.get(label_col) is None:
            continue
        pred = rule_predict_row(row, rule_cfg)
        if pred is None:
            unevaluable_rule += 1
            continue
        y_true.append(int(row[label_col]))
        y_pred.append(pred)
        y_score.append(float(pred))
    clf = classification_metrics(y_true, y_pred, y_score or None, horizon, evidence_level=evidence)
    return {
        "persistence": reg.to_dict(),
        "rule": clf.to_dict(),
        "rule_unevaluable_origins": unevaluable_rule,
    }


if __name__ == "__main__":
    sys.exit(main())
