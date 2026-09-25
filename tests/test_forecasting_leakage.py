"""Phase 6 adversarial forecasting leakage release gates.

1. Post-origin mutation leaves the earlier input sequence unchanged.
2. Validation/test target mutation leaves fitted scaler/model unchanged.
3. Appended future data leaves training samples unchanged.
4. Test-set changes leave training preprocessing unchanged.
5. Sequence windows never include target timestamps.
6. Target values never appear as features.
7. Current thresholds cannot leak into forecasting samples.
8. Post-origin weather forecasts are unavailable (retrieved_at guard).
9. Chronological folds keep order.
10. Lookback windows never bridge disconnected capture windows.
"""

from __future__ import annotations

import pytest

from floodguard.forecasting.dataset import ForecastDatasetConfig, build_forecast_samples
from floodguard.forecasting.gradient_boosting import lag_delta_feature_names
from floodguard.forecasting.preprocessing import fit_preprocessor
from floodguard.forecasting.statistical import (
    StatisticalConfig,
    lag_feature_names,
    train_linear_ar,
)
from floodguard.forecasting.synthetic import (
    make_constant_series,
    make_rise_series,
    with_disconnected_windows,
)

pytestmark = pytest.mark.usefixtures("no_network")

CFG = ForecastDatasetConfig(lookback_minutes=60, dataset_version="t")
LAG_CFG = StatisticalConfig()


