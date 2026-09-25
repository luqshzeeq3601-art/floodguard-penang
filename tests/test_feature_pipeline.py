"""Offline end-to-end tests for the feature pipeline (Phase 4).

Tests:
1. Feature pipeline run with synthetic dataset.
2. Invariant verification and manifest generation.
3. Write-once idempotency: rerunning produces exact match.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from floodguard.analysis.dataset import ProcessedDataset
from floodguard.features.pipeline import run_feature_pipeline
from floodguard.features.registry import SCHEMA_VERSION

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
MYT = timezone(timedelta(hours=8))
START = datetime(2030, 1, 1, 0, 5, tzinfo=MYT)


def make_test_row(
    i: int,
    value: float | None,
    measurement_type: str,
    sensor: str,
    site: str,
    unit: str,
) -> dict[str, Any]:
    local = START + timedelta(minutes=5 * i)
    st = "RAINFALL" if measurement_type == "RAINFALL_INTERVAL" else "WATER_LEVEL"
    return {
        "observation_schema_version": "observations/v1",
        "source": "JPS_PUBLIC_INFOBANJIR",
        "fg_sensor_id": sensor,
        "fg_site_id": site,
        "sensor_type": st,
        "measurement_type": measurement_type,
        "observation_time_local": local.isoformat(),
        "observation_time_utc": local.astimezone(UTC).isoformat(),
        "value": value,
        "unit": unit,
        "quality_flags": ["TIMEZONE_ASSUMED"] if value is not None else ["VALUE_MISSING_SENTINEL"],
        "usable": value is not None,
    }


def test_feature_pipeline_execution(tmp_path: Path) -> None:
    rf_rows = [
        make_test_row(i, float(i), "RAINFALL_INTERVAL", "RF_1", "SITE_1", "mm") for i in range(12)
    ]
    wl_rows = [
        make_test_row(i, 2.0 + 0.1 * i, "WATER_LEVEL", "WL_1", "SITE_1", "m") for i in range(12)
    ]
    all_rows = rf_rows + wl_rows

    dataset = ProcessedDataset(
        dataset_version="syn_test_001",
        observations_sha256="0" * 64,
        rows=all_rows,
        quality_summary={"summary_schema_version": "summary/v1"},
        manifest={
            "dataset_version": "syn_test_001",
            "observations_sha256": "0" * 64,
            "checks": [{"name": "mock_check", "passed": True}],
            "observations_rows": len(all_rows),
        },
    )

    out_root = tmp_path / "features"
    res = run_feature_pipeline(dataset, out_root)

    assert res.dataset_version == "syn_test_001"
    assert res.feature_schema_version == SCHEMA_VERSION
    assert len(res.written) == 4

    manifest_path = res.output_dir / "feature_manifest.json"
    assert manifest_path.is_file()
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert man["artifacts"]["rainfall_features"]["rows"] == 12
    assert man["artifacts"]["water_level_features"]["rows"] == 12
    assert man["artifacts"]["paired_site_features"]["rows"] == 12
    assert all(c["passed"] is True for c in man["checks"])

    res_repeat = run_feature_pipeline(dataset, out_root)
    assert len(res_repeat.written) == 0
