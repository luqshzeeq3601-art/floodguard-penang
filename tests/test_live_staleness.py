"""Stale-station detection tests (Phase 10, Task 3; offline, synthetic)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from floodguard.live.staleness import (
    STALE_POLICY_VERSION,
    StalePolicy,
    StationState,
    age_minutes,
    evaluate_sensor,
    parse_assumed_local,
)

pytestmark = pytest.mark.usefixtures("no_network")

NOW = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)


def test_policy_is_versioned_and_configurable() -> None:
    policy = StalePolicy()
    assert policy.version == STALE_POLICY_VERSION
    assert policy.stale_after_minutes == 60
    with pytest.raises(ValueError, match="positive"):
        StalePolicy(stale_after_minutes=0)


def test_f2_sensor_boundaries() -> None:
    policy = StalePolicy(stale_after_minutes=60)
    # Exactly at the bound stays ACTIVE; one second over is STALE.
    at = NOW - timedelta(minutes=60)
    over = NOW - timedelta(minutes=60, seconds=1)
    assert (
        evaluate_sensor(
            "s1", observed_utc=at, now_utc=NOW, expected_interval_minutes=15, policy=policy
        ).state
        == StationState.ACTIVE
    )
    assert (
        evaluate_sensor(
            "s1", observed_utc=over, now_utc=NOW, expected_interval_minutes=15, policy=policy
        ).state
        == StationState.STALE
    )
    # Fresh F2 batch is ACTIVE.
    recent = NOW - timedelta(minutes=10)
    verdict = evaluate_sensor(
        "s1", observed_utc=recent, now_utc=NOW, expected_interval_minutes=15, policy=policy
    )
    assert verdict.state == StationState.ACTIVE
    assert verdict.policy_version == STALE_POLICY_VERSION
    assert verdict.age_minutes == pytest.approx(10.0)


def test_unknown_cadence_never_verdicts_stale() -> None:
    old = NOW - timedelta(hours=10)
    verdict = evaluate_sensor("s2", observed_utc=old, now_utc=NOW, expected_interval_minutes=None)
    assert verdict.state == StationState.UNKNOWN
    assert verdict.age_minutes == pytest.approx(600.0)


def test_invalid_times() -> None:
    assert (
        evaluate_sensor("s3", observed_utc=None, now_utc=NOW, expected_interval_minutes=15).state
        == StationState.INVALID
    )
    future = NOW + timedelta(minutes=30)
    assert (
        evaluate_sensor("s3", observed_utc=future, now_utc=NOW, expected_interval_minutes=15).state
        == StationState.INVALID
    )


def test_age_is_factual_and_assumed_zone_parses() -> None:
    assert age_minutes(None, NOW) is None
    moment = datetime(2030, 1, 1, 11, 30, tzinfo=UTC)
    assert age_minutes(moment, NOW) == pytest.approx(30.0)
    parsed = parse_assumed_local("01/01/2030 08:00")
    assert parsed is not None
    assert parsed.utcoffset() is not None
    assert parse_assumed_local("") is None
    assert parse_assumed_local("not a time") is None


def test_dashboard_factual_age_untouched() -> None:
    # The dashboard view-model still reports factual age only (no verdicts).
    from floodguard.dashboard.client import RESULT_OK, ApiResult
    from floodguard.dashboard.viewmodels import monitoring_vm

    stations = ApiResult(
        RESULT_OK,
        data=[
            {
                "fg_site_id": "site-1",
                "sensors": [{"fg_sensor_id": "sen-1", "sensor_type": "WATER_LEVEL", "unit": "m"}],
            }
        ],
    )
    view = monitoring_vm(
        stations,
        {
            "sen-1": {
                "value": 1.0,
                "usable": True,
                "observation_time_utc": "2030-01-01T00:00:00+00:00",
            }
        },
        now_utc=datetime(2030, 1, 1, 2, 0, tzinfo=UTC),
    )
    assert view.state == "ok"
    assert view.tables["latest"][0]["age_minutes"] == pytest.approx(120.0)
    assert "no production freshness verdict" in view.notices[0].lower()
