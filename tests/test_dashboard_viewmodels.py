"""Dashboard view-model tests: states, gaps, provenance, honesty (offline)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from floodguard.dashboard.client import ApiResult
from floodguard.dashboard.viewmodels import (
    STATE_EMPTY,
    STATE_ERROR,
    STATE_OK,
    STATE_UNAVAILABLE,
    drift_vm,
    monitoring_vm,
    observation_series_vm,
    overview_vm,
    performance_vm,
    prediction_vm,
    quality_vm,
    shap_vm,
    station_vm,
)

pytestmark = pytest.mark.usefixtures("no_network")

NOW = datetime(2030, 6, 1, 12, 0, tzinfo=UTC)


def _ok(data: object) -> ApiResult:
    return ApiResult("ok", data=data)


def _empty() -> ApiResult:
    return ApiResult("empty", data=[])


def test_overview_states_and_eligibility() -> None:
    view = overview_vm(
        _ok({"status": "ok"}),
        _ok({"status": "ready", "checks": {"database": "ok", "postgis": "skipped"}}),
        _ok([{"fg_site_id": "s1", "sensors": [{"fg_sensor_id": "a"}, {"fg_sensor_id": "b"}]}]),
        _ok({"status": "NO_ELIGIBLE_MODEL"}),
    )
    assert view.state == STATE_OK
    assert view.summary["sites"] == 1
    assert view.summary["sensors"] == 2
    assert view.summary["model_status"] == "NO_ELIGIBLE_MODEL"
    assert view.summary["forecast_model_status"] == "NO_ELIGIBLE_FORECAST_MODEL"

    down = overview_vm(
        ApiResult("unavailable"),
        _ok({}),
        _ok([]),
        _ok({}),
    )
    assert down.state == STATE_UNAVAILABLE


def test_monitoring_age_fact_and_sort() -> None:
    from typing import Any

    stations = _ok(
        [
            {
                "fg_site_id": "s2",
                "sensors": [{"fg_sensor_id": "b", "sensor_type": "WATER_LEVEL", "unit": "m"}],
            },
            {
                "fg_site_id": "s1",
                "sensors": [{"fg_sensor_id": "a", "sensor_type": "RAINFALL", "unit": "mm"}],
            },
        ]
    )
    latest: dict[str, dict[str, Any]] = {
        "a": {"value": 0.0, "usable": True, "observation_time_utc": "2030-06-01T11:30:00+00:00"},
        "b": {"value": None, "usable": False, "observation_time_utc": None},
    }
    view = monitoring_vm(stations, latest, now_utc=NOW)
    assert view.state == STATE_OK
    assert [row["sensor"] for row in view.tables["latest"]] == ["a", "b"]
    assert view.tables["latest"][0]["age_minutes"] == pytest.approx(30.0)
    assert view.tables["latest"][1]["age_minutes"] is None


def test_prediction_empty_and_evidence() -> None:
    view = prediction_vm(_empty(), _ok({"status": "NO_ELIGIBLE_MODEL"}))
    assert view.state == STATE_EMPTY
    assert "NO_ELIGIBLE_MODEL" in view.notices[0]
    full = prediction_vm(
        _ok(
            [
                {
                    "prediction_origin_utc": "t",
                    "target_time_utc": "t2",
                    "horizon_minutes": 30,
                    "predicted_value": 1.5,
                    "predicted_label": None,
                    "model_family": "persistence",
                    "run_id": "persistence",
                    "evidence_level": "SYNTHETIC_SOFTWARE_VALIDATION",
                }
            ]
        ),
        _ok({"status": "NO_ELIGIBLE_MODEL"}),
    )
    assert full.state == STATE_OK
    assert "not real performance" in full.tables["predictions"][0]["evidence"]


def test_station_threshold_provenance_and_normal_excluded() -> None:
    view = station_vm(
        _ok(
            {
                "fg_site_id": "s1",
                "site_name": "S",
                "district": "D",
                "main_basin": "B",
                "crs": "EPSG:4326 (inferred)",
                "latitude": 5.41,
                "longitude": 100.32,
                "sensors": [{}, {}],
                "thresholds": [
                    {"threshold_type": "NORMAL", "value_m": 0.0},
                    {
                        "threshold_type": "WASPADA",
                        "value_m": 1.5,
                        "threshold_source": "S",
                        "captured_at": "t",
                        "temporal_validity": "CURRENT_THRESHOLD_REFERENCE_ONLY",
                        "fg_label_eligible": True,
                    },
                ],
            }
        )
    )
    assert view.state == STATE_OK
    assert [row["type"] for row in view.tables["thresholds"]] == ["WASPADA"]
    assert view.tables["thresholds"][0]["validity"] == "CURRENT_THRESHOLD_REFERENCE_ONLY"
    assert view.series["map_point"] == [{"lat": 5.41, "lon": 100.32}]
    assert view.summary["sensors"] == 2


def test_series_gaps_and_zero_vs_missing() -> None:
    view = observation_series_vm(
        _ok(
            {
                "items": [
                    {"observation_time_utc": "t0", "value": 0.0},
                    {"observation_time_utc": "t1", "value": None},
                    {"observation_time_utc": "t2", "value": 2.5},
                ]
            }
        ),
        measurement_type="RAINFALL_INTERVAL",
        unit="mm",
    )
    assert view.state == STATE_OK
    assert view.series["values"][1] == {"time": "t1", "value": None}
    assert view.summary["missing_points"] == 1
    assert view.summary["zero_points"] == 1
    assert observation_series_vm(_empty(), measurement_type="m", unit="m").state == STATE_EMPTY


def test_performance_goals_not_results_and_shap_empty() -> None:
    view = performance_vm(_ok({"status": "NO_ELIGIBLE_MODEL", "registry_models": []}))
    assert view.state == STATE_OK
    assert "goal" in view.summary["recall_target"]
    assert shap_vm().state == STATE_EMPTY
    assert "never causality" in shap_vm().notices[1]


def test_quality_and_drift_states() -> None:
    summary = {"total": 10, "usable": 8, "evidence": "LOCAL_REAL_DATA_DIAGNOSTIC"}
    view = quality_vm(_ok({"items": []}), summary)
    assert view.state == STATE_OK
    assert "not Penang-wide" in view.notices[1]
    assert quality_vm(_ok({"items": []}), {"total": 0}).state == STATE_EMPTY
    assert quality_vm(ApiResult("server"), {}).state == STATE_ERROR
    drift = drift_vm([{"site": "s1"}])
    assert drift.state == STATE_OK
    assert "never drift" in drift.notices[1] or "not a drift" in drift.notices[1]
    assert drift_vm([]).state == STATE_EMPTY
