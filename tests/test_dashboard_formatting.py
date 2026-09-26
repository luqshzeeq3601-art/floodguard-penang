"""Dashboard formatting tests: units, timezones, evidence, quality (offline)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from floodguard.dashboard.config import DashboardConfig, load_config
from floodguard.dashboard.formatting import (
    evidence_label,
    format_age_minutes,
    format_timestamp,
    format_value,
    model_status_label,
    quality_summary,
)

pytestmark = pytest.mark.usefixtures("no_network")


def test_units_always_explicit_and_missing_is_dash() -> None:
    assert format_value(1.234, "m") == "1.23 m"
    assert format_value(0.0, "mm") == "0.00 mm"
    assert format_value(30, "C") == "30 °C"
    assert format_value(None, "m") == "—"


def test_timestamp_requires_tz_and_shows_both_zones() -> None:
    moment = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    text = format_timestamp(moment)
    assert "UTC" in text
    assert "20:00" in text  # 12:00 UTC is 20:00 in Asia/Kuala_Lumpur
    assert "12:00" in text
    with pytest.raises(ValueError, match="naive"):
        format_timestamp(datetime(2030, 1, 1, 12, 0))  # noqa: DTZ001 - naive input is the test case


def test_age_is_fact_never_verdict() -> None:
    assert format_age_minutes(None) == "unknown"
    assert format_age_minutes(-5.0) == "unknown"
    assert format_age_minutes(0.5) == "<1 min"
    assert format_age_minutes(45.0) == "45 min"
    assert "FRESH" not in format_age_minutes(1.0)
    assert "STALE" not in format_age_minutes(9999.0)


def test_evidence_labels_honest() -> None:
    assert "not real performance" in evidence_label("SYNTHETIC_SOFTWARE_VALIDATION")
    assert "not Penang-wide" in evidence_label("LOCAL_REAL_DATA_DIAGNOSTIC")
    assert evidence_label("REAL_PREDICTIVE_EVALUATION") == "real predictive evaluation"
    assert "unknown" in evidence_label("SOMETHING_ELSE")
    assert "no eligible" in model_status_label("NO_ELIGIBLE_MODEL")
    assert "no eligible" in model_status_label("NO_ELIGIBLE_FORECAST_MODEL")


def test_quality_summary_reuses_flags() -> None:
    from typing import Any

    rows: list[dict[str, Any]] = [
        {"usable": True, "value": 0.0, "quality_flags": ["TIMEZONE_ASSUMED"]},
        {"usable": True, "value": 2.5, "quality_flags": ["TIMEZONE_ASSUMED"]},
        {"usable": False, "value": None, "quality_flags": ["VALUE_MISSING_SENTINEL"]},
    ]
    summary = quality_summary(rows)
    assert summary["total"] == 3
    assert summary["usable"] == 2
    assert summary["missing_or_unusable"] == 1
    assert summary["zero_values"] == 1
    assert summary["flag_counts"]["TIMEZONE_ASSUMED"] == 2


def test_config_validation_and_defaults() -> None:
    config = load_config({})
    assert config.api_base_url == "http://localhost:8000"
    assert config.timeout_seconds == 10.0
    with pytest.raises(ValueError, match="http"):
        DashboardConfig(api_base_url="ftp://x", timeout_seconds=5.0)
    with pytest.raises(ValueError, match="positive"):
        DashboardConfig(api_base_url="http://x", timeout_seconds=0.0)
    with pytest.raises(ValueError, match="number"):
        load_config({"FLOODGUARD_API_TIMEOUT_SECONDS": "soon"})
