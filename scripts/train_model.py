"""Train one Phase 5 classifier in ONE offline CPU run: print JSON, exit.

Flow: joined rows -> feasibility gate -> chronological split (with +120-min
purge/embargo) -> eligible features -> train-only preprocessing -> model fit
on train -> frozen validation evaluation -> local artifact with lineage.

Usage (repo root):
    .\\.venv\\Scripts\\python.exe scripts\\train_model.py --synthetic --model logistic --horizon 30
    .\\.venv\\Scripts\\python.exe scripts\\train_model.py --input joined.jsonl --model forest

Models: logistic | forest | xgboost. Horizons: 30 | 60 | 120.
No network, no Docker, no CUDA. CPU only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from floodguard.modeling.artifacts import ArtifactMetadata, artifact_dir, save_artifact
from floodguard.modeling.feasibility import FeasibilityConfig, assess_feasibility
from floodguard.modeling.features import EligibilityPolicy, select_eligible_features
from floodguard.modeling.labels import extract_horizon_labels
from floodguard.modeling.metrics import classification_metrics
from floodguard.modeling.preprocessing import (
    PreprocessingConfig,
    fit_preprocessor,
    transform_rows,
)
from floodguard.modeling.splits import SplitConfig, chronological_split

LABEL_VERSION = "labels/v1"
FEATURE_SCHEMA_VERSION = "features/v1"


def _load_rows(path: Path | None, synthetic: bool) -> list[dict[str, Any]]:
    if synthetic:
        from floodguard.modeling.synthetic import make_synthetic_joined_rows

        return make_synthetic_joined_rows(n_origins=120)
    if path is None:
        raise ValueError("--input is required unless --synthetic is given")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _split_feature_types(
    train_rows: list[dict[str, Any]], eligible: list[str]
) -> tuple[list[str], list[str]]:
    """Infer numeric vs categorical types from training rows only (review L1)."""
    numeric = [
        c
        for c in eligible
        if train_rows and isinstance(train_rows[0].get(c), (int, float, type(None)))
    ]
    categorical = [c for c in eligible if c not in numeric]
    # Text columns actually holding strings become categoricals.
    text_cols = [c for c in eligible if any(isinstance(r.get(c), str) for r in train_rows)]
    for col in text_cols:
        if col in numeric:
            numeric.remove(col)
        if col not in categorical:
            categorical.append(col)
    return numeric, categorical


def _partition_by_time(
    rows: list[dict[str, Any]], train_end: str, val_end: str, embargo_minutes: int = 120
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int, int]:
    """Partition row indices with the same embargo rule as chronological_split.

    Index-keyed (never a timestamp-keyed dict) so multi-station rows sharing
    one origin are never collapsed (review H1). Returns
    (train, validation, test, purged_train, purged_val).
    """
    from datetime import datetime as _datetime
    from datetime import timedelta as _timedelta

    train_end_dt = _datetime.fromisoformat(train_end)
    val_end_dt = _datetime.fromisoformat(val_end)
    embargo = _timedelta(minutes=embargo_minutes)
    train_cutoff = train_end_dt - embargo
    val_cutoff = val_end_dt - embargo
    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []
    purged_train = 0
    purged_val = 0
    for row in rows:
        origin = _datetime.fromisoformat(str(row["prediction_origin_utc"]))
        if origin <= train_end_dt:
            if origin <= train_cutoff:
                train.append(row)
            else:
                purged_train += 1
        elif origin <= val_end_dt:
            if origin <= val_cutoff:
                val.append(row)
            else:
                purged_val += 1
        else:
            test.append(row)
    return train, val, test, purged_train, purged_val


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train one Phase 5 classifier (offline, CPU).")
    ap.add_argument("--input", type=Path, default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--model", choices=("logistic", "forest", "xgboost"), default="logistic")
    ap.add_argument("--horizon", type=int, choices=(30, 60, 120), default=30)
    ap.add_argument("--output-root", type=Path, default=Path("artifacts/models"))
    ap.add_argument("--dataset-version", default="synthetic-test-v1")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    try:
        rows = _load_rows(args.input, args.synthetic)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print("REJECTED: no rows.", file=sys.stderr)
        return 2

    if args.synthetic:
        feasibility = assess_feasibility(
            rows, FeasibilityConfig(min_positives=2, min_positive_episodes=1)
        )
    else:
        # Real runs use the documented standard gate (review M5).
        feasibility = assess_feasibility(rows, FeasibilityConfig())
    if not feasibility.feasible and not args.synthetic:
        print(json.dumps({"status": feasibility.status, **feasibility.to_dict()}, indent=2))
        return 0

    times = sorted(r["prediction_origin_utc"] for r in rows)
    train_end = times[len(times) * 2 // 3]
    val_end = times[len(times) * 5 // 6]
    split = chronological_split(
        rows, SplitConfig(train_end_utc=train_end, validation_end_utc=val_end)
    )
    # Train on the embargo-respecting partitions (same rule as the reported
    # split); index-keyed so shared timestamps never collapse (review H1).
    train_rows, val_rows, _test_rows, purged_train, purged_val = _partition_by_time(
        rows, train_end, val_end
    )
    assert len(train_rows) + purged_train == split.train.row_count + split.train.purged_row_count
    assert len(val_rows) + purged_val == (
        split.validation.row_count + split.validation.purged_row_count
    )

    eligibility = select_eligible_features(list(rows[0].keys()), EligibilityPolicy())
    numeric, categorical = _split_feature_types(train_rows, list(eligibility.eligible_features))
    pre_cfg = PreprocessingConfig(
        numeric_features=tuple(numeric), categorical_features=tuple(categorical)
    )
    fitted = fit_preprocessor(train_rows, pre_cfg)

    x_train_full = transform_rows(train_rows, fitted)
    x_val_full = transform_rows(val_rows, fitted)
    labels_train = extract_horizon_labels(train_rows, args.horizon)
    labels_val = extract_horizon_labels(val_rows, args.horizon)
    x_train = [x_train_full[i] for i in labels_train.row_indices]
    y_train = list(labels_train.y)
    x_val = [x_val_full[i] for i in labels_val.row_indices]
    y_val = list(labels_val.y)

    if args.model == "logistic":
        from floodguard.modeling.logistic import LogisticConfig, train_logistic

        estimator, meta = train_logistic(
            x_train, y_train, LogisticConfig(random_state=args.seed), horizon_minutes=args.horizon
        )
        family = "logistic_regression"
    elif args.model == "forest":
        from floodguard.modeling.forest import ForestConfig, train_forest

        estimator, meta = train_forest(
            x_train,
            y_train,
            ForestConfig(n_estimators=10, random_state=args.seed),
            horizon_minutes=args.horizon,
        )
        family = "random_forest"
    else:
        from floodguard.modeling.gradient_boosting import (
            GradientBoostingConfig,
            train_gradient_boosting,
        )

        estimator, meta = train_gradient_boosting(
            x_train,
            y_train,
            GradientBoostingConfig(n_estimators=10, random_state=args.seed),
            horizon_minutes=args.horizon,
        )
        family = "xgboost"
    if estimator is None:
        print(json.dumps(meta.to_dict() if hasattr(meta, "to_dict") else meta, indent=2))
        return 0

    import numpy as np

    evidence = "SYNTHETIC_SOFTWARE_VALIDATION" if args.synthetic else "LOCAL_REAL_DATA_DIAGNOSTIC"
    scores_val = [float(p[1]) for p in estimator.predict_proba(np.asarray(x_val))] if x_val else []
    preds_val = [1 if s >= 0.5 else 0 for s in scores_val]
    evaluation = classification_metrics(
        y_val, preds_val, scores_val or None, args.horizon, evidence_level=evidence
    )

    artifact_meta = ArtifactMetadata(
        model_family=family,
        run_id=f"{family}-plus-{args.horizon}m-seed{args.seed}",
        horizon_minutes=args.horizon,
        dataset_version=args.dataset_version,
        observations_hash="synthetic" if args.synthetic else "local",
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        label_version=LABEL_VERSION,
        split_definition=f"train_end={train_end};val_end={val_end};embargo=120m",
        training_timestamp_utc=datetime.now(UTC).isoformat(),
        random_seed=args.seed,
        feature_names=tuple(eligibility.eligible_features),
        feature_eligibility_policy="standard historical training",
        preprocessing=fitted.to_dict(),
        class_weighting=None,
        hyperparameters=dict(meta.get("config", {})) if isinstance(meta, dict) else {},
        library_versions={"device": "cpu"},
        device="cpu",
        evidence_level=evidence,
    )
    saved = save_artifact(args.output_root, estimator, artifact_meta)
    _ = artifact_dir  # keep import referenced for lineage layout docs
    print(
        json.dumps(
            {
                "status": "TRAINED",
                "model_family": family,
                "horizon_minutes": args.horizon,
                "artifact_dir": str(saved),
                "split": split.to_dict(),
                "feasibility": feasibility.to_dict(),
                "evaluation_validation": evaluation.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
