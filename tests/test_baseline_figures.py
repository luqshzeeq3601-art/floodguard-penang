"""Offline unit tests for baseline EDA figure generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from floodguard.analysis.figures import (
    plot_missingness_summary,
    plot_rainfall_timeseries,
    plot_water_level_timeseries,
    produce_all_figures,
)

T0 = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)
_KL = ZoneInfo("Asia/Kuala_Lumpur")


def make_obs_row(
    step: int,
    value: float | None,
    mtype: str = "WATER_LEVEL",
    unit: str = "m",
    sid: str = "s1",
) -> dict[str, Any]:
    t = T0 + timedelta(minutes=5 * step)
    local = t.astimezone(_KL)
    usable = value is not None
    return {
        "observation_schema_version": "observations/v1",
        "source": "JPS_PUBLIC_INFOBANJIR",
        "fg_sensor_id": sid,
        "fg_site_id": f"site_{sid}",
        "sensor_type": "WATER_LEVEL" if mtype == "WATER_LEVEL" else "RAINFALL",
        "measurement_type": mtype,
        "unit": unit,
        "observation_time_utc": t.isoformat(),
        "observation_time_local": local.isoformat(),
        "value": value,
        "usable": usable,
        "quality_flags": ["TIMEZONE_ASSUMED"] if usable else ["VALUE_MISSING_SENTINEL"],
        "datasets": ["jps_history"],
        "provenance": [{"dataset": "jps_history", "ingestion_batch_id": "b1"}],
    }


def test_plot_rainfall_timeseries(tmp_path: Path) -> None:
    rows = [
        make_obs_row(i, 2.5 if i % 4 == 0 else 0.0, mtype="RAINFALL_INTERVAL", unit="mm")
        for i in range(20)
    ]
    doc = {"dataset_version": "test_ds"}
    figs = plot_rainfall_timeseries(doc, rows, tmp_path)
    assert len(figs) == 1
    assert figs[0].is_file()
    assert figs[0].stat().st_size > 0


def test_plot_water_level_timeseries(tmp_path: Path) -> None:
    # 20 rows with a missing gap at step 10
    rows = [
        make_obs_row(i, None if i == 10 else 2.0 + 0.1 * i, mtype="WATER_LEVEL", unit="m")
        for i in range(20)
    ]
    doc = {
        "dataset_version": "test_ds",
        "stations": [
            {
                "fg_sensor_id": "s1",
                "threshold_reference": {
                    "thresholds": [
                        {"threshold_type": "WASPADA", "value_m": 3.0},
                        {"threshold_type": "AMARAN", "value_m": 4.0},
                    ]
                },
            }
        ],
    }
    figs = plot_water_level_timeseries(doc, rows, tmp_path)
    assert len(figs) == 1
    assert figs[0].is_file()
    assert figs[0].stat().st_size > 0


def test_plot_missingness_summary(tmp_path: Path) -> None:
    doc = {
        "dataset_version": "test_ds",
        "series": [
            {
                "fg_sensor_id": "s1",
                "measurement_type": "WATER_LEVEL",
                "cadence_windows": [{"usable_slots": 100, "missing_slots": 20}],
            }
        ],
    }
    figs = plot_missingness_summary(doc, tmp_path)
    assert len(figs) == 1
    assert figs[0].is_file()
    assert figs[0].stat().st_size > 0


def test_produce_all_figures(tmp_path: Path) -> None:
    # Setup mock dataset dir
    ds_dir = tmp_path / "processed" / "test_ds"
    ds_dir.mkdir(parents=True)
    rows = [
        make_obs_row(0, 5.0, mtype="RAINFALL_INTERVAL", unit="mm"),
        make_obs_row(0, 2.0, mtype="WATER_LEVEL", unit="m"),
    ]
    lines = [json.dumps(r) for r in rows]
    (ds_dir / "observations.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ds_dir / "dataset_manifest.json").write_text(
        json.dumps({"dataset_version": "test_ds"}), encoding="utf-8"
    )

    # Setup mock analysis outputs
    analysis_root = tmp_path / "analysis"
    (analysis_root / "rainfall" / "test_ds").mkdir(parents=True)
    (analysis_root / "rainfall" / "test_ds" / "rainfall_distribution.json").write_text(
        json.dumps({"dataset_version": "test_ds"}), encoding="utf-8"
    )

    (analysis_root / "water_level" / "test_ds").mkdir(parents=True)
    (analysis_root / "water_level" / "test_ds" / "water_level_trends.json").write_text(
        json.dumps({"dataset_version": "test_ds", "stations": []}), encoding="utf-8"
    )

    (analysis_root / "missingness" / "test_ds").mkdir(parents=True)
    (analysis_root / "missingness" / "test_ds" / "missingness.json").write_text(
        json.dumps({"dataset_version": "test_ds", "series": []}), encoding="utf-8"
    )

    out_dir = tmp_path / "figures" / "test_ds"
    res = produce_all_figures(analysis_root, ds_dir, out_dir)

    assert res["dataset_version"] == "test_ds"
    assert res["figures_count"] >= 1
