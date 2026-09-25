"""Data-quality flags: one derived row per raw record and measurement field (docs/QUALITY_FLAGS.md).

Combines the statuses the three component layers already produced (timestamps, station IDs,
units); it never re-parses times, re-resolves IDs or re-validates units. Flags are granular and
several may apply to one row. They describe data quality only and are unrelated to the JPS flood
severity categories (Normal/Waspada/Amaran/Bahaya), which are never used here.

A row whose components cannot be joined one-to-one (missing, duplicated or orphan component rows,
or rows that disagree on provenance) is a pipeline defect: ``PipelineJoinError`` is raised instead
of emitting a data-quality flag. Pure and deterministic.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from floodguard.ingestion.adapters.jps_common import NO_DATA_MARKER
from floodguard.ingestion.contracts import MappingStatus, QuarantineReason
from floodguard.ingestion.station_mapping import IdMappingStatus
from floodguard.preprocessing.station_ids import raw_mapping_conflict
from floodguard.preprocessing.timestamps import Precision, TimestampFlag, TimezoneStatus
from floodguard.preprocessing.units import FieldRole, MeasurementType, UnitStatus, ValueParseStatus

SCHEMA_VERSION = "quality_flags/v1"
Key = tuple[str, int]  # (ingestion_batch_id, source_row_index)


class PipelineJoinError(RuntimeError):
    """Component layers do not join one-to-one with the raw records (a pipeline defect)."""


class QualityFlag(StrEnum):
    # structure / raw layer
    RAW_QUARANTINED = "RAW_QUARANTINED"
    ROW_STRUCTURE_INVALID = "ROW_STRUCTURE_INVALID"
    # timestamp layer
    TIMESTAMP_MISSING = "TIMESTAMP_MISSING"
    TIMESTAMP_INVALID_FORMAT = "TIMESTAMP_INVALID_FORMAT"
    TIMESTAMP_AMBIGUOUS = "TIMESTAMP_AMBIGUOUS"
    TIMESTAMP_FUTURE = "TIMESTAMP_FUTURE"
    TIMESTAMP_UNSPECIFIED_TIMEZONE = "TIMESTAMP_UNSPECIFIED_TIMEZONE"
    TIMESTAMP_DATE_ONLY = "TIMESTAMP_DATE_ONLY"
    TIMEZONE_ASSUMED = "TIMEZONE_ASSUMED"
    # station-ID layer
    NO_STATION_SENSOR = "NO_STATION_SENSOR"  # source has no station master (forecasts)
    SENSOR_UNMAPPED = "SENSOR_UNMAPPED"
    SOURCE_ID_INVALID = "SOURCE_ID_INVALID"
    SENSOR_TYPE_MISMATCH = "SENSOR_TYPE_MISMATCH"
    SENSOR_TYPE_INVALID = "SENSOR_TYPE_INVALID"
    STATION_MASTER_CHANGED_SINCE_INGEST = "STATION_MASTER_CHANGED_SINCE_INGEST"
    # unit layer
    UNIT_MISSING = "UNIT_MISSING"
    UNIT_UNKNOWN = "UNIT_UNKNOWN"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    UNIT_SENSOR_TYPE_MISMATCH = "UNIT_SENSOR_TYPE_MISMATCH"
    MEASUREMENT_SEMANTICS_UNKNOWN = "MEASUREMENT_SEMANTICS_UNKNOWN"
    # value (source markers kept apart; zero is a valid number and never flagged)
    VALUE_MISSING_SENTINEL = "VALUE_MISSING_SENTINEL"  # -9999
    VALUE_SOURCE_ERROR = "VALUE_SOURCE_ERROR"  # ERROR
    VALUE_NO_DATA_MARKER = "VALUE_NO_DATA_MARKER"  # Tiada Data
    VALUE_EMPTY = "VALUE_EMPTY"
    VALUE_NON_NUMERIC = "VALUE_NON_NUMERIC"
    RAINFALL_NEGATIVE = "RAINFALL_NEGATIVE"  # definitional: accumulated rain cannot be < 0
    SOURCE_SEVERITY_ERROR = "SOURCE_SEVERITY_ERROR"  # JPS WL history QC field severity=ERROR
    # canonical table (floodguard.validation.observations)
    DUPLICATE_IDENTICAL = "DUPLICATE_IDENTICAL"
    DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"


# Informational flags keep a row usable; every other flag blocks use as a canonical observation.
INFORMATIONAL = frozenset(
    {
        QualityFlag.TIMEZONE_ASSUMED,
        QualityFlag.STATION_MASTER_CHANGED_SINCE_INGEST,
        QualityFlag.SOURCE_SEVERITY_ERROR,
        QualityFlag.DUPLICATE_IDENTICAL,
    }
)

_TS = {
    TimestampFlag.MISSING: QualityFlag.TIMESTAMP_MISSING,
    TimestampFlag.INVALID_FORMAT: QualityFlag.TIMESTAMP_INVALID_FORMAT,
    TimestampFlag.AMBIGUOUS: QualityFlag.TIMESTAMP_AMBIGUOUS,
    TimestampFlag.FUTURE: QualityFlag.TIMESTAMP_FUTURE,
    TimestampFlag.UNSPECIFIED_TIMEZONE: QualityFlag.TIMESTAMP_UNSPECIFIED_TIMEZONE,
}
_QUARANTINE = {
    QuarantineReason.MISSING_TIMESTAMP: QualityFlag.TIMESTAMP_MISSING,
    QuarantineReason.UNPARSEABLE_TIMESTAMP: QualityFlag.TIMESTAMP_INVALID_FORMAT,
    QuarantineReason.INVALID_ROW_STRUCTURE: QualityFlag.ROW_STRUCTURE_INVALID,
}  # UNMAPPED_SENSOR / INVALID_SOURCE_ID come from the station-ID layer
_STATION = {
    IdMappingStatus.UNMAPPED: QualityFlag.SENSOR_UNMAPPED,
    IdMappingStatus.INVALID_SOURCE_ID: QualityFlag.SOURCE_ID_INVALID,
    IdMappingStatus.SENSOR_TYPE_MISMATCH: QualityFlag.SENSOR_TYPE_MISMATCH,
    IdMappingStatus.INVALID_SENSOR_TYPE: QualityFlag.SENSOR_TYPE_INVALID,
}
_UNIT = {
    UnitStatus.MISSING_UNIT: QualityFlag.UNIT_MISSING,
    UnitStatus.UNKNOWN_UNIT: QualityFlag.UNIT_UNKNOWN,
    UnitStatus.UNIT_MISMATCH: QualityFlag.UNIT_MISMATCH,
    UnitStatus.SENSOR_TYPE_MISMATCH: QualityFlag.UNIT_SENSOR_TYPE_MISMATCH,
    UnitStatus.UNKNOWN_MEASUREMENT_SEMANTICS: QualityFlag.MEASUREMENT_SEMANTICS_UNKNOWN,
}
_VALUE = {
    ValueParseStatus.EMPTY: QualityFlag.VALUE_EMPTY,
    ValueParseStatus.NON_NUMERIC: QualityFlag.VALUE_NON_NUMERIC,
}
_MARKERS = {
    "ERROR": QualityFlag.VALUE_SOURCE_ERROR,
    NO_DATA_MARKER: QualityFlag.VALUE_NO_DATA_MARKER,
}
RAINFALL_TYPES = frozenset({MeasurementType.RAINFALL_INTERVAL, MeasurementType.RAINFALL_1H_TOTAL})


def is_usable(flags: Sequence[str]) -> bool:
    return all(QualityFlag(f) in INFORMATIONAL for f in flags)


def _key(row: Mapping[str, Any]) -> Key:
    return row["ingestion_batch_id"], row["source_row_index"]


def _index(rows: Sequence[Mapping[str, Any]], layer: str) -> dict[Key, Mapping[str, Any]]:
    out: dict[Key, Mapping[str, Any]] = {}
    for r in rows:
        if (k := _key(r)) in out:
            raise PipelineJoinError(f"{layer}: duplicate row for {k}")
        out[k] = r
    return out


def _check_same(record: Mapping[str, Any], row: Mapping[str, Any], layer: str) -> None:
    for f in ("payload_sha256", "source", "dataset"):
        if row[f] != record[f]:
            raise PipelineJoinError(f"{layer}: {f} differs for {_key(record)}")


def _value_flags(unit: Mapping[str, Any]) -> list[QualityFlag]:
    if unit["measurement_type"] is None:  # not a measurement: its value text is not assessed
        return []
    status = ValueParseStatus(unit["value_parse_status"])
    if status is ValueParseStatus.SOURCE_MARKER:
        text = (unit["value_raw"] or "").strip()
        return [_MARKERS.get(text, QualityFlag.VALUE_MISSING_SENTINEL)]
    if status in _VALUE:
        return [_VALUE[status]]
    mt, value = unit["measurement_type"], unit["parsed_value"]
    if mt in RAINFALL_TYPES and value is not None and value < 0:
        return [QualityFlag.RAINFALL_NEGATIVE]
    return []


def flag_batch(
    records: Sequence[Mapping[str, Any]],
    *,
    quarantined: bool,
    timestamp_rows: Sequence[Mapping[str, Any]],
    station_rows: Sequence[Mapping[str, Any]],
    unit_rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Quality rows for one raw records (or quarantine) file and its component-layer rows.

    One row per record for the primary value, plus one per other field the unit layer promoted
    to a measurement type (forecast min/max temperature). Thresholds are source metadata and stay
    in the unit layer. The timestamp layer does not cover quarantined rows, so ``timestamp_rows``
    must be empty for a quarantine file; ``station_rows`` may be empty only when no record has a
    station master (``mapping_status`` NOT_APPLICABLE).
    """
    recs = _index(records, "raw")
    ts = _index(timestamp_rows, "timestamps")
    sid = _index(station_rows, "station_ids")
    if quarantined and ts:
        raise PipelineJoinError("timestamps: quarantined rows are not normalised")
    if not quarantined and ts.keys() != recs.keys():
        raise PipelineJoinError("timestamps: rows do not match the raw records one-to-one")
    if sid and sid.keys() != recs.keys():
        raise PipelineJoinError("station_ids: rows do not match the raw records one-to-one")
    if not sid and any(r["mapping_status"] != MappingStatus.NOT_APPLICABLE for r in records):
        raise PipelineJoinError("station_ids: missing for records that need a station master")
    units: dict[Key, list[Mapping[str, Any]]] = {}
    for u in unit_rows:
        if _key(u) not in recs:
            raise PipelineJoinError(f"units: orphan row {_key(u)}")
        units.setdefault(_key(u), []).append(u)
    for k, us in units.items():
        fields = Counter((u["source_field"], u["field_role"]) for u in us)
        if max(fields.values()) > 1:
            raise PipelineJoinError(f"units: duplicate field row for {k}")

    out: list[dict[str, Any]] = []
    for k, rec in recs.items():
        t, s = ts.get(k), sid.get(k)
        for layer, row in (("timestamps", t), ("station_ids", s)):
            if row is not None:
                _check_same(rec, row, layer)
        if (rec["quarantine_reason"] is not None) != quarantined:
            raise PipelineJoinError(f"raw: quarantine_reason does not match the file for {k}")
        if t is not None and (
            t["fg_sensor_id"] != rec["fg_sensor_id"]
            or t["observation_time_raw"] != rec["source_time_raw"]
        ):
            raise PipelineJoinError(f"timestamps: sensor or time text differs from raw for {k}")
        if s is not None and (
            s["raw_fg_sensor_id"] != rec["fg_sensor_id"] or raw_mapping_conflict(s)
        ):
            raise PipelineJoinError(f"station_ids: fg_sensor_id conflicts with raw for {k}")
        rec_units = units.get(k, [])
        primary = [u for u in rec_units if u["field_role"] == FieldRole.PRIMARY_VALUE]
        if len(primary) != 1:
            raise PipelineJoinError(f"units: expected one PRIMARY_VALUE row for {k}")
        if (primary[0]["value_raw"], primary[0]["source_time_raw"]) != (
            rec["value_raw"],
            rec["source_time_raw"],
        ):
            raise PipelineJoinError(f"units: value or time text differs from raw for {k}")
        promoted = [
            u
            for u in rec_units
            if u["field_role"] == FieldRole.SOURCE_FIELD and u["measurement_type"] is not None
        ]
        base = _record_flags(rec, t, s, quarantined)
        for u in (*primary, *promoted):
            _check_same(rec, u, "units")
            flags = sorted({*base, *_unit_flags(u), *_value_flags(u)})
            out.append(_row(rec, t, s, u, flags, quarantined))
    return out


