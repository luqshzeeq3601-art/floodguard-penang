"""Offline unit and contract tests for +30/+60/+120 label definitions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from floodguard.analysis.labels import (
    SCHEMA_VERSION,
    LabelDefinitionConfig,
    analyze,
    construct_labels_for_sensor,
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


def test_construct_labels_horizons() -> None:
    # 30 steps of 5 min = 150 minutes
    # Step 0 to 5 (0-25m): 2.0m
    # Step 6 (30m): 3.2m (exceeds Waspada 3.0m)
    # Step 12 (60m): 3.5m
    # Step 24 (120m): 2.8m (drops back below 3.0m)
    rows = []
    for i in range(30):
        val = 3.2 if 6 <= i <= 10 else 3.5 if 11 <= i <= 15 else 2.0
        rows.append(make_wl_row(i, val))

    thresholds = [make_thresh(ThresholdType.WASPADA, 3.0)]
    cfg = LabelDefinitionConfig()
    res = construct_labels_for_sensor(rows, thresholds, cfg)

    assert res["fg_sensor_id"] == "wl_sensor_1"
    assert res["usable_origins_count"] == 30

    h30 = res["horizons"]["plus_30m"]
    assert h30["horizon_minutes"] == 30
    assert h30["evaluable_origins"] == 24  # 30 - 6 steps at the end
    assert h30["missing_future_origins"] == 6

    h60 = res["horizons"]["plus_60m"]
    assert h60["horizon_minutes"] == 60
    assert h60["evaluable_origins"] == 18  # 30 - 12 steps at the end
    assert h60["missing_future_origins"] == 12

    h120 = res["horizons"]["plus_120m"]
    assert h120["horizon_minutes"] == 120
    assert h120["evaluable_origins"] == 6  # 30 - 24 steps at the end
    assert h120["missing_future_origins"] == 24


def test_missing_future_target_not_imputed() -> None:
    # 10 steps, step 6 is missing (-9999)
    rows = []
    for i in range(10):
        if i == 6:
            rows.append(make_wl_row(i, None, usable=False))
        else:
            rows.append(make_wl_row(i, 2.0))

    thresholds = [make_thresh(ThresholdType.WASPADA, 3.0)]
    cfg = LabelDefinitionConfig(horizons_minutes=(30,))  # 30m = 6 steps
    res = construct_labels_for_sensor(rows, thresholds, cfg)

    h30 = res["horizons"]["plus_30m"]
    # Total usable origins: 9 (step 6 is not usable so not an origin)
    # Origin 0 targets step 6 (which is missing) -> missing future target
    # Origins 1, 2, 3 target steps 7, 8, 9 (usable) -> evaluable
    # Origins 4, 5, 7, 8, 9 target steps 10, 11, 13, 14, 15 (out of bounds) -> missing future target
    assert h30["total_origins"] == 9
    assert h30["evaluable_origins"] == 3
    assert h30["missing_future_origins"] == 6


def test_analyze_full_output(tmp_path: Path) -> None:
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
    assert doc["feasibility"]["label_construction_verification"]["status"] == "SUFFICIENT"
    assert doc["feasibility"]["evaluable_origins_sufficiency"]["status"] == "SUFFICIENT"
    assert doc["feasibility"]["positive_label_feasibility"]["status"] == "INSUFFICIENT"

    out_path, written = write_summary(doc, tmp_path)
    assert written is True
    assert out_path.is_file()
