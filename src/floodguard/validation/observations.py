"""Canonical long-form observation table from quality rows (docs/HISTORICAL_PIPELINE.md).

Identity: ``(source, fg_sensor_id, observation_time)`` (docs/STATION_MASTER_DESIGN.md section 12),
with ``observation_time`` = ``observation_time_utc``. A sensor can publish more than one verified
measurement for one instant (a rain gauge's 5-min interval and its 1-hour total), so each
``measurement_type`` is its own value column of that observation: rows are keyed by the identity
plus ``measurement_type``. No other identity is used.

Only rows with a mapped sensor, a VALID instant, a VALID unit and an observation measurement type
enter; everything else is counted by reason. Rows whose value is a source marker or empty stay in
with ``value`` null, so missingness remains visible. Duplicates across batches (overlapping
history windows, repeated listing snapshots, listing vs history) are detected here; the raw layer
is never touched. Identical repeats collapse to one row that lists every source row; conflicting
values are never resolved: the row keeps ``value`` null, ``DUPLICATE_CONFLICT`` and the candidates.
No gaps are filled and no rows are invented. Pure and deterministic; output is sorted by sensor,
measurement type and time.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any

from floodguard.preprocessing.timestamps import TimestampFlag
from floodguard.preprocessing.units import MeasurementType, UnitStatus, ValueParseStatus
from floodguard.validation.quality_flags import PipelineJoinError, QualityFlag, is_usable

SCHEMA_VERSION = "observations/v1"
OBSERVATION_TYPES = frozenset(
    {
        MeasurementType.RAINFALL_INTERVAL,
        MeasurementType.RAINFALL_1H_TOTAL,
        MeasurementType.WATER_LEVEL,
    }
)
Key = tuple[str, str, str, str]  # source, fg_sensor_id, measurement_type, observation_time_utc


class Exclusion(StrEnum):
    NOT_A_STATION_OBSERVATION = "NOT_A_STATION_OBSERVATION"  # forecasts, unpromoted fields
    UNIT_NOT_VALID = "UNIT_NOT_VALID"
    NO_CANONICAL_SENSOR = "NO_CANONICAL_SENSOR"  # unmapped, invalid ID, quarantined
    NO_VALID_OBSERVATION_TIME = "NO_VALID_OBSERVATION_TIME"  # incl. FUTURE, AMBIGUOUS


class DuplicateStatus(StrEnum):
    UNIQUE = "UNIQUE"
    IDENTICAL = "IDENTICAL"  # several source rows, same value representation
    CONFLICT = "CONFLICT"  # several source rows, different values: value left null


class ConflictReason(StrEnum):
    NUMERIC_VALUES_DIFFER = "NUMERIC_VALUES_DIFFER"
    MARKER_VS_NUMERIC = "MARKER_VS_NUMERIC"
    MARKERS_DIFFER = "MARKERS_DIFFER"


def exclusion(row: Mapping[str, Any]) -> Exclusion | None:
    """Why a quality row cannot enter the canonical table (None: it enters)."""
    if row["measurement_type"] not in OBSERVATION_TYPES:
        return Exclusion.NOT_A_STATION_OBSERVATION
    if row["unit_validation_status"] != UnitStatus.VALID:
        return Exclusion.UNIT_NOT_VALID
    if row["fg_sensor_id"] is None or row["raw_file"] != "records":
        return Exclusion.NO_CANONICAL_SENSOR
    if row["timestamp_quality_flag"] != TimestampFlag.VALID or not row["observation_time_utc"]:
        return Exclusion.NO_VALID_OBSERVATION_TIME
    return None


def _signature(row: Mapping[str, Any]) -> str:
    if row["value_parse_status"] == ValueParseStatus.NUMERIC:
        return f"NUMERIC:{float(row['parsed_value']) + 0.0!r}"  # + 0.0 folds -0.0 into 0.0
    return f"{row['value_parse_status']}:{(row['value_raw'] or '').strip()}"


def _conflict_reason(signatures: Iterable[str]) -> ConflictReason:
    numeric = {s.startswith("NUMERIC:") for s in signatures}
    if numeric == {True}:
        return ConflictReason.NUMERIC_VALUES_DIFFER
    return (
        ConflictReason.MARKER_VS_NUMERIC
        if numeric == {True, False}
        else ConflictReason.MARKERS_DIFFER
    )


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text)


def _order(row: Mapping[str, Any]) -> tuple[datetime, str, int, str]:
    return (
        _instant(row["retrieved_at"]),
        row["ingestion_batch_id"],
        row["source_row_index"],
        row["source_field"],
    )


def build_observations(
    quality_rows: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    """(canonical rows, exclusion counts ``{reason: {dataset: n}}``)."""
    groups: dict[Key, list[Mapping[str, Any]]] = defaultdict(list)
    excluded: dict[str, Counter[str]] = defaultdict(Counter)
    for r in quality_rows:
        reason = exclusion(r)
        if reason is not None:
            excluded[reason][r["dataset"]] += 1
            continue
        key = (r["source"], r["fg_sensor_id"], r["measurement_type"], r["observation_time_utc"])
        groups[key].append(r)

    out = []
    for key in sorted(groups, key=lambda k: (k[0], k[1], k[2], _instant(k[3]))):
        members = sorted(groups[key], key=_order)
        for field in ("fg_site_id", "canonical_unit", "observation_time_local", "sensor_type"):
            if len({m[field] for m in members}) != 1:
                raise PipelineJoinError(f"canonical key {key}: members disagree on {field}")
        out.append(_resolve(key, members))
    return out, {k: dict(sorted(v.items())) for k, v in sorted(excluded.items())}


def _resolve(key: Key, members: list[Mapping[str, Any]]) -> dict[str, Any]:
    rep = members[0]  # earliest capture; only its metadata is used when values conflict
    signatures = sorted({_signature(m) for m in members})
    flags = {f for m in members for f in m["quality_flags"]}
    conflict = len(signatures) > 1
    if conflict:
        status = DuplicateStatus.CONFLICT
        flags.add(QualityFlag.DUPLICATE_CONFLICT)
    elif len(members) > 1:
        status = DuplicateStatus.IDENTICAL
        flags.add(QualityFlag.DUPLICATE_IDENTICAL)
    else:
        status = DuplicateStatus.UNIQUE
    value = None if conflict else rep["parsed_value"]
    quality_flags = sorted(flags)
    source, sensor, measurement, utc = key
    return {
        "observation_schema_version": SCHEMA_VERSION,
        "source": source,
        "fg_site_id": rep["fg_site_id"],
        "fg_sensor_id": sensor,
        "sensor_type": rep["sensor_type"],
        "measurement_type": measurement,
        "observation_time_utc": utc,
        "observation_time_local": rep["observation_time_local"],
        "timezone_name": rep["timezone_name"],
        "timezone_status": rep["timezone_status"],
        "value": value,
        "unit": rep["canonical_unit"],
        "value_raw": None if conflict else rep["value_raw"],
        "value_parse_status": None if conflict else rep["value_parse_status"],
        "quality_flags": quality_flags,
        "usable": value is not None and is_usable(quality_flags),
        "duplicate_status": status,
        "duplicate_count": len(members),
        "conflict_reason": _conflict_reason(signatures) if conflict else None,
        "conflicting_values": signatures if conflict else [],
        "first_retrieved_at": rep["retrieved_at"],
        "datasets": sorted({m["dataset"] for m in members}),
        "provenance": [
            {
                "ingestion_batch_id": m["ingestion_batch_id"],
                "payload_sha256": m["payload_sha256"],
                "dataset": m["dataset"],
                "source_row_index": m["source_row_index"],
                "source_field": m["source_field"],
                "retrieved_at": m["retrieved_at"],
                "value_signature": _signature(m),  # what this capture said (as-of joins)
            }
            for m in members
        ],
    }
