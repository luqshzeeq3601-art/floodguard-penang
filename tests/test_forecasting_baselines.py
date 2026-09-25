"""Persistence/statistical/GBM forecasting tests: correctness + determinism."""

from __future__ import annotations

import pytest

from floodguard.forecasting import NOT_EVALUABLE
from floodguard.forecasting.dataset import ForecastDatasetConfig, build_forecast_samples
from floodguard.forecasting.evaluation import persistence_skill, score_predictions
from floodguard.forecasting.gradient_boosting import GradientBoostingConfig, train_gbm_regressor
from floodguard.forecasting.persistence import score_all_stations, score_station_horizon
from floodguard.forecasting.preprocessing import fit_preprocessor, require_station
from floodguard.forecasting.statistical import StatisticalConfig, train_linear_ar
from floodguard.forecasting.synthetic import (
    make_constant_series,
    make_fall_series,
    make_rise_series,
)

pytestmark = pytest.mark.usefixtures("no_network")


def test_persistence_exact_on_constant_series() -> None:
    rows = make_constant_series(n=100, level=2.0)
    per_horizon, _ = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=60, dataset_version="t")
    )
    for horizon in (30, 60, 120):
        score = score_station_horizon(per_horizon[horizon], horizon)
        assert score.n > 0
        assert score.mae_m == 0.0
        assert score.rmse_m == 0.0


def test_persistence_per_station_not_pooled() -> None:
    from floodguard.forecasting.synthetic import make_two_datum_stations

    rows = make_two_datum_stations(n=100)
    per_horizon, _ = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=60, dataset_version="t")
    )
    report = score_all_stations(per_horizon)
    assert set(report["per_station"]) == {"SYN_WL_HIGH", "SYN_WL_LOW"}
    assert report["overall"]["30"]["weighting"].startswith("sample-weighted")
    assert report["overall"]["30"]["stations"] == 2


def test_statistical_trains_and_repeats_deterministically() -> None:
    rows = make_rise_series(n=150)
    per_horizon, _ = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=120, dataset_version="t")
    )
    samples = per_horizon[30][:60]
    cfg = StatisticalConfig()
    seqs = [[s.origin_level_m - i * 0.01 for i in range(24)] for s in samples]
    x_train = [[seq[-lag // 5] for lag in cfg.lag_offsets_minutes] for seq in seqs]
    y_train = [s.target_level_m for s in samples]
    est1, meta1 = train_linear_ar(
        x_train, y_train, cfg, fg_sensor_id="SYN_WL_A", horizon_minutes=30
    )
    est2, _ = train_linear_ar(x_train, y_train, cfg, fg_sensor_id="SYN_WL_A", horizon_minutes=30)
    assert list(est1.predict(x_train)) == list(est2.predict(x_train))
    assert meta1["device"] == "cpu"


def test_statistical_beats_persistence_on_rise() -> None:
    rows = make_rise_series(n=200, slope_per_step=0.02)
    per_horizon, _ = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=120, dataset_version="t")
    )
    samples = per_horizon[60]
    persist = score_station_horizon(samples, 60)
    assert isinstance(persist.mae_m, float)
    assert persist.mae_m > 0
    cfg = StatisticalConfig()
    x_all = [[s.origin_level_m - i * 0.02 for i in range(24)] for s in samples]
    # Closed-form AR on a perfect line extrapolates nearly exactly.
    est, _ = train_linear_ar(
        x_all,
        [s.target_level_m for s in samples],
        cfg,
        fg_sensor_id="SYN_WL_A",
        horizon_minutes=60,
    )
    import numpy as np

    preds = [float(v) for v in est.predict(np.asarray(x_all))]
    model = score_predictions(
        [s.target_level_m for s in samples],
        preds,
        fg_sensor_id="SYN_WL_A",
        model_family="linear_ar",
        horizon_minutes=60,
    )
    assert isinstance(model.mae_m, float)
    assert model.mae_m < persist.mae_m
    assert persistence_skill(model.mae_m, persist.mae_m) == pytest.approx(1.0, abs=1e-6)


def test_gbm_cpu_trains_and_repeats() -> None:
    rows = make_fall_series(n=150)
    per_horizon, _ = build_forecast_samples(
        rows, ForecastDatasetConfig(lookback_minutes=120, dataset_version="t")
    )
    samples = per_horizon[30][:60]
    x_train = [[s.origin_level_m] * 6 + [0.0] * 5 for s in samples]
    y_train = [s.target_level_m for s in samples]
    cfg = GradientBoostingConfig(n_estimators=10, random_state=42, device="cpu")
    est1, meta1 = train_gbm_regressor(
        x_train, y_train, cfg, fg_sensor_id="SYN_WL_A", horizon_minutes=30
    )
    est2, _ = train_gbm_regressor(
        x_train, y_train, cfg, fg_sensor_id="SYN_WL_A", horizon_minutes=30
    )
    assert list(est1.predict(x_train)) == list(est2.predict(x_train))
    assert meta1["device"] == "cpu"


def test_gbm_rejects_non_cpu_device() -> None:
    with pytest.raises(ValueError, match="must be 'cpu'"):
        GradientBoostingConfig(device="cuda")


def test_train_only_scaling_and_unseen_station_rejected() -> None:
    preprocessor = fit_preprocessor({"SYN_WL_A": [1.0, 2.0, 3.0]})
    before = dict(preprocessor.to_dict()["scalers"])
    scaler = require_station(preprocessor, "SYN_WL_A")
    assert scaler.transform(2.0) == pytest.approx(0.0)
    assert preprocessor.to_dict()["scalers"] == before
    with pytest.raises(ValueError, match="unseen station"):
        require_station(preprocessor, "SYN_WL_NEW")


def test_empty_evaluation_not_evaluable() -> None:
    score = score_predictions([], [], fg_sensor_id="S", model_family="m", horizon_minutes=30)
    assert score.mae_m == NOT_EVALUABLE
    assert score.rmse_m == NOT_EVALUABLE
    assert persistence_skill(0.1, 0.0) == NOT_EVALUABLE
    assert persistence_skill(NOT_EVALUABLE, 0.5) == NOT_EVALUABLE
