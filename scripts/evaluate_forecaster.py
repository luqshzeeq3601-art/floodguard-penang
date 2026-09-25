"""Evaluate one saved Phase 6 forecaster on caller-supplied rows: print JSON, exit.

Loads a trusted local artifact directory (written by
scripts/train_forecaster.py) and evaluates it once on canonical rows or a
synthetic fixture segment. The caller is responsible for holdout: rows given
here are scored as-is, never split, never refit. In particular
``--synthetic`` generates a different time segment than the training script
so synthetic scores are not training-set scores. Horizon mismatch between
artifact and request is rejected.

Usage (repo root):
    .\\.venv\\Scripts\\python.exe scripts\\evaluate_forecaster.py --artifact DIR
        --synthetic --horizon 30

No network, no Docker, no CUDA. CPU only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from floodguard.forecasting.artifacts import load_forecast_artifact_trusted
from floodguard.forecasting.dataset import ForecastDatasetConfig, build_forecast_samples
from floodguard.forecasting.evaluation import persistence_skill, score_predictions
from floodguard.forecasting.preprocessing import (
    ForecastPreprocessor,
    StationScaler,
    require_station,
)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate a saved Phase 6 forecaster (offline).")
    ap.add_argument("--artifact", type=Path, required=True)
    ap.add_argument("--input", type=Path, default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--horizon", type=int, choices=(30, 60, 120), default=30)
    args = ap.parse_args(argv)

    try:
        estimators, metadata = load_forecast_artifact_trusted(args.artifact)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    artifact_horizon = metadata.get("horizon_minutes")
    if artifact_horizon is not None and int(artifact_horizon) != args.horizon:
        print(
            f"REJECTED: artifact horizon +{artifact_horizon}m != requested +{args.horizon}m.",
            file=sys.stderr,
        )
        return 2

    if args.synthetic:
        from datetime import UTC as _UTC
        from datetime import datetime as _datetime

        from floodguard.forecasting.synthetic import make_rise_series

        # A different segment than scripts/train_forecaster.py generates, so
        # synthetic evaluation is not a training-set score (review M3).
        rows: list[dict[str, Any]] = make_rise_series(
            n=240, start=_datetime(2030, 6, 1, tzinfo=_UTC)
        )
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

    lookback = int(metadata.get("lookback_minutes", 120))
    architecture = metadata.get("model_architecture", {})
    if not isinstance(architecture, dict) or "lags" not in architecture:
        print("REJECTED: artifact lineage lacks model_architecture.lags.", file=sys.stderr)
        return 2
    lag_offsets = tuple(int(v) for v in architecture["lags"])
    if max(lag_offsets) > lookback:
        print(
            f"REJECTED: artifact max lag {max(lag_offsets)}m exceeds lookback {lookback}m.",
            file=sys.stderr,
        )
        return 2
    per_horizon, _ = build_forecast_samples(
        rows,
        ForecastDatasetConfig(
            lookback_minutes=lookback, dataset_version=str(metadata.get("dataset_version", "eval"))
        ),
    )
    samples = per_horizon[args.horizon]
    pre_dict = metadata.get("preprocessing", {}).get("scalers", {})
    preprocessor = ForecastPreprocessor(
        scalers={
            sid: StationScaler(
                fg_sensor_id=sid,
                mean_m=float(entry["mean_m"]),
                std_m=float(entry["std_m"]),
            )
            for sid, entry in pre_dict.items()
        }
    )
    from floodguard.forecasting.statistical import StatisticalConfig as _EvalLagConfig

    lag_config = _EvalLagConfig(lag_offsets_minutes=lag_offsets)
    family = str(metadata.get("model_family", "unknown"))
    evidence = str(metadata.get("evidence_level", "LOCAL_REAL_DATA_DIAGNOSTIC"))

    evaluations: dict[str, Any] = {}
    skills: dict[str, Any] = {}
    for sensor_id in sorted({s.fg_sensor_id for s in samples}):
        try:
            scaler = require_station(preprocessor, sensor_id)
        except ValueError as exc:
            evaluations[sensor_id] = {"status": "REJECTED_UNSEEN_STATION", "reason": str(exc)}
            continue
        estimator = estimators.get(sensor_id)
        if estimator is None:
            evaluations[sensor_id] = {"status": "REJECTED_UNSEEN_STATION", "reason": "no model"}
            continue
        station_rows = {
            str(r["observation_time_utc"]): scaler.transform(float(str(r["value"])))
            for r in rows
            if str(r.get("fg_sensor_id")) == sensor_id
            and r.get("measurement_type") == "WATER_LEVEL"
            and r.get("usable")
            and isinstance(r.get("value"), (int, float))
        }
        vlist = [s for s in samples if s.fg_sensor_id == sensor_id]
        val_origins = [s.origin_utc for s in vlist]
        # Origin-exclusive lag features via the library builders (review M1).
        if family == "linear_ar":
            from floodguard.forecasting.statistical import build_lag_matrix as _eval_lags

            x_eval, kept = _eval_lags(station_rows, val_origins, lag_config)
            expected_features = len(lag_config.lag_offsets_minutes)
        else:
            from floodguard.forecasting.gradient_boosting import (
                build_lag_delta_matrix as _eval_lag_delta,
            )

            x_eval, kept = _eval_lag_delta(
                station_rows, val_origins, lag_config.lag_offsets_minutes
            )
            expected_features = 2 * len(lag_config.lag_offsets_minutes) - 1
        trained_features = getattr(estimator, "n_features_in_", expected_features)
        if int(trained_features) != expected_features:
            print(
                f"REJECTED: station {sensor_id}: artifact expects {expected_features} "
                f"features but estimator trained on {trained_features}.",
                file=sys.stderr,
            )
            return 2
        import numpy as np

        target_by_origin = {s.origin_utc: s.target_level_m for s in vlist}
        origin_by_origin = {s.origin_utc: s.origin_level_m for s in vlist}
        preds: list[float] = []
        trues: list[float] = []
        persist_preds: list[float] = []
        for features, origin in zip(x_eval, kept, strict=True):
            preds.append(scaler.inverse(float(estimator.predict(np.asarray([features]))[0])))
            trues.append(target_by_origin[origin])
            persist_preds.append(origin_by_origin[origin])
        model_score = score_predictions(
            trues,
            preds,
            fg_sensor_id=sensor_id,
            model_family=family,
            horizon_minutes=args.horizon,
            evidence_level=evidence,
        )
        persist_score = score_predictions(
            trues,
            persist_preds,
            fg_sensor_id=sensor_id,
            model_family="persistence",
            horizon_minutes=args.horizon,
            evidence_level=evidence,
        )
        evaluations[sensor_id] = model_score.to_dict()
        skills[sensor_id] = persistence_skill(model_score.mae_m, persist_score.mae_m)
    print(
        json.dumps(
            {
                "status": "EVALUATED",
                "artifact": str(args.artifact),
                "model_family": family,
                "horizon_minutes": args.horizon,
                "device": "cpu",
                "evaluation_test": evaluations,
                "persistence_skill_mae": skills,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