def _unit_flags(u: Mapping[str, Any]) -> list[QualityFlag]:
    status = UnitStatus(u["unit_validation_status"])
    return [] if status is UnitStatus.VALID else [_UNIT[status]]


def _record_flags(
    rec: Mapping[str, Any],
    t: Mapping[str, Any] | None,
    s: Mapping[str, Any] | None,
    quarantined: bool,
) -> set[QualityFlag]:
    flags: set[QualityFlag] = set()
    if quarantined:
        flags.add(QualityFlag.RAW_QUARANTINED)
        reason = rec["quarantine_reason"]
        if reason in _QUARANTINE:
            flags.add(_QUARANTINE[QuarantineReason(reason)])
    if t is not None:
        tf = TimestampFlag(t["timestamp_quality_flag"])
        if tf in _TS:
            flags.add(_TS[tf])
        if t["timezone_status"] == TimezoneStatus.UNSPECIFIED_ASSUMED:
            flags.add(QualityFlag.TIMEZONE_ASSUMED)
        if t["precision"] == Precision.DATE:
            flags.add(QualityFlag.TIMESTAMP_DATE_ONLY)
    if s is None:
        flags.add(QualityFlag.NO_STATION_SENSOR)
    else:
        status = IdMappingStatus(s["station_id_mapping_status"])
        if status in _STATION:
            flags.add(_STATION[status])
        if s["raw_fg_sensor_id"] != s["fg_sensor_id"]:
            flags.add(QualityFlag.STATION_MASTER_CHANGED_SINCE_INGEST)
    if (rec["source_fields_raw"].get("severity") or "").strip() == "ERROR" and rec[
        "dataset"
    ] == "water_level_history":
        flags.add(QualityFlag.SOURCE_SEVERITY_ERROR)
    return flags


