"""Deterministic synthetic water-level sequences for Phase 6 software checks.

Source marker: SYNTHETIC_TEST_ONLY. Patterns: constant, linear rise, linear
fall, periodic, rainfall-driven response. Multi-station fixtures use different
gauge datums (never pooled). Gap variants: complete, one missing slot,
internal missing run, boundary truncation, disconnected capture windows.
Software verification only; never FloodGuard performance.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

from floodguard.forecasting import CADENCE_MINUTES, SYNTHETIC_SOURCE

SYNTHETIC_FORECAST_SCHEMA: Final[str] = "synthetic_forecast/v1"


def _row(
    sensor: str,
    site: str,
    moment: datetime,
    value: float | None,
    *,
    measurement: str = "WATER_LEVEL",
) -> dict[str, Any]:
    local = moment.isoformat()
    return {
        "source": SYNTHETIC_SOURCE,
        "fg_sensor_id": sensor,
        "fg_site_id": site,
        "sensor_type": "WATER_LEVEL",
        "measurement_type": measurement,
        "observation_time_local": local,
        "observation_time_utc": local,
        "value": value,
        "unit": "m",
        "quality_flags": [] if value is not None else ["VALUE_MISSING_SENTINEL"],
        "usable": value is not None,
    }


def make_constant_series(
    *,
    n: int = 120,
    level: float = 1.5,
    sensor: str = "SYN_WL_A",
    site: str = "SYN_SITE_A",
    start: datetime | None = None,
    step_minutes: int = CADENCE_MINUTES,
) -> list[dict[str, Any]]:
    """Flat gauge datum series (persistence is exact here)."""
    t0 = start or datetime(2030, 1, 1, tzinfo=UTC)
    return [_row(sensor, site, t0 + timedelta(minutes=step_minutes * i), level) for i in range(n)]


def make_rise_series(
    *,
    n: int = 120,
    start_level: float = 1.0,
    slope_per_step: float = 0.01,
    sensor: str = "SYN_WL_A",
    site: str = "SYN_SITE_A",
    start: datetime | None = None,
    step_minutes: int = CADENCE_MINUTES,
) -> list[dict[str, Any]]:
    """Linear rise (tests trend-following baselines beat persistence)."""
    t0 = start or datetime(2030, 1, 1, tzinfo=UTC)
    return [
        _row(
            sensor, site, t0 + timedelta(minutes=step_minutes * i), start_level + slope_per_step * i
        )
        for i in range(n)
    ]


def make_fall_series(
    *,
    n: int = 120,
    start_level: float = 3.0,
    slope_per_step: float = 0.01,
    sensor: str = "SYN_WL_A",
    site: str = "SYN_SITE_A",
    start: datetime | None = None,
    step_minutes: int = CADENCE_MINUTES,
) -> list[dict[str, Any]]:
    """Linear fall (mirror of rise)."""
    t0 = start or datetime(2030, 1, 1, tzinfo=UTC)
    return [
        _row(
            sensor, site, t0 + timedelta(minutes=step_minutes * i), start_level - slope_per_step * i
        )
        for i in range(n)
    ]


def make_periodic_series(
    *,
    n: int = 200,
    base: float = 2.0,
    amplitude: float = 0.4,
    period_steps: int = 48,
    sensor: str = "SYN_WL_A",
    site: str = "SYN_SITE_A",
    start: datetime | None = None,
    step_minutes: int = CADENCE_MINUTES,
) -> list[dict[str, Any]]:
    """Smooth periodic signal (deterministic sine, no randomness)."""
    import math

    t0 = start or datetime(2030, 1, 1, tzinfo=UTC)
    return [
        _row(
            sensor,
            site,
            t0 + timedelta(minutes=step_minutes * i),
            base + amplitude * math.sin(2 * math.pi * i / period_steps),
        )
        for i in range(n)
    ]


def make_two_datum_stations(
    *,
    n: int = 120,
    start: datetime | None = None,
) -> list[dict[str, Any]]:
    """Two gauges with different datums (19 m vs 0.2 m scale must not pool)."""
    t0 = start or datetime(2030, 1, 1, tzinfo=UTC)
    high = make_constant_series(
        n=n, level=19.0, sensor="SYN_WL_HIGH", site="SYN_SITE_HIGH", start=t0
    )
    low = make_constant_series(n=n, level=0.2, sensor="SYN_WL_LOW", site="SYN_SITE_LOW", start=t0)
    return high + low


def with_missing_slot(rows: list[dict[str, Any]], index: int) -> list[dict[str, Any]]:
    """One usable row turned into a missing sentinel (gap variant)."""
    out = [dict(r) for r in rows]
    out[index] = {
        **out[index],
        "value": None,
        "usable": False,
        "quality_flags": ["VALUE_MISSING_SENTINEL"],
    }
    return out


def with_missing_run(
    rows: list[dict[str, Any]], start_index: int, length: int
) -> list[dict[str, Any]]:
    """Internal missing run (never bridged by windowing)."""
    out = [dict(r) for r in rows]
    for i in range(start_index, min(start_index + length, len(out))):
        out[i] = {
            **out[i],
            "value": None,
            "usable": False,
            "quality_flags": ["VALUE_MISSING_SENTINEL"],
        }
    return out


def with_disconnected_windows(
    rows: list[dict[str, Any]], second_start_index: int, gap_minutes: int = 180
) -> list[dict[str, Any]]:
    """Split one capture into two windows separated by a long gap."""
    import copy

    out = copy.deepcopy(rows)
    shift = timedelta(minutes=gap_minutes)
    for i in range(second_start_index, len(out)):
        moved = datetime.fromisoformat(str(out[i]["observation_time_utc"])) + shift
        out[i]["observation_time_utc"] = moved.isoformat()
        out[i]["observation_time_local"] = moved.isoformat()
    return out
