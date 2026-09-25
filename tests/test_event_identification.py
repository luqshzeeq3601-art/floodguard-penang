"""Unit and contract tests for provisional flood/threshold event identification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from floodguard.analysis.events import (
    CURRENT_THRESHOLD_REFERENCE_ONLY,
    ENDED_BELOW_THRESHOLD,
    INTERRUPTED_BY_MISSING_DATA,
    PROVISIONAL_EXCEEDANCE_ONLY,
    SCHEMA_VERSION,
    WINDOW_EDGE,
    EventIdentificationConfig,
    analyze,
    segment_threshold_episodes,
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


def test_segment_episodes_clean_ended() -> None:
    # 5 steps: 2.0, 3.2 (exceed), 3.5 (exceed), 3.1 (exceed), 2.8 (below)
    rows = [
        make_wl_row(0, 2.0),
        make_wl_row(1, 3.2),
        make_wl_row(2, 3.5),
        make_wl_row(3, 3.1),
        make_wl_row(4, 2.8),
    ]
    thresh = make_thresh(ThresholdType.WASPADA, 3.0)
    cfg = EventIdentificationConfig()
    episodes, next_idx = segment_threshold_episodes(rows, thresh, cfg)

    assert len(episodes) == 1
    assert next_idx == 2
    ep = episodes[0]
    assert ep["observations_count"] == 3
    assert ep["start_utc"] == rows[1]["observation_time_utc"]
    assert ep["end_utc"] == rows[3]["observation_time_utc"]
    assert ep["duration_minutes"] == 10.0
    assert ep["peak_level_m"] == 3.5
    assert ep["max_exceedance_m"] == 0.5
    assert ep["termination_reason"] == ENDED_BELOW_THRESHOLD
    assert ep["temporal_validity"] == CURRENT_THRESHOLD_REFERENCE_ONLY
    assert ep["evidence_level"] == PROVISIONAL_EXCEEDANCE_ONLY


def test_segment_episodes_interrupted_by_missing() -> None:
    # 4 steps: 3.2 (exceed), None (unusable / -9999), 3.4 (exceed), 2.5 (below)
    rows = [
        make_wl_row(0, 3.2),
        make_wl_row(1, None, usable=False, flags=["VALUE_MISSING_SENTINEL"]),
        make_wl_row(2, 3.4),
        make_wl_row(3, 2.5),
    ]
    thresh = make_thresh(ThresholdType.AMARAN, 3.0)
    cfg = EventIdentificationConfig()
    episodes, _ = segment_threshold_episodes(rows, thresh, cfg)

    assert len(episodes) == 2
    assert episodes[0]["termination_reason"] == INTERRUPTED_BY_MISSING_DATA
    assert episodes[0]["observations_count"] == 1
    assert episodes[1]["termination_reason"] == ENDED_BELOW_THRESHOLD
    assert episodes[1]["observations_count"] == 1


def test_segment_episodes_window_edge() -> None:
    # 2 steps at the end of window: 3.2, 3.5
    rows = [
        make_wl_row(0, 3.2),
        make_wl_row(1, 3.5),
    ]
    thresh = make_thresh(ThresholdType.BAHAYA, 3.0)
    cfg = EventIdentificationConfig()
    episodes, _ = segment_threshold_episodes(rows, thresh, cfg)

    assert len(episodes) == 1
    assert episodes[0]["termination_reason"] == WINDOW_EDGE
    assert episodes[0]["observations_count"] == 2
    assert episodes[0]["duration_minutes"] == 5.0


def test_segment_episodes_interrupted_by_time_gap() -> None:
    # step 0 (3.2), step 3 (3.4) -> gap is 15 min > max_gap_minutes (5 min)
    rows = [
        make_wl_row(0, 3.2),
        make_wl_row(3, 3.4),
        make_wl_row(4, 2.5),
    ]
    thresh = make_thresh(ThresholdType.WASPADA, 3.0)
    cfg = EventIdentificationConfig()
    episodes, _ = segment_threshold_episodes(rows, thresh, cfg)

    assert len(episodes) == 2
    assert episodes[0]["termination_reason"] == INTERRUPTED_BY_MISSING_DATA
    assert episodes[1]["termination_reason"] == ENDED_BELOW_THRESHOLD


def test_normal_threshold_excluded() -> None:
    rows = [make_wl_row(0, 4.0)]
    thresholds = {
        "wl_sensor_1": [
            {
                "threshold_type": "NORMAL",
                "value_m": 1.0,
                "captured_at": "2026-09-25T00:00:00+08:00",
            },
            {
                "threshold_type": "WASPADA",
                "value_m": 3.0,
                "captured_at": "2026-09-25T00:00:00+08:00",
            },
        ]
    }
    doc = analyze(
        rows,
        dataset_version="v1",
        threshold_reference=thresholds,
    )
    station_eval = doc["stations"][0]["threshold_evaluations"]
    assert len(station_eval) == 1
    assert station_eval[0]["threshold_type"] == "WASPADA"


def test_analyze_full_output_contract(tmp_path: Path) -> None:
    # Generate 40 usable rows with 2 exceedance episodes
    rows = []
    for i in range(40):
        val = 3.5 if 10 <= i <= 15 or 25 <= i <= 28 else 2.0
        rows.append(make_wl_row(i, val))

    thresholds = {
        "wl_sensor_1": [
            make_thresh(ThresholdType.WASPADA, 3.0),
            make_thresh(ThresholdType.AMARAN, 4.0),
        ]
    }
    meta = {
        "wl_sensor_1": {
            "sensor_type": SensorType.WATER_LEVEL,
            "district": "Timur Laut",
            "main_basin": "Sungai Pinang",
        }
    }

    doc = analyze(
        rows,
        dataset_version="test_ds_1",
        observations_sha256="fake_sha",
        station_metadata=meta,
        threshold_reference=thresholds,
    )

    assert doc["analysis_schema_version"] == SCHEMA_VERSION
    assert doc["dataset_version"] == "test_ds_1"
    assert doc["network"]["stations_analysed"] == 1
    assert doc["network"]["stations_with_reference_thresholds"] == 1
    assert doc["network"]["verified_historical_flood_events"] == 0

    station = doc["stations"][0]
    assert station["fg_sensor_id"] == "wl_sensor_1"
    assert len(station["threshold_evaluations"]) == 2

    waspada_eval = station["threshold_evaluations"][0]
    assert waspada_eval["threshold_type"] == "WASPADA"
    assert waspada_eval["contiguous_exceedance_episodes"] == 2
    assert waspada_eval["exceedance_observations"] == 10  # 6 + 4
    assert waspada_eval["verified_historical_flood_events"] == 0

    amaran_eval = station["threshold_evaluations"][1]
    assert amaran_eval["threshold_type"] == "AMARAN"
    assert amaran_eval["contiguous_exceedance_episodes"] == 0
    assert amaran_eval["exceedance_observations"] == 0

    suff = doc["sufficiency"]
    assert suff["implementation_verification"]["status"] == "SUFFICIENT"
    assert suff["provisional_exceedance_detection"]["status"] == "SUFFICIENT"
    assert suff["episode_sample_statistics"]["status"] == "INSUFFICIENT"
    assert suff["historical_flood_ground_truth"]["status"] == "INSUFFICIENT"

    # Write-once test
    out_path, written = write_summary(doc, tmp_path)
    assert written is True
    assert out_path.is_file()

    # Rerun is a no-op
    _, written_again = write_summary(doc, tmp_path)
    assert written_again is False


def test_invalid_contract_rejected() -> None:
    # Rainfall row passed to water-level event analysis
    bad_row = {
        "observation_schema_version": OBSERVATION_SCHEMA,
        "source": "jps_rainfall",
        "fg_sensor_id": "rf_1",
        "fg_site_id": "site_1",
        "sensor_type": SensorType.RAINFALL,
        "measurement_type": MeasurementType.RAINFALL_INTERVAL,
        "unit": "mm",
        "observation_time_utc": T0.isoformat(),
        "observation_time_local": T0.isoformat(),
        "value": 5.0,
        "usable": True,
        "quality_flags": [],
        "datasets": ["jps_rainfall_history"],
        "provenance": [{"dataset": "jps_rainfall_history", "ingestion_batch_id": "b1"}],
    }
    # Only WATER_LEVEL rows enter; RAINFALL row is excluded. If NO water-level rows exist:
    doc = analyze([bad_row], dataset_version="v1")
    assert doc["input"]["water_level_rows"] == 0
    assert doc["network"]["stations_analysed"] == 0