def _row(
    rec: Mapping[str, Any],
    t: Mapping[str, Any] | None,
    s: Mapping[str, Any] | None,
    u: Mapping[str, Any],
    flags: list[QualityFlag],
    quarantined: bool,
) -> dict[str, Any]:
    def ts(field: str) -> Any:
        return t[field] if t is not None else None

    def st(field: str) -> Any:
        return s[field] if s is not None else None

    return {
        "quality_schema_version": SCHEMA_VERSION,
        "ingestion_batch_id": rec["ingestion_batch_id"],
        "payload_sha256": rec["payload_sha256"],
        "source": rec["source"],
        "dataset": rec["dataset"],
        "source_row_index": rec["source_row_index"],
        "raw_file": "quarantine" if quarantined else "records",
        "retrieved_at": rec["retrieved_at"],
        "source_station_id": rec["source_station_id"],
        "sensor_type": rec["sensor_type"],
        "fg_site_id": st("fg_site_id"),
        "fg_sensor_id": st("fg_sensor_id"),
        "observation_time_raw": rec["source_time_raw"],
        "observation_time_local": ts("observation_time_local"),
        "observation_time_utc": ts("observation_time_utc"),
        "observation_date_local": ts("observation_date_local"),
        "timezone_name": ts("timezone_name"),
        "timezone_status": ts("timezone_status"),
        "source_field": u["source_field"],
        "field_role": u["field_role"],
        "measurement_type": u["measurement_type"],
        "canonical_unit": u["canonical_unit"],
        "value_raw": u["value_raw"],
        "parsed_value": u["parsed_value"],
        # component statuses, preserved as produced
        "raw_quarantine_reason": rec["quarantine_reason"],
        "timestamp_quality_flag": ts("timestamp_quality_flag"),
        "station_id_mapping_status": st("station_id_mapping_status"),
        "unit_validation_status": u["unit_validation_status"],
        "value_parse_status": u["value_parse_status"],
        "timestamp_schema_version": ts("timestamp_schema_version"),
        "station_id_schema_version": st("station_id_schema_version"),
        "station_master_origin": st("station_master_origin"),
        "unit_schema_version": u["unit_schema_version"],
        "unit_policy_version": u["unit_policy_version"],
        "quality_flags": [f.value for f in flags],
        "usable": is_usable(flags) and u["parsed_value"] is not None,
    }