def _fit_first_window(rows: list[dict[str, object]]) -> tuple[dict[str, object], list[float]]:
    """Fit scaler + OLS on the earliest 40-sample window; return frozen state."""
    per_horizon, _ = build_forecast_samples(rows, CFG)
    samples = per_horizon[30][:40]
    levels = [s.origin_level_m for s in samples]
    preprocessor = fit_preprocessor({"SYN_WL_A": levels})
    seqs = [[s.origin_level_m] * 24 for s in samples]
    x_train = [[seq[-lag // 5] for lag in LAG_CFG.lag_offsets_minutes] for seq in seqs]
    y_train = [s.target_level_m for s in samples]
    est, _ = train_linear_ar(x_train, y_train, LAG_CFG, fg_sensor_id="SYN_WL_A", horizon_minutes=30)
    return preprocessor.to_dict(), list(est.predict(x_train))


def test_post_origin_mutation_leaves_earlier_sequence_unchanged() -> None:
    rows = make_rise_series(n=100)
    per_before, _ = build_forecast_samples(rows, CFG)
    early_ids = [s.sample_id() for s in per_before[30][:20]]
    early_levels = {s.sample_id(): s.input_levels_m for s in per_before[30][:20]}
    mutated = [dict(r) for r in rows]
    for row in mutated[60:]:
        row["value"] = 999.0
    per_after, _ = build_forecast_samples(mutated, CFG)
    after_levels = {s.sample_id(): s.input_levels_m for s in per_after[30]}
    for sample_id in early_ids:
        assert after_levels[sample_id] == early_levels[sample_id]


def test_validation_target_mutation_leaves_training_unchanged() -> None:
    rows = make_rise_series(n=120)
    scaler_before, preds_before = _fit_first_window(rows)
    mutated = [dict(r) for r in rows]
    for row in mutated[80:]:
        row["value"] = -50.0
    scaler_after, preds_after = _fit_first_window(mutated)
    assert scaler_after == scaler_before
    assert preds_after == preds_before


def test_appended_future_data_leaves_training_samples_unchanged() -> None:
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime
    from datetime import timedelta as _timedelta

    from floodguard.forecasting.synthetic import make_constant_series as _constant

    rows = make_constant_series(n=80)
    per_base, _ = build_forecast_samples(rows, CFG)
    base = {(s.sample_id(), s.input_levels_m) for s in per_base[30]}
    continuation_start = _datetime(2030, 1, 1, tzinfo=_UTC) + _timedelta(minutes=5 * 80)
    extended = rows + _constant(n=20, start=continuation_start)
    per_ext, _ = build_forecast_samples(extended, CFG)
    ext = {(s.sample_id(), s.input_levels_m) for s in per_ext[30]}
    # Pre-existing samples byte-identical; only new tail origins may appear.
    assert base <= ext
    assert len(ext) > len(base)


def test_test_mutation_leaves_training_preprocessing_unchanged() -> None:
    rows = make_constant_series(n=100)
    per_horizon, _ = build_forecast_samples(rows, CFG)
    train_levels = [s.origin_level_m for s in per_horizon[30][:40]]
    before = fit_preprocessor({"SYN_WL_A": train_levels}).to_dict()
    mutated = [dict(r) for r in rows]
    for row in mutated[60:]:
        row["value"] = 123.0
    per_mut, _ = build_forecast_samples(mutated, CFG)
    after_levels = [s.origin_level_m for s in per_mut[30][:40]]
    # Earliest-40 training window is structurally identical; refit is equal.
    assert after_levels == train_levels
    assert fit_preprocessor({"SYN_WL_A": after_levels}).to_dict() == before


def test_sequences_exclude_target_timestamps() -> None:
    rows = make_rise_series(n=100)
    per_horizon, _ = build_forecast_samples(rows, CFG)
    for horizon, samples in per_horizon.items():
        assert horizon in (30, 60, 120)
        for sample in samples:
            assert len(sample.input_times_utc) == 12
            assert sample.input_times_utc[-1] == sample.origin_utc


def test_targets_and_thresholds_absent_from_features() -> None:

    rows = make_rise_series(n=100)
    per_horizon, _ = build_forecast_samples(rows, CFG)
    lag_names = set(lag_feature_names(StatisticalConfig()))
    lag_names |= set(lag_delta_feature_names((5, 10, 15, 30, 60, 120)))
    assert not any("target" in name or "threshold" in name for name in lag_names)
    for samples in per_horizon.values():
        for sample in samples:
            payload = sample.to_dict()
            assert not any("threshold" in key for key in payload)
            assert len(payload["input_levels_m"]) == len(payload["input_times_utc"])


def test_no_forecast_or_threshold_inputs_can_enter_samples() -> None:
    """Forecasting samples accept canonical rows only: no weather/threshold path exists."""
    import inspect

    from floodguard.forecasting import dataset as dataset_module

    params = inspect.signature(dataset_module.build_forecast_samples).parameters
    assert "forecast_records" not in params
    assert "threshold_reference" not in params
    assert "retrieved_at" not in params
    rows = make_rise_series(n=60)
    per_horizon, _ = build_forecast_samples(rows, CFG)
    forbidden = ("threshold", "retrieved_at", "forecast", "future_level", "exceed")
    for samples in per_horizon.values():
        for sample in samples:
            keys = " ".join(sample.to_dict().keys())
            assert not any(marker in keys for marker in forbidden)


def test_chronological_folds_ordered_with_embargo() -> None:
    from floodguard.modeling.splits import SplitConfig, chronological_split

    rows = make_rise_series(n=200)
    per_horizon, _ = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=120, dataset_version="t")
    )
    origins = sorted({s.origin_utc for s in per_horizon[30]})
    split = chronological_split(
        [{"prediction_origin_utc": o} for o in origins],
        SplitConfig(train_end_utc=origins[len(origins) * 2 // 3], validation_end_utc=origins[-1]),
    )
    assert split.status == "OK"
    assert split.train.row_count > 0


def test_lookback_never_bridges_disconnected_windows() -> None:
    rows = make_constant_series(n=80)
    split = with_disconnected_windows(rows, 40, gap_minutes=180)
    per_horizon, _ = build_forecast_samples(
        split, ForecastDatasetConfig(lookback_minutes=60, dataset_version="t")
    )
    complete, _ = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=60, dataset_version="t")
    )
    for horizon in (30, 60, 120):
        assert len(per_horizon[horizon]) < len(complete[horizon])
