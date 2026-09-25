"""Offline unit and contract tests for class imbalance and event-count viability analysis."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from floodguard.analysis.class_imbalance import (
    SCHEMA_VERSION,
    ClassImbalanceConfig,
    analyze,
    analyze_sensor_imbalance,
    write_summary,
)
from floodguard.preprocessing.units import MeasurementType
from floodguard.station_master import SensorType, ThresholdType
from floodguard.validation.observations import SCHEMA_VERSION as OBSERVATION_SCHEMA

T0 = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
_KL = ZoneInfo("Asia/Kuala_Lumpur")


def make_wl_row(
    step: int,
    value: float | None,
    *,
    sensor_id: str = "wl_sensor_1",
    site_id: str = "site_1",
    usable: bool = True,
    flags: list[str] | None = None,
) -> dict[str, Any]:
    t = T0 + timedelta(minutes=5 * step)
    local = t.astimezone(_KL)
    return {
        "observation_schema_version": OBSERVATION_SCHEMA,
        "source": "JPS_PUBLIC_INFOBANJIR",
        "fg_sensor_id": sensor_id,
        "fg_site_id": site_id,
        "sensor_type": SensorType.WATER_LEVEL,
        "measurement_type": MeasurementType.WATER_LEVEL,
        "unit": "m",
        "observation_time_utc": t.isoformat(),
        "observation_time_local": local.isoformat(),
        "value": value,
        "usable": usable,
        "quality_flags": flags or (["TIMEZONE_ASSUMED"] if usable else ["VALUE_MISSING_SENTINEL"]),
        "datasets": ["jps_water_level_history"],
        "provenance": [
            {
                "dataset": "jps_water_level_history",
                "ingestion_batch_id": "batch_1",
                "record_id": f"rec_{step}",
            }
        ],
    }


def make_thresh(
    threshold_type: str = ThresholdType.WASPADA,
    value_m: float = 3.0,
    source: str = "jps_state",
) -> dict[str, Any]:
    return {
        "threshold_type": threshold_type,
        "value_m": value_m,
        "threshold_source": source,
        "captured_at": "2026-09-25T00:00:00+08:00",
    }


def test_analyze_sensor_imbalance() -> None:
    # 30 steps: steps 10..15 exceed Waspada (3.0m), rest 2.0m
    rows = [make_wl_row(i, 3.5 if 10 <= i <= 15 else 2.0) for i in range(30)]
    thresholds = [make_thresh(ThresholdType.WASPADA, 3.0)]
    cfg = ClassImbalanceConfig()
    res = analyze_sensor_imbalance(rows, thresholds, cfg)

    assert res["fg_sensor_id"] == "wl_sensor_1"
    waspada_data = res["thresholds"]["WASPADA_jps_state"]
    assert waspada_data["observation_level_exceedances"] == 6
    assert waspada_data["contiguous_exceedance_episodes"] == 1

    h30 = waspada_data["horizons"]["plus_30m"]
    assert h30["evaluable_origins"] == 24
    # Positive exceedances at +30m (origins 4..9 target steps 10..15) -> 6 positive instances
    assert h30["exceedance"]["positive_count"] == 6
    assert h30["exceedance"]["negative_count"] == 18
    assert h30["exceedance"]["imbalance_ratio_negative_to_positive"] == 3.0  # 18 / 6


def test_analyze_full_output_and_feasibility(tmp_path: Path) -> None:
    # 40 steps of all 2.0m -> zero exceedances
    rows = [make_wl_row(i, 2.0) for i in range(40)]
    thresholds = {"wl_sensor_1": [make_thresh(ThresholdType.WASPADA, 3.0)]}
    meta = {"wl_sensor_1": {"sensor_type": SensorType.WATER_LEVEL}}

    doc = analyze(
        rows,
        dataset_version="test_ds",
        observations_sha256="fake_sha",
        station_metadata=meta,
        threshold_reference=thresholds,
    )

    assert doc["analysis_schema_version"] == SCHEMA_VERSION
    assert doc["dataset_version"] == "test_ds"
    assert doc["network"]["stations_analysed"] == 1

    feas = doc["feasibility"]
    assert feas["imbalance_analysis_verification"]["status"] == "SUFFICIENT"
    assert feas["chronological_split_viability"]["status"] == "INSUFFICIENT"

    out_path, written = write_summary(doc, tmp_path)
    assert written is True
    assert out_path.is_file()
