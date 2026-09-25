"""Data-quality checks over the validated and canonical layers (docs/HISTORICAL_PIPELINE.md §5).

Each check is an invariant the pipeline promises; a failure means a defect, so the build writes no
processed output. They do not judge whether the data is "good" (that is the quality summary's job)
and add no physical range rules. Pure and deterministic.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from itertools import pairwise
from typing import Any

from floodguard.preprocessing.timestamps import FUTURE_SKEW, TimezoneStatus
from floodguard.preprocessing.units import MeasurementType, ValueParseStatus
from floodguard.validation.observations import OBSERVATION_TYPES, DuplicateStatus, exclusion
from floodguard.validation.quality_flags import RAINFALL_TYPES, QualityFlag, is_usable
from floodguard.validation.summary import MISSING_VALUE_FLAGS

Row = Mapping[str, Any]
UNITS = {
    MeasurementType.RAINFALL_INTERVAL: "mm",
    MeasurementType.RAINFALL_1H_TOTAL: "mm",
    MeasurementType.WATER_LEVEL: "m",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    failing: int
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _key(o: Row) -> tuple[str, str, str, datetime]:
    return (
        o["source"],
        o["fg_sensor_id"],
        o["measurement_type"],
        datetime.fromisoformat(o["observation_time_utc"]),
    )


def _rowwise(name: str, rows: Sequence[Row], bad: Callable[[Row], bool], what: str) -> CheckResult:
    n = sum(1 for r in rows if bad(r))
    return CheckResult(name, n == 0, n, what if n else "ok")


def _value_consistent(o: Row) -> bool:
    numeric = o["value_parse_status"] == ValueParseStatus.NUMERIC
    if (o["value"] is not None) != numeric:
        return False
    flags = set(o["quality_flags"])
    if o["value"] is None:  # missingness must be explained, never silent
        return bool(flags & (MISSING_VALUE_FLAGS | {QualityFlag.DUPLICATE_CONFLICT}))
    return not flags & MISSING_VALUE_FLAGS


def run_checks(obs: Sequence[Row], quality_rows: Sequence[Row]) -> list[CheckResult]:
    keys = [_key(o) for o in obs]
    dup_keys = sum(n - 1 for n in Counter(keys).values() if n > 1)
    unordered = sum(1 for a, b in pairwise(keys) if a >= b)

    def ref(r: Row) -> tuple[str, int, str]:
        return r["ingestion_batch_id"], r["source_row_index"], r["source_field"]

    entering = Counter(ref(q) for q in quality_rows if exclusion(q) is None)
    collapsed = Counter(ref(p) for o in obs for p in o["provenance"])
    lost = sum(((entering - collapsed) + (collapsed - entering)).values())
    known_flags = {f.value for f in QualityFlag}
    return [
        CheckResult("canonical_key_unique", dup_keys == 0, dup_keys, "repeated canonical keys"),
        CheckResult(
            "chronological_order",
            unordered == 0,
            unordered,
            "rows not strictly ordered by source, sensor, measurement type, time",
        ),
        CheckResult(
            "no_row_lost",
            lost == 0,
            lost,
            "eligible quality rows and table provenance differ (lost, extra or repeated rows)",
        ),
        _rowwise(
            "verified_measurement_types_only",
            obs,
            lambda o: o["measurement_type"] not in OBSERVATION_TYPES,
            "measurement type outside the verified unit policy",
        ),
        _rowwise(
            "unit_matches_measurement_type",
            obs,
            lambda o: UNITS.get(o["measurement_type"]) != o["unit"],
            "unit is not the canonical unit of its measurement type",
        ),
        _rowwise(
            "identity_complete",
            obs,
            lambda o: not (o["fg_sensor_id"] and o["fg_site_id"] and o["observation_time_utc"]),
            "missing fg_sensor_id, fg_site_id or observation_time_utc",
        ),
        _rowwise(
            "value_matches_status_and_flags",
            obs,
            lambda o: not _value_consistent(o),
            "value/null does not match value_parse_status or missing-value flags",
        ),
        _rowwise(
            "zero_is_not_missing",
            [*obs, *quality_rows],
            lambda r: (
                r.get("value", r.get("parsed_value")) == 0
                and bool(set(r["quality_flags"]) & MISSING_VALUE_FLAGS)
            ),
            "a zero value carries a missing-value flag",
        ),
        _rowwise(
            "usable_matches_flags",
            obs,
            lambda o: o["usable"] != (o["value"] is not None and is_usable(o["quality_flags"])),
            "usable disagrees with value and flags",
        ),
        _rowwise(
            "no_future_observation",
            obs,
            lambda o: (
                datetime.fromisoformat(o["observation_time_utc"])
                > datetime.fromisoformat(o["first_retrieved_at"]) + FUTURE_SKEW
            ),
            "observation later than its first capture + skew",
        ),
        _rowwise(
            "timezone_assumption_marked",
            obs,
            lambda o: (
                o["timezone_status"] is None
                or (
                    o["timezone_status"] == TimezoneStatus.UNSPECIFIED_ASSUMED
                    and QualityFlag.TIMEZONE_ASSUMED not in o["quality_flags"]
                )
            ),
            "timezone status missing or assumption not flagged",
        ),
        _rowwise(
            "provenance_complete",
            obs,
            lambda o: (
                o["duplicate_count"] != len(o["provenance"])
                or not o["provenance"]
                or (o["duplicate_count"] == 1) != (o["duplicate_status"] == DuplicateStatus.UNIQUE)
                or any(
                    p["ingestion_batch_id"] is None or p["source_row_index"] is None
                    for p in o["provenance"]
                )
            ),
            "provenance count/status mismatch or missing batch/row reference",
        ),
        _rowwise(
            "conflicts_unresolved",
            obs,
            lambda o: (
                o["duplicate_status"] == DuplicateStatus.CONFLICT
                and not (o["value"] is None and len(o["conflicting_values"]) >= 2)
            ),
            "a conflicting key was given a value",
        ),
        _rowwise(
            "usable_rainfall_non_negative",
            obs,
            lambda o: o["usable"] and o["measurement_type"] in RAINFALL_TYPES and o["value"] < 0,
            "usable negative rainfall",
        ),
        _rowwise(
            "quality_flags_known",
            [*obs, *quality_rows],
            lambda r: (
                not set(r["quality_flags"]) <= known_flags
                or r["quality_flags"] != sorted(set(r["quality_flags"]))
            ),
            "unknown, unsorted or repeated quality flag",
        ),
    ]
