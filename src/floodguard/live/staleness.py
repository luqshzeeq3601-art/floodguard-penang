"""Stale-station detection (Phase 10, Task 3).

Versioned, source/sensor-aware policy based on documented source cadence
(``data/metadata/jps/LIVE_ACCESS.md``). The dashboard keeps reporting factual
age-in-minutes only; this module adds an explicit verdict layer for operations.

Cadence evidence:
- F2 stations publish every 15 min in sync, lag 4-7 min.
- Other stations publish asynchronously on 5-min-aligned times, no fixed cadence.

Policy ``stale_policy/v1``:
- Sensors with a known expected interval (station master
  ``fg_expected_listing_interval_minutes``, i.e. F2 = 15) are evaluable.
- Sensors without a known interval yield ``UNKNOWN`` (never a stale verdict).
- A sensor is ``STALE`` only when its age exceeds ``stale_after_minutes``.
  Default ``stale_after_minutes = 60`` for 15-min cadence (four missed batches
  plus lag allowance); configurable per policy instance and recorded in output.
- ``INVALID`` when the observation time is missing/unparseable or more than
  5 min in the future (mirrors the discovery Future tolerance, not a verdict).

The provisional discovery ``FRESH/DELAYED/STALE`` 30/180 thresholds are NOT
reused; this policy is separately versioned and tested at its boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final

from floodguard.preprocessing.timestamps import SOURCE_TIMEZONE_POLICY
from floodguard.station_master import SOURCE_JPS

STALE_POLICY_VERSION: Final[str] = "stale_policy/v1"
ASSUMED_ZONE: Final[str] = "Asia/Kuala_Lumpur"
FUTURE_TOLERANCE_MINUTES: Final[int] = 5
DEFAULT_STALE_AFTER_MINUTES: Final[int] = 60

# Single timezone source: reuse the registry zone (TIMESTAMP_POLICY.md).
# No direct zone construction here; the registry owns the single instance.
_MYT = SOURCE_TIMEZONE_POLICY[SOURCE_JPS].assumed_zone
assert _MYT.key == ASSUMED_ZONE


class StationState(StrEnum):
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"


@dataclass(frozen=True)
class StalePolicy:
    """Versioned stale-detection policy."""

    version: str = STALE_POLICY_VERSION
    stale_after_minutes: int = DEFAULT_STALE_AFTER_MINUTES

    def __post_init__(self) -> None:
        if not self.stale_after_minutes > 0:
            raise ValueError("stale_after_minutes must be positive")


@dataclass(frozen=True)
class StaleVerdict:
    sensor_id: str
    state: StationState
    age_minutes: float | None
    expected_interval_minutes: int | None
    policy_version: str
    reason: str


def age_minutes(observed_utc: datetime | None, now_utc: datetime) -> float | None:
    """Factual age in minutes (None when the instant is unknown)."""
    if observed_utc is None:
        return None
    moment = observed_utc if observed_utc.tzinfo is not None else observed_utc.replace(tzinfo=UTC)
    now = now_utc if now_utc.tzinfo is not None else now_utc.replace(tzinfo=UTC)
    return (now - moment).total_seconds() / 60.0


def parse_assumed_local(raw: str | None) -> datetime | None:
    """Parse a JPS display time as assumed Asia/Kuala_Lumpur (None when unusable)."""
    if raw is None or not raw.strip():
        return None
    text = raw.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            naive = datetime.strptime(text, fmt)  # noqa: DTZ007
            return naive.replace(tzinfo=_MYT)
        except ValueError:
            continue
    return None


def evaluate_sensor(
    sensor_id: str,
    *,
    observed_utc: datetime | None,
    now_utc: datetime,
    expected_interval_minutes: int | None,
    policy: StalePolicy | None = None,
) -> StaleVerdict:
    """Verdict for one sensor (no I/O, deterministic, boundary-tested)."""
    active_policy = policy or StalePolicy()
    age = age_minutes(observed_utc, now_utc)
    if age is None:
        return StaleVerdict(
            sensor_id,
            StationState.INVALID,
            None,
            expected_interval_minutes,
            active_policy.version,
            "observation time missing or unparseable",
        )
    if age < -FUTURE_TOLERANCE_MINUTES:
        return StaleVerdict(
            sensor_id,
            StationState.INVALID,
            age,
            expected_interval_minutes,
            active_policy.version,
            "observation time is in the future",
        )
    if expected_interval_minutes is None:
        return StaleVerdict(
            sensor_id,
            StationState.UNKNOWN,
            age,
            None,
            active_policy.version,
            "no verified cadence for this sensor",
        )
    if age > active_policy.stale_after_minutes:
        return StaleVerdict(
            sensor_id,
            StationState.STALE,
            age,
            expected_interval_minutes,
            active_policy.version,
            f"age {age:.1f} min exceeds stale_after {active_policy.stale_after_minutes} min",
        )
    return StaleVerdict(
        sensor_id,
        StationState.ACTIVE,
        age,
        expected_interval_minutes,
        active_policy.version,
        "within stale_after bound",
    )
