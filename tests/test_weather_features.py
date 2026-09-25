"""Offline tests for weather/forecast features (Phase 4 Task 5)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from floodguard.features.registry import REGISTRY
from floodguard.features.weather import (
    WeatherForecastRecord,
    compute_weather_features_for_origin,
    register_weather_features,
)

pytestmark = pytest.mark.usefixtures("no_network")

MYT = timezone(timedelta(hours=8))


def test_weather_feature_registration() -> None:
    defs = register_weather_features()
    assert len(defs) > 0
    assert REGISTRY.contains("fc_temp_min_c")
    assert REGISTRY.contains("fc_temp_max_c")
    assert REGISTRY.contains("fc_temp_range_c")
    assert REGISTRY.contains("fc_is_rain_forecast")
    assert REGISTRY.contains("fc_is_thunderstorm_forecast")


def test_weather_forecast_extraction_point_in_time() -> None:
    origin_t = datetime(2030, 6, 15, 10, 0, tzinfo=MYT)
    retrieved_t = datetime(2030, 6, 15, 6, 0, tzinfo=MYT)

    fcs = [
        WeatherForecastRecord(
            location_id="LOC_01",
            location_name="Timur Laut",
            forecast_date=date(2030, 6, 15),
            retrieved_at=retrieved_t,
            min_temp_c=24.5,
            max_temp_c=31.5,
            summary_forecast="Ribut petir di satu dua tempat",
        )
    ]

    feats = compute_weather_features_for_origin(origin_t, "Timur Laut", fcs)
    assert feats["fc_temp_min_c"] == 24.5
    assert feats["fc_temp_max_c"] == 31.5
    assert feats["fc_temp_range_c"] == 7.0
    assert feats["fc_is_rain_forecast"] == 1
    assert feats["fc_is_thunderstorm_forecast"] == 1


def test_weather_forecast_future_retrieval_rejected() -> None:
    origin_t = datetime(2030, 6, 15, 10, 0, tzinfo=MYT)
    future_retrieved_t = datetime(2030, 6, 15, 11, 0, tzinfo=MYT)

    fcs = [
        WeatherForecastRecord(
            location_id="LOC_01",
            location_name="Timur Laut",
            forecast_date=date(2030, 6, 15),
            retrieved_at=future_retrieved_t,
            min_temp_c=24.5,
            max_temp_c=31.5,
            summary_forecast="Ribut petir",
        )
    ]

    feats = compute_weather_features_for_origin(origin_t, "Timur Laut", fcs)
    assert feats["fc_temp_min_c"] is None
    assert feats["fc_temp_max_c"] is None
    assert feats["fc_is_rain_forecast"] is None
