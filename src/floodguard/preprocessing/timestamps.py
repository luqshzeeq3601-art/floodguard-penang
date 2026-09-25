"""Timestamp normalisation: a derived layer over raw records (policy: docs/TIMESTAMP_POLICY.md).

Works from the preserved source text (``source_time_raw``), never from the raw layer's naive
parse, and never writes to the raw store. Pure and deterministic: the "future" check compares
against an injected reference instant (the record's ``retrieved_at`` in the batch path), so the
same records always give the same output.

- The source's timezone is taken from the text when it carries ``Z``/an offset
  (``EXPLICIT_IN_SOURCE``); otherwise from ``SOURCE_TIMEZONE_POLICY`` (``UNSPECIFIED_ASSUMED``);
  a source without a policy gets no local/UTC instant (``UNSPECIFIED_TIMEZONE``).
- Date-only values stay calendar-date labels (``observation_date_local``); no midnight instant.
- ``retrieved_at`` is never used as a substitute for a missing observation time.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from zoneinfo import ZoneInfo

from floodguard.ingestion.adapters.data_gov_my import SOURCE as SOURCE_DATA_GOV_MY
from floodguard.ingestion.adapters.jps import RAINFALL_LISTING, WATER_LEVEL_LISTING
from floodguard.ingestion.adapters.jps_common import HISTORY_TIME_FORMAT
from floodguard.station_master import SOURCE_JPS

SCHEMA_VERSION = "timestamp_normalization/v1"
# Observation times later than reference + skew are FUTURE; exactly at the boundary is not.
FUTURE_SKEW = timedelta(minutes=10)
ISO_8601 = "ISO_8601"  # TimeFormat.pattern for ISO 8601 date-times (optional Z/offset)
_ISO_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?P<sec>:\d{2})?(?:Z|[+-]\d{2}:\d{2})?", re.ASCII
)


class Precision(StrEnum):
    DATE = "DATE"
    MINUTE = "MINUTE"
    SECOND = "SECOND"


class TimezoneStatus(StrEnum):
    EXPLICIT_IN_SOURCE = "EXPLICIT_IN_SOURCE"  # Z or offset in the text itself
    UNSPECIFIED_ASSUMED = "UNSPECIFIED_ASSUMED"  # no zone in text; policy assumption applied
    UNSPECIFIED_NO_POLICY = "UNSPECIFIED_NO_POLICY"  # no zone in text and no policy


class TimestampFlag(StrEnum):
    VALID = "VALID"
    MISSING = "MISSING"  # None, empty or whitespace-only
    INVALID_FORMAT = "INVALID_FORMAT"  # no permitted format matches, or impossible date/time
    AMBIGUOUS = "AMBIGUOUS"  # local time repeated or skipped in the assumed zone
    FUTURE = "FUTURE"  # later than reference + FUTURE_SKEW; values kept
    UNSPECIFIED_TIMEZONE = "UNSPECIFIED_TIMEZONE"  # parsed, but no zone: UTC not derivable


@dataclass(frozen=True)
class TimezonePolicy:
    assumed_zone: ZoneInfo
    rationale: str
    evidence: str
    evidence_date: str


_MALAYSIA = ZoneInfo("Asia/Kuala_Lumpur")  # the only zone constructed for normalisation

# THE source-timezone registry. Neither source documents a timezone (checked 2026-09-24).
SOURCE_TIMEZONE_POLICY: Mapping[str, TimezonePolicy] = MappingProxyType(
    {
        SOURCE_JPS: TimezonePolicy(
            assumed_zone=_MALAYSIA,
            rationale=(
                "No zone or offset in any listing or history response and none documented. "
                "Observed times are consistent with Malaysia local time (latest reading never "
                "after the local retrieval clock; history matches listing)."
            ),
            evidence=(
                "data/metadata/jps/HISTORICAL_AVAILABILITY.md#timezone; "
                "data/metadata/jps/LIVE_ACCESS.md; data/metadata/jps/README.md"
            ),
            evidence_date="2026-09-24",
        ),
        SOURCE_DATA_GOV_MY: TimezonePolicy(
            assumed_zone=_MALAYSIA,
            rationale=(
                "Forecast 'date' is a naive calendar date with no documented zone; the first "
                "date equals the Malaysian date at retrieval [inferred]."
            ),
            evidence="data/metadata/metmalaysia/ACCESS.md",
            evidence_date="2026-09-24",
        ),
    }
)


@dataclass(frozen=True)
class TimeFormat:
    pattern: str  # strptime pattern (strict round-trip) or ISO_8601
    precision: Precision  # for ISO_8601, MINUTE/SECOND is taken from the text


# Formats verified in captured payloads (docs/TIMESTAMP_POLICY.md, "Observed formats").
DATASET_FORMATS: Mapping[tuple[str, str], tuple[TimeFormat, ...]] = MappingProxyType(
    {
        (SOURCE_JPS, RAINFALL_LISTING.dataset): (
            TimeFormat(RAINFALL_LISTING.time_format, Precision.SECOND),
        ),
        (SOURCE_JPS, WATER_LEVEL_LISTING.dataset): (
            TimeFormat(WATER_LEVEL_LISTING.time_format, Precision.MINUTE),
        ),
        (SOURCE_JPS, "rainfall_history"): (TimeFormat(HISTORY_TIME_FORMAT, Precision.MINUTE),),
        (SOURCE_JPS, "water_level_history"): (TimeFormat(HISTORY_TIME_FORMAT, Precision.MINUTE),),
        (SOURCE_DATA_GOV_MY, "weather_forecast"): (TimeFormat("%Y-%m-%d", Precision.DATE),),
    }
)


@dataclass(frozen=True)
class NormalizedTimestamp:
    observation_time_raw: str | None  # exactly as in the raw record
    timestamp_quality_flag: TimestampFlag
    observation_time_local: str | None = None  # ISO 8601 with offset
    observation_time_utc: str | None = None  # ISO 8601, +00:00
    observation_date_local: str | None = None  # DATE precision only (calendar label)
    precision: Precision | None = None
    timezone_name: str | None = None  # IANA key (assumed) or the explicit zone label
    timezone_status: TimezoneStatus | None = None


def _parse(text: str, fmt: TimeFormat) -> tuple[datetime, Precision] | None:
    if fmt.pattern == ISO_8601:
        m = _ISO_RE.fullmatch(text)
        if m is None:
            return None
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        return dt, Precision.SECOND if m["sec"] else Precision.MINUTE
    try:
        # Naive wall time on purpose; the zone comes from the text or the policy below.
        dt = datetime.strptime(text, fmt.pattern)  # noqa: DTZ007
    except ValueError:
        return None
    # Strict: reject unpadded or otherwise non-canonical variants of the verified format.
    return (dt, fmt.precision) if dt.strftime(fmt.pattern) == text else None


def _unique_local(naive: datetime, zone: ZoneInfo) -> bool:
    """False when the wall time is repeated (fold) or skipped (gap) in ``zone``."""
    return naive.replace(tzinfo=zone, fold=0).utcoffset() == (
        naive.replace(tzinfo=zone, fold=1).utcoffset()
    )


def normalize(
    raw: str | None,
    source: str,
    formats: Sequence[TimeFormat],
    *,
    reference_utc: datetime,
    skew: timedelta = FUTURE_SKEW,
) -> NormalizedTimestamp:
    """Normalise one source time. ``reference_utc`` (tz-aware) is only the FUTURE bound."""
    if reference_utc.utcoffset() is None:
        raise ValueError("reference_utc must be timezone-aware")
    text = (raw or "").strip()  # outer whitespace ignored for parsing; raw kept verbatim
    if not text:
        return NormalizedTimestamp(raw, TimestampFlag.MISSING)
    parsed = next((p for f in formats if (p := _parse(text, f)) is not None), None)
    if parsed is None:
        return NormalizedTimestamp(raw, TimestampFlag.INVALID_FORMAT)
    dt, precision = parsed
    policy = SOURCE_TIMEZONE_POLICY.get(source)
    if dt.tzinfo is not None:
        local, zone_name, status = dt, dt.tzname(), TimezoneStatus.EXPLICIT_IN_SOURCE
    elif policy is None:
        return NormalizedTimestamp(
            raw,
            TimestampFlag.UNSPECIFIED_TIMEZONE,
            observation_date_local=dt.date().isoformat() if precision is Precision.DATE else None,
            precision=precision,
            timezone_status=TimezoneStatus.UNSPECIFIED_NO_POLICY,
        )
    else:
        zone = policy.assumed_zone
        local, zone_name, status = (
            dt.replace(tzinfo=zone),
            zone.key,
            TimezoneStatus.UNSPECIFIED_ASSUMED,
        )
        if precision is Precision.DATE:  # calendar label only; no FUTURE check (forecast dates)
            return NormalizedTimestamp(
                raw,
                TimestampFlag.VALID,
                observation_date_local=dt.date().isoformat(),
                precision=precision,
                timezone_name=zone_name,
                timezone_status=status,
            )
        if not _unique_local(dt, zone):
            return NormalizedTimestamp(
                raw,
                TimestampFlag.AMBIGUOUS,
                precision=precision,
                timezone_name=zone_name,
                timezone_status=status,
            )
    utc = local.astimezone(UTC)
    return NormalizedTimestamp(
        raw,
        TimestampFlag.FUTURE if utc > reference_utc + skew else TimestampFlag.VALID,
        observation_time_local=local.isoformat(),
        observation_time_utc=utc.isoformat(),
        precision=precision,
        timezone_name=zone_name,
        timezone_status=status,
    )


def normalize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """One derived row for one raw record (``raw_record/v1``); the record is not modified."""
    key = (record["source"], record["dataset"])
    if key not in DATASET_FORMATS:
        raise ValueError(f"no verified timestamp format for {key}")
    nt = normalize(
        record["source_time_raw"],
        record["source"],
        DATASET_FORMATS[key],
        reference_utc=datetime.fromisoformat(record["retrieved_at"]),
    )
    return {
        "timestamp_schema_version": SCHEMA_VERSION,
        "ingestion_batch_id": record["ingestion_batch_id"],
        "payload_sha256": record["payload_sha256"],
        "source": record["source"],
        "dataset": record["dataset"],
        "source_row_index": record["source_row_index"],
        "source_station_id": record["source_station_id"],
        "fg_sensor_id": record["fg_sensor_id"],
        "source_time_field": record["source_time_field"],
        "retrieved_at": record["retrieved_at"],
        "future_skew_seconds": int(FUTURE_SKEW.total_seconds()),
        **asdict(nt),
    }


@dataclass(frozen=True)
class MonotonicityReport:
    checked: int  # rows with a UTC instant
    non_monotonic_positions: tuple[int, ...]  # row index earlier than the preceding instant
    duplicate_groups: tuple[tuple[str, tuple[int, ...]], ...]  # (UTC instant, row indexes)
    unplaced_positions: tuple[int, ...]  # rows without a UTC instant (not compared)

    @property
    def is_monotonic(self) -> bool:
        return not self.non_monotonic_positions and not self.duplicate_groups


def check_monotonic(rows: Sequence[tuple[int, str | None]]) -> MonotonicityReport:
    """Report ordering problems in source order; never reorders or drops.

    ``rows`` are ``(source_row_index, observation_time_utc)`` in source sequence.
    """
    previous: datetime | None = None
    backwards: list[int] = []
    unplaced: list[int] = []
    groups: dict[datetime, list[int]] = defaultdict(list)
    for index, utc_text in rows:
        if utc_text is None:
            unplaced.append(index)
            continue
        t = datetime.fromisoformat(utc_text)
        if previous is not None and t < previous:
            backwards.append(index)
        groups[t].append(index)
        previous = t
    dups = tuple(
        (t.astimezone(UTC).isoformat(), tuple(ix)) for t, ix in groups.items() if len(ix) > 1
    )
    return MonotonicityReport(
        checked=len(rows) - len(unplaced),
        non_monotonic_positions=tuple(backwards),
        duplicate_groups=dups,
        unplaced_positions=tuple(unplaced),
    )
