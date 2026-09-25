"""Evaluate one saved Phase 5 artifact on held-out rows: print JSON, exit.

Loads a trusted local artifact directory (written by scripts/train_model.py
via save_artifact) and evaluates it once on the provided joined rows or a
synthetic fixture. Test rows never refit preprocessing, thresholds, or
calibration; the frozen training preprocessor stored in metadata is applied
unchanged.

Usage (repo root):
    .\\.venv\\Scripts\\python.exe scripts\\evaluate_model.py --artifact DIR --synthetic --horizon 30

No network, no Docker, no CUDA. CPU only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from floodguard.modeling.artifacts import load_artifact_trusted
from floodguard.modeling.labels import extract_horizon_labels
from floodguard.modeling.metrics import classification_metrics
from floodguard.modeling.preprocessing import (
    FittedPreprocessor,
    PreprocessingConfig,
    transform_rows,
)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate a saved Phase 5 artifact (offline).")
    ap.add_argument("--artifact", type=Path, required=True)
    ap.add_argument("--input", type=Path, default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--horizon", type=int, choices=(30, 60, 120), default=30)
    ap.add_argument("--threshold", type=float, default=0.5)
    args = ap.parse_args(argv)

    try:
        estimator, metadata = load_artifact_trusted(args.artifact)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.synthetic:
        from floodguard.modeling.synthetic import make_synthetic_joined_rows

        rows: list[dict[str, Any]] = make_synthetic_joined_rows(n_origins=120)
    elif args.input is not None:
        try:
            rows = [
                json.loads(line)
                for line in args.input.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
    else:
        print("REJECTED: --input or --synthetic is required.", file=sys.stderr)
        return 2

    pre_dict = metadata.get("preprocessing", {})
    cfg_dict = pre_dict.get("config", {})
    fitted = FittedPreprocessor(
        config=PreprocessingConfig(
            numeric_features=tuple(cfg_dict.get("numeric_features", ())),
            categorical_features=tuple(cfg_dict.get("categorical_features", ())),
            scale_numeric=bool(cfg_dict.get("scale_numeric", True)),
        ),
        numeric_medians=dict(pre_dict.get("numeric_medians", {})),
        numeric_means=dict(pre_dict.get("numeric_means", {})),
        numeric_stds=dict(pre_dict.get("numeric_stds", {})),
        categorical_vocabularies={
            k: tuple(v) for k, v in pre_dict.get("categorical_vocabularies", {}).items()
        },
    )
    matrix = transform_rows(rows, fitted)
    labels = extract_horizon_labels(rows, args.horizon)
    x_test = [matrix[i] for i in labels.row_indices]
    y_test = list(labels.y)
    if not x_test:
        print(
            json.dumps(
                {
                    "status": "NOT_EVALUABLE",
                    "reason": "no evaluable test rows for horizon.",
                    "horizon_minutes": args.horizon,
                },
                indent=2,
            )
        )
        return 0
    import numpy as np

    artifact_horizon = metadata.get("horizon_minutes")
    if artifact_horizon is not None and int(artifact_horizon) != args.horizon:
        print(
            f"REJECTED: artifact horizon +{artifact_horizon}m != requested +{args.horizon}m.",
            file=sys.stderr,
        )
        return 2
    scores = [float(p[1]) for p in estimator.predict_proba(np.asarray(x_test))]
    preds = [1 if s >= args.threshold else 0 for s in scores]
    evidence = str(metadata.get("evidence_level", "LOCAL_REAL_DATA_DIAGNOSTIC"))
    evaluation = classification_metrics(
        y_test, preds, scores, args.horizon, evidence_level=evidence
    )
    print(
        json.dumps(
            {
                "status": "EVALUATED",
                "artifact": str(args.artifact),
                "model_family": metadata.get("model_family"),
                "horizon_minutes": args.horizon,
                "threshold": args.threshold,
                "threshold_provenance": (
                    "CLI --threshold (caller-provided operating point; for real "
                    "evaluation use the validation-frozen threshold from "
                    "threshold selection, never a test-tuned value)"
                ),
                "device": "cpu",
                "evaluation_test": evaluation.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
