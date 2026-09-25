"""Train one Phase 6 forecaster in ONE offline CPU run: print JSON, exit.

Flow: canonical rows -> forecast samples -> chronological origin split
(+120-min embargo, reused Phase 5 rule) -> per-station train-only scaling ->
model fit on train -> frozen validation evaluation -> local artifact.

Models: statistical | xgboost. `--lstm-gru` runs the justification gate
(expected: NOT_JUSTIFIED on current data; no torch added). `--timesfm`
checks benchmark availability (expected: blocked without setup).

Usage (repo root):
    .\\.venv\\Scripts\\python.exe scripts\\train_forecaster.py --synthetic
        --model statistical --horizon 30

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
from floodguard.forecasting.artifacts import ForecastArtifactMetadata, save_forecast_artifact
from floodguard.forecasting.dataset import (
    DATASET_SCHEMA_VERSION,
    ForecastDatasetConfig,
    ForecastSample,
    build_forecast_samples,
)
from floodguard.forecasting.evaluation import score_predictions
from floodguard.forecasting.preprocessing import fit_preprocessor, require_station
from floodguard.modeling.splits import SplitConfig, chronological_split


def _load_rows(path: Path | None, synthetic: bool) -> list[dict[str, Any]]:
    if synthetic:
        from floodguard.forecasting.synthetic import make_rise_series

        return make_rise_series(n=240)
    if path is None:
        raise ValueError("--input is required unless --synthetic is given")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _partition_samples(
    samples: list[ForecastSample], train_end: str, val_end: str, embargo_minutes: int = 120
) -> tuple[
    list[ForecastSample],
    list[ForecastSample],
    list[ForecastSample],
    int,
    int,
]:
    """Partition samples via the centralized Phase 5 embargo rule (no copy).

    Returns ``(train, validation, test, purged_train, purged_val)``. The rule
    lives in ``modeling.splits.partition_rows``; this wrapper only adapts
    sample objects to row dicts and maps the partitioned rows back, so the
    reported split always describes the trained partitions (review M2).
    """
    from floodguard.modeling.splits import SplitConfig as _SplitConfig
    from floodguard.modeling.splits import partition_rows as _partition_rows

    order = list(samples)
    proxy = [{"prediction_origin_utc": s.origin_utc, "_index": i} for i, s in enumerate(order)]
    config = _SplitConfig(
        train_end_utc=train_end, validation_end_utc=val_end, purge_embargo_minutes=embargo_minutes
    )
    train_rows, val_rows, test_rows, purged_train, purged_val = _partition_rows(proxy, config)
    train = [order[int(r["_index"])] for r in train_rows]
    val = [order[int(r["_index"])] for r in val_rows]
    test = [order[int(r["_index"])] for r in test_rows]
    return train, val, test, purged_train, purged_val


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train one Phase 6 forecaster (offline, CPU).")
    ap.add_argument("--input", type=Path, default=None)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--model", choices=("statistical", "xgboost"), default="statistical")
    ap.add_argument("--horizon", type=int, choices=(30, 60, 120), default=30)
    ap.add_argument("--lookback", type=int, default=120, choices=(60, 120, 180))
    ap.add_argument("--output-root", type=Path, default=Path("artifacts/forecasting"))
    ap.add_argument("--dataset-version", default="synthetic-forecast-v1")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--lstm-gru", action="store_true", help="run the LSTM/GRU justification gate")
    ap.add_argument("--timesfm", action="store_true", help="check TimesFM benchmark availability")
    args = ap.parse_args(argv)

    if args.lstm_gru:
        from floodguard.forecasting.sequence_gate import assess_sequence_justification

        gate_verdict = assess_sequence_justification(train_samples=0, stations_meeting_coverage=0)
        print(json.dumps(gate_verdict.to_dict(), indent=2, sort_keys=True))
        return 0
    if args.timesfm:
        from floodguard.forecasting.timesfm import check_timesfm_availability

        availability = check_timesfm_availability()
        print(json.dumps(availability.to_dict(), indent=2, sort_keys=True))
        return 0

    try:
        rows = _load_rows(args.input, args.synthetic)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not rows:
        print("REJECTED: no rows.", file=sys.stderr)
        return 2

    per_horizon, build_reports = build_forecast_samples(
        rows,
        ForecastDatasetConfig(lookback_minutes=args.lookback, dataset_version=args.dataset_version),
    )
    samples = per_horizon[args.horizon]
    if not samples:
        print(
            json.dumps(
                {"status": "NOT_EVALUABLE", "reason": "no samples built.", "horizon": args.horizon},
                indent=2,
            )
        )
        return 0

    origins = sorted(s.origin_utc for s in samples)
    train_end = origins[len(origins) * 2 // 3]
    val_end = origins[len(origins) * 5 // 6]
    proxy_rows = [{"prediction_origin_utc": s.origin_utc} for s in samples]
    split = chronological_split(
        proxy_rows,
        SplitConfig(train_end_utc=train_end, validation_end_utc=val_end),
    )
    train_samples, val_samples, test_samples, purged_train, purged_val = _partition_samples(
        samples, train_end, val_end
    )
    # Reported split and trained partitions share one code path (review M2).
    assert len(train_samples) == split.train.row_count
    assert len(val_samples) == split.validation.row_count
    assert len(test_samples) == split.test.row_count
    assert purged_train == split.train.purged_row_count
    assert purged_val == split.validation.purged_row_count
    evidence = EVIDENCE_SYNTHETIC if args.synthetic else EVIDENCE_LOCAL_DIAGNOSTIC

    by_station_train: dict[str, list[ForecastSample]] = {}
    for sample in train_samples:
        by_station_train.setdefault(sample.fg_sensor_id, []).append(sample)
    # Scaler fits on train-origin levels only (a distribution choice: the
    # origin level anchors every forecast; windows/targets reuse it frozen).
    preprocessor = fit_preprocessor(
        {sid: [s.origin_level_m for s in slist] for sid, slist in by_station_train.items()}
    )

    from floodguard.forecasting.statistical import StatisticalConfig

    lag_cfg = StatisticalConfig()

    # Scaled per-station level history for origin-exclusive lag features via
    # the library builders (single definition of lag semantics, review M1).
    # Transform is pointwise with frozen training stats: using all rows here
    # leaks nothing; only train/val origins below enter matrices.
    def _scaled_history(sensor_id: str) -> dict[str, float]:
        scaler = require_station(preprocessor, sensor_id)
        history: dict[str, float] = {}
        for row in rows:
            if str(row.get("fg_sensor_id")) != sensor_id:
                continue
            if row.get("measurement_type") != "WATER_LEVEL":
                continue
            if not row.get("usable") or not isinstance(row.get("value"), (int, float)):
                continue
            history[str(row["observation_time_utc"])] = scaler.transform(float(str(row["value"])))
        return history

    def _target_map(slist: list[ForecastSample]) -> dict[str, float]:
        scaler = require_station(preprocessor, slist[0].fg_sensor_id)
        return {s.origin_utc: scaler.transform(s.target_level_m) for s in slist}

    estimators: dict[str, Any] = {}
    metas: dict[str, Any] = {}
    for sensor_id, slist in sorted(by_station_train.items()):
        history = _scaled_history(sensor_id)
        targets = _target_map(slist)
        train_origins = [s.origin_utc for s in slist]
        if args.model == "statistical":
            from floodguard.forecasting.statistical import build_lag_matrix, train_linear_ar

            x_train, kept = build_lag_matrix(history, train_origins, lag_cfg)
            y_train = [targets[o] for o in kept]
            est, meta = train_linear_ar(
                x_train, y_train, lag_cfg, fg_sensor_id=sensor_id, horizon_minutes=args.horizon
            )
            family = "linear_ar"
        else:
            from floodguard.forecasting.gradient_boosting import (
                GradientBoostingConfig,
                build_lag_delta_matrix,
                train_gbm_regressor,
            )

            x_train, kept = build_lag_delta_matrix(
                history, train_origins, lag_cfg.lag_offsets_minutes
            )
            y_train = [targets[o] for o in kept]
            est, meta = train_gbm_regressor(
                x_train,
                y_train,
                GradientBoostingConfig(n_estimators=10, random_state=args.seed),
                fg_sensor_id=sensor_id,
                horizon_minutes=args.horizon,
            )
            family = "xgboost_regressor"
        estimators[sensor_id] = est
        metas[sensor_id] = meta

    # Frozen validation evaluation per station.
    evaluations: dict[str, Any] = {}
    for sensor_id in sorted(by_station_train):
        history = _scaled_history(sensor_id)
        vlist = [s for s in val_samples if s.fg_sensor_id == sensor_id]
        val_origins = [s.origin_utc for s in vlist]
        val_targets = {s.origin_utc: s.target_level_m for s in vlist}
        if family == "linear_ar":
            from floodguard.forecasting.statistical import build_lag_matrix as _val_lags

            x_val, kept_val = _val_lags(history, val_origins, lag_cfg)
        else:
            from floodguard.forecasting.gradient_boosting import (
                build_lag_delta_matrix as _val_lag_delta,
            )

            x_val, kept_val = _val_lag_delta(history, val_origins, lag_cfg.lag_offsets_minutes)
        import numpy as np

        scaler = require_station(preprocessor, sensor_id)
        preds = [
            scaler.inverse(float(estimators[sensor_id].predict(np.asarray([row]))[0]))
            for row in x_val
        ]
        trues = [val_targets[o] for o in kept_val]
        evaluations[sensor_id] = score_predictions(
            trues,
            preds,
            fg_sensor_id=sensor_id,
            model_family=family,
            horizon_minutes=args.horizon,
            evidence_level=evidence,
        ).to_dict()

    import hashlib

    rows_digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
    artifact_meta = ForecastArtifactMetadata(
        model_family=family,
        run_id=f"{family}-plus-{args.horizon}m-seed{args.seed}",
        horizon_minutes=args.horizon,
        dataset_version=args.dataset_version,
        observations_hash=rows_digest,
        feature_schema_version="features/v1",
        sequence_schema_version=DATASET_SCHEMA_VERSION,
        target_definition="exact water level at t+h (no interpolation)",
        station_scope=tuple(sorted(by_station_train)),
        lookback_minutes=args.lookback,
        preprocessing=preprocessor.to_dict(),
        scaler_lineage="per-station mean/std fit on training origins only",
        model_architecture={"lags": list(lag_cfg.lag_offsets_minutes)},
        random_seed=args.seed,
        device="cpu",
        library_versions={"device": "cpu"},
        train_partition=f"origins <= {train_end} minus 120m embargo",
        validation_partition=f"({train_end}, {val_end}] minus 120m embargo",
        test_partition=f"origins > {val_end}",
        evidence_level=evidence,
        metrics_eligibility="synthetic validation only" if args.synthetic else "local diagnostic",
    )
    saved = save_forecast_artifact(args.output_root, estimators, artifact_meta)
    print(
        json.dumps(
            {
                "status": "TRAINED",
                "model_family": family,
                "horizon_minutes": args.horizon,
                "lookback_minutes": args.lookback,
                "artifact_dir": str(saved),
                "split": split.to_dict(),
                "build_reports": [r.to_dict() for r in build_reports],
                "evaluation_validation": evaluations,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
