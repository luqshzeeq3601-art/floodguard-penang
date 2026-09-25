"""Offline tests for station/basin spatial features and paired multi-sensor sites."""

from __future__ import annotations

import pytest

from floodguard.features.paired import build_paired_site_features, register_paired_features
from floodguard.features.registry import REGISTRY
from floodguard.features.spatial import (
    extract_station_spatial_features,
    register_spatial_features,
)

pytestmark = pytest.mark.usefixtures("no_network")


def test_spatial_feature_registration() -> None:
    defs = register_spatial_features()
    assert len(defs) > 0
    assert REGISTRY.contains("station_latitude")
    assert REGISTRY.contains("station_longitude")
    assert REGISTRY.contains("station_district")
    assert REGISTRY.contains("station_main_basin")
    assert REGISTRY.contains("station_sensor_type")


def test_paired_feature_registration() -> None:
    defs = register_paired_features()
    assert len(defs) > 0
    assert REGISTRY.contains("paired_rainfall_sensor_id")
    assert REGISTRY.contains("paired_water_level_sensor_id")


def test_spatial_feature_extraction() -> None:
    meta = {
        "latitude": 5.4164,
        "longitude": 100.3327,
        "district": "Timur Laut",
        "main_basin": "Sg. Pinang",
        "sensor_type": "WATER_LEVEL",
    }
    feats = extract_station_spatial_features(meta)
    assert feats["station_latitude"] == 5.4164
    assert feats["station_longitude"] == 100.3327
    assert feats["station_district"] == "Timur Laut"
    assert feats["station_main_basin"] == "Sg. Pinang"
    assert feats["station_sensor_type"] == "WATER_LEVEL"


def test_paired_site_joining() -> None:
    rf_features = [
        {
            "source": "JPS_PUBLIC_INFOBANJIR",
            "fg_sensor_id": "RF_001",
            "fg_site_id": "SITE_001",
            "prediction_origin_utc": "2030-01-01T00:00:00Z",
            "prediction_origin_local": "2030-01-01T08:00:00+08:00",
            "rf_roll_15m_sum_mm": 5.0,
        },
        {
            "source": "JPS_PUBLIC_INFOBANJIR",
            "fg_sensor_id": "RF_002",
            "fg_site_id": "SITE_002",
            "prediction_origin_utc": "2030-01-01T00:00:00Z",
            "prediction_origin_local": "2030-01-01T08:00:00+08:00",
            "rf_roll_15m_sum_mm": 2.0,
        },
    ]

    wl_features = [
        {
            "source": "JPS_PUBLIC_INFOBANJIR",
            "fg_sensor_id": "WL_001",
            "fg_site_id": "SITE_001",
            "prediction_origin_utc": "2030-01-01T00:00:00Z",
            "prediction_origin_local": "2030-01-01T08:00:00+08:00",
            "wl_level_m": 2.5,
            "wl_delta_15m_m": 0.2,
        }
    ]

    paired = build_paired_site_features(rf_features, wl_features)
    assert len(paired) == 1
    p = paired[0]
    assert p["fg_site_id"] == "SITE_001"
    assert p["paired_rainfall_sensor_id"] == "RF_001"
    assert p["paired_water_level_sensor_id"] == "WL_001"
    assert p["rf_roll_15m_sum_mm"] == 5.0
    assert p["wl_level_m"] == 2.5
    assert p["wl_delta_15m_m"] == 0.2
