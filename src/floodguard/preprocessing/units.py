"""Unit and measurement-semantics validation: a derived layer over raw records.

Policy and evidence: docs/UNIT_POLICY.md.

One registry (``UNIT_POLICIES``) says which source fields are promoted to a canonical
measurement type and unit, and on what evidence; ``EXCLUDED_FIELDS`` lists measurement-like fields
whose semantics are not verified, so they are reported but never promoted. Everything else in a
raw record (IDs, names, times, severity codes, categorical text) is not unit-validated.

Pure and deterministic; no conversion (every verified source uses one unit), no range bounds, no
imputation. The unit status is kept apart from the value status: a ``-9999`` in a verified field
is a VALID-unit row whose value is a SOURCE_MARKER. ``parsed_value`` is set only when both the
unit is VALID and the value is NUMERIC, so unverified fields can never leak as numbers.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from floodguard.ingestion.adapters.data_gov_my import SOURCE as SOURCE_DATA_GOV_MY
from floodguard.ingestion.adapters.jps_common import MISSING_SENTINEL, NO_DATA_MARKER
from floodguard.station_master import SOURCE_JPS, SensorType, ThresholdType

SCHEMA_VERSION = "unit_validation/v1"
POLICY_VERSION = "unit_policy/v1"


class MeasurementType(StrEnum):
    RAINFALL_INTERVAL = "RAINFALL_INTERVAL"  # rain in the 5-min interval ending at the row time
    RAINFALL_1H_TOTAL = "RAINFALL_1H_TOTAL"  # listing "Jumlah 1 Jam" (window alignment unverified)
    WATER_LEVEL = "WATER_LEVEL"
    WATER_LEVEL_THRESHOLD = "WATER_LEVEL_THRESHOLD"
    FORECAST_TEMPERATURE_MIN = "FORECAST_TEMPERATURE_MIN"  # daily forecast minimum for `date`
    FORECAST_TEMPERATURE_MAX = "FORECAST_TEMPERATURE_MAX"


class UnitProvenance(StrEnum):
    IN_PAYLOAD = "IN_PAYLOAD"  # unit text is part of the published field label
    OFFICIAL_UI_OR_DOCS = "OFFICIAL_UI_OR_DOCS"  # official page labels / API documentation
    INFERRED = "INFERRED"  # reasoned from values only; never canonical


class SemanticsStatus(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"


class UnitStatus(StrEnum):
    VALID = "VALID"
    MISSING_UNIT = "MISSING_UNIT"  # unit must be in the payload label, and the label has none
    UNKNOWN_UNIT = "UNKNOWN_UNIT"  # unit text is not a representation any policy accepts
    UNIT_MISMATCH = "UNIT_MISMATCH"  # a known unit, but another measurement's (e.g. m on rain)
    SENSOR_TYPE_MISMATCH = "SENSOR_TYPE_MISMATCH"  # field on the wrong sensor type
    UNKNOWN_MEASUREMENT_SEMANTICS = "UNKNOWN_MEASUREMENT_SEMANTICS"  # excluded or unregistered


class ValueParseStatus(StrEnum):
    NUMERIC = "NUMERIC"
    SOURCE_MARKER = "SOURCE_MARKER"  # -9999 (numerically), ERROR, Tiada Data
    EMPTY = "EMPTY"  # JSON null / absent / blank or whitespace-only text
    NON_NUMERIC = "NON_NUMERIC"  # anything else (e.g. "1,2", "abc", "nan")


class FieldRole(StrEnum):
    PRIMARY_VALUE = "PRIMARY_VALUE"  # the raw record's value_field / value_raw
    THRESHOLD = "THRESHOLD"  # a key of threshold_values_raw
    SOURCE_FIELD = "SOURCE_FIELD"  # another source_fields_raw key named by the policy


# Canonical unit -> exact source representations accepted (outer whitespace ignored). Only
# representations seen in payloads or official labels; no case or spelling variants invented.
ACCEPTED_SOURCE_UNITS: Mapping[str, frozenset[str]] = {
    "mm": frozenset({"mm"}),
    "m": frozenset({"m"}),
    "°C": frozenset({"°C"}),
}
_KNOWN_UNITS = frozenset().union(*ACCEPTED_SOURCE_UNITS.values())
SOURCE_MARKERS = frozenset({MISSING_SENTINEL, "ERROR", NO_DATA_MARKER})
_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)
_RF, _WL = SensorType.RAINFALL.value, SensorType.WATER_LEVEL.value


@dataclass(frozen=True)
class UnitPolicy:
    """A promoted field. ``field`` is the exact source key, or a label template whose ``{unit}``
    placeholder captures the unit printed in the payload (IN_PAYLOAD provenance)."""

    source: str
    dataset: str
    field: str
    measurement_type: MeasurementType
    canonical_unit: str
    unit_provenance: UnitProvenance
    expected_sensor_type: str | None  # None: the source has no JPS sensor (forecasts)
    evidence: str
    threshold_category: ThresholdType | None = None
    semantics_status: SemanticsStatus = SemanticsStatus.VERIFIED


@dataclass(frozen=True)
class ExcludedField:
    """A measurement-like field that is never promoted. ``{any}`` matches a dated label part."""

    source: str
    dataset: str
    field: str
    reason: str
    evidence: str


_HIST = "data/metadata/jps/HISTORICAL_AVAILABILITY.md"
_RF_UNIT = f"{_HIST} Rainfall 'Units' (graph-page labels 'Data Hujan (mm)', axis 'Hujan (mm)')"
_WL_UNIT = f"{_HIST} Water Level 'Units' (graph-page labels 'Aras Air (m)')"
_THR_UNIT = (
    f"{_HIST} Water Level 'Units' (graph-page tooltip 'Normal: ...m Waspada: ...m Amaran: ...m "
    "Bahaya: ...m'); category from the listing markup <th id='alert'>Waspada</th>, "
    "id='warning' Amaran, id='danger' Bahaya (tests/fixtures/jps/aras_air_data_PNG_trimmed.html)"
)
_WL_THRESHOLDS = {
    ThresholdType.NORMAL: ("Normal", "normal"),
    ThresholdType.WASPADA: ("Waspada", "alert"),
    ThresholdType.AMARAN: ("Amaran", "warning"),
    ThresholdType.BAHAYA: ("Bahaya", "danger"),
}


def _wl_threshold(dataset: str, field: str, category: ThresholdType) -> UnitPolicy:
    return UnitPolicy(
        SOURCE_JPS,
        dataset,
        field,
        MeasurementType.WATER_LEVEL_THRESHOLD,
        "m",
        UnitProvenance.OFFICIAL_UI_OR_DOCS,
        _WL,
        _THR_UNIT,
        threshold_category=category,
    )


UNIT_POLICIES: tuple[UnitPolicy, ...] = (
    UnitPolicy(
        SOURCE_JPS,
        "rainfall_listing",
        "Jumlah 1 Jam(Terkini)",
        MeasurementType.RAINFALL_1H_TOTAL,
        "mm",
        UnitProvenance.OFFICIAL_UI_OR_DOCS,
        _RF,
        f"{_RF_UNIT}; header 'Jumlah 1 Jam' (1-hour total) in payload; trailing vs clock-hour "
        "window unobserved (data/metadata/jps/LIVE_ACCESS.md, dry period)",
    ),
    UnitPolicy(
        SOURCE_JPS,
        "rainfall_history",
        "raw",
        MeasurementType.RAINFALL_INTERVAL,
        "mm",
        UnitProvenance.OFFICIAL_UI_OR_DOCS,
        _RF,
        f"{_RF_UNIT}; {_HIST} Rainfall 'Semantics': raw = 5-min interval ending at dt, equals "
        "the cyearly step in every checked pair (high confidence)",
    ),
    UnitPolicy(
        SOURCE_JPS,
        "water_level_listing",
        "Aras Air ({unit})(Graf)",
        MeasurementType.WATER_LEVEL,
        "m",
        UnitProvenance.IN_PAYLOAD,
        _WL,
        "listing header 'Aras Air (m)' (data/metadata/jps/README.md water-level inventory)",
    ),
    UnitPolicy(
        SOURCE_JPS,
        "water_level_history",
        "final",
        MeasurementType.WATER_LEVEL,
        "m",
        UnitProvenance.OFFICIAL_UI_OR_DOCS,
        _WL,
        f"{_WL_UNIT}; {_HIST} Water Level 'Fields': the official page plots final",
    ),
    *(
        _wl_threshold("water_level_listing", f"Tahap Nilai Ambang {label}", cat)
        for cat, (label, _) in _WL_THRESHOLDS.items()
    ),
    *(_wl_threshold("water_level_history", key, cat) for cat, (_, key) in _WL_THRESHOLDS.items()),
    *(
        UnitPolicy(
            SOURCE_DATA_GOV_MY,
            "weather_forecast",
            key,
            mt,
            "°C",
            UnitProvenance.OFFICIAL_UI_OR_DOCS,
            None,
            "data/metadata/metmalaysia/ACCESS.md section 1A 'Units': min_temp/max_temp are "
            "integers in °C [doc]",
        )
        for key, mt in (
            ("min_temp", MeasurementType.FORECAST_TEMPERATURE_MIN),
            ("max_temp", MeasurementType.FORECAST_TEMPERATURE_MAX),
        )
    ),
)

_SEM = f"{_HIST} Rainfall 'Semantics'"
EXCLUDED_FIELDS: tuple[ExcludedField, ...] = (
    *(
        ExcludedField(SOURCE_JPS, "rainfall_history", key, reason, _SEM)
        for key, reason in (
            ("clean", "value depends on the request datafreq (5-min step or trailing 15-min sum)"),
            ("chourly", "meaning unknown (equalled clean in inspected rows)"),
            ("c15min", "meaning unknown (equalled clean in inspected rows)"),
            ("tdaily", "meaning unknown (0 in every inspected row, also when -9999 elsewhere)"),
            ("cdaily", "running daily total: day boundary held, one unexplained window; derivable"),
            ("cyearly", "running yearly total: not promoted in policy v1 (derivable from raw)"),
        )
    ),
    *(
        ExcludedField(
            SOURCE_JPS,
            "rainfall_history",
            key,
            "rainfall threshold: unit and accumulation period not labelled",
            f"{_HIST} Rainfall 'Thresholds'",
        )
        for key in ("light", "moderate", "heavy", "veryheavy")
    ),
    ExcludedField(
        SOURCE_JPS,
        "rainfall_listing",
        "Taburan Hujan Harian {any}",
        "listing daily total: day boundary not verified for the listing",
        f"{_SEM} (cdaily vs listing daily total, one station); docs/RAW_INGESTION_DESIGN.md §10",
    ),
    ExcludedField(
        SOURCE_JPS,
        "rainfall_listing",
        "Taburan Hujan dari Tengah Malam ({any})",
        "since-midnight total: semantics not verified",
        "data/metadata/jps/LIVE_ACCESS.md (rainfall dynamics unobserved)",
    ),
    *(
        ExcludedField(
            SOURCE_JPS,
            "water_level_history",
            key,
            reason,
            f"{_HIST} Water Level 'Fields' / 'Missing representation'",
        )
        for key, reason in (
            ("raw", "pre-QC reading; semantics undocumented (ERROR rows hold raw only)"),
            ("ecm", "ECM meaning undocumented"),
            ("clean", "relationship to final undocumented"),
        )
    ),
    ExcludedField(
        SOURCE_DATA_GOV_MY,
        "weather_forecast",
        "summary_forecast",
        "categorical forecast text, not a numeric measurement",
        "data/metadata/metmalaysia/ACCESS.md section 1A 'Units'",
    ),
)


def _template_re(field: str) -> re.Pattern[str]:
    pat = re.escape(field).replace(r"\{unit\}", r"(?P<unit>[^()]*)").replace(r"\{any\}", "[^()]*")
    return re.compile(pat)


def check_policy(
    policies: Iterable[UnitPolicy], excluded: Iterable[ExcludedField]
) -> dict[tuple[str, str], list[tuple[re.Pattern[str], UnitPolicy | ExcludedField]]]:
    """Validate the registry invariants and index it; raises ``ValueError`` on a violation."""
    index: dict[tuple[str, str], list[tuple[re.Pattern[str], UnitPolicy | ExcludedField]]] = {}
    keys: set[tuple[str, str, str]] = set()
    entries: list[UnitPolicy | ExcludedField] = [*policies, *excluded]
    for e in entries:
        key = (e.source, e.dataset, e.field)
        if key in keys:
            raise ValueError(f"field registered twice: {key}")
        keys.add(key)
        if isinstance(e, UnitPolicy):
            if e.semantics_status is not SemanticsStatus.VERIFIED:
                raise ValueError(f"unverified semantics cannot be canonical: {key}")
            if e.unit_provenance is UnitProvenance.INFERRED:
                raise ValueError(f"inferred unit cannot be canonical: {key}")
            if e.canonical_unit not in ACCEPTED_SOURCE_UNITS:
                raise ValueError(f"no accepted representations for unit {e.canonical_unit!r}")
            if (e.unit_provenance is UnitProvenance.IN_PAYLOAD) != ("{unit}" in e.field):
                raise ValueError(f"IN_PAYLOAD needs a {{unit}} label template (and only it): {key}")
            is_threshold = e.measurement_type is MeasurementType.WATER_LEVEL_THRESHOLD
            if is_threshold != (e.threshold_category is not None):
                raise ValueError(f"threshold category must be set exactly for thresholds: {key}")
        index.setdefault((e.source, e.dataset), []).append((_template_re(e.field), e))
    return index


_INDEX = check_policy(UNIT_POLICIES, EXCLUDED_FIELDS)


def lookup(
    source: str, dataset: str, field: str
) -> tuple[UnitPolicy | ExcludedField | None, str | None]:
    """(entry, unit text captured from the label) for one source field; (None, None) if unknown."""
    for pat, entry in _INDEX.get((source, dataset), ()):
        m = pat.fullmatch(field)
        if m:
            return entry, m.groupdict().get("unit")
    return None, None


def parse_value(value_raw: str | None) -> tuple[ValueParseStatus, float | None]:
    """Classify value text; the number is returned only for NUMERIC (0 stays 0.0)."""
    if value_raw is None or not value_raw.strip():
        return ValueParseStatus.EMPTY, None
    text = value_raw.strip()
    if text in SOURCE_MARKERS:
        return ValueParseStatus.SOURCE_MARKER, None
    if not _NUMBER_RE.fullmatch(text):
        return ValueParseStatus.NON_NUMERIC, None
    number = float(text)
    if number == float(MISSING_SENTINEL):  # "-9999.0" is the same documented sentinel
        return ValueParseStatus.SOURCE_MARKER, None
    return ValueParseStatus.NUMERIC, number


@dataclass(frozen=True)
class UnitValidationResult:
    source_field: str
    field_role: FieldRole
    value_raw: str | None  # exactly as in the raw record
    value_parse_status: ValueParseStatus
    parsed_value: float | None  # only when VALID unit and NUMERIC value
    source_unit_raw: str | None  # unit text printed in the payload label (IN_PAYLOAD only)
    raw_record_unit: str | None  # adapter-assigned raw ``unit`` (primary value only)
    measurement_type: MeasurementType | None
    canonical_unit: str | None
    unit_provenance: UnitProvenance | None
    semantics_status: SemanticsStatus
    threshold_category: ThresholdType | None
    unit_validation_status: UnitStatus
    reason: str | None  # None only when VALID


def _unit_problem(text: str | None, canonical: str, what: str) -> tuple[UnitStatus, str] | None:
    if text is None:
        return None
    t = text.strip()
    if t in ACCEPTED_SOURCE_UNITS[canonical]:
        return None
    if t in _KNOWN_UNITS:
        return UnitStatus.UNIT_MISMATCH, f"{what} {text!r} is not {canonical!r}"
    return UnitStatus.UNKNOWN_UNIT, f"{what} {text!r} is not an accepted unit"


def validate_unit(
    *,
    source: str,
    dataset: str,
    source_field: str,
    field_role: FieldRole,
    value_raw: str | None,
    sensor_type: str | None,
    raw_record_unit: str | None = None,
) -> UnitValidationResult:
    """Validate one source field. Check order: semantics, sensor type, payload unit, record unit."""
    parse_status, number = parse_value(value_raw)
    entry, label_unit = lookup(source, dataset, source_field)

    def result(
        status: UnitStatus, reason: str | None, policy: UnitPolicy | None = None
    ) -> UnitValidationResult:
        valid = status is UnitStatus.VALID
        return UnitValidationResult(
            source_field=source_field,
            field_role=field_role,
            value_raw=value_raw,
            value_parse_status=parse_status,
            parsed_value=number if valid else None,
            source_unit_raw=label_unit,
            raw_record_unit=raw_record_unit,
            measurement_type=policy.measurement_type if policy else None,
            canonical_unit=policy.canonical_unit if policy else None,
            unit_provenance=policy.unit_provenance if policy else None,
            semantics_status=policy.semantics_status if policy else SemanticsStatus.UNVERIFIED,
            threshold_category=policy.threshold_category if policy else None,
            unit_validation_status=status,
            reason=reason,
        )

    if entry is None:
        return result(UnitStatus.UNKNOWN_MEASUREMENT_SEMANTICS, "field not in the unit policy")
    if isinstance(entry, ExcludedField):
        return result(UnitStatus.UNKNOWN_MEASUREMENT_SEMANTICS, f"excluded: {entry.reason}")
    if sensor_type != entry.expected_sensor_type:
        return result(
            UnitStatus.SENSOR_TYPE_MISMATCH,
            f"{entry.measurement_type} expects sensor {entry.expected_sensor_type}, "
            f"record has {sensor_type}",
            entry,
        )
    if entry.unit_provenance is UnitProvenance.IN_PAYLOAD and not (label_unit or "").strip():
        return result(UnitStatus.MISSING_UNIT, "field label carries no unit", entry)
    for text, what in ((label_unit, "label unit"), (raw_record_unit, "raw record unit")):
        problem = _unit_problem(text, entry.canonical_unit, what)
        if problem:
            return result(*problem, entry)
    return result(UnitStatus.VALID, None, entry)


def record_fields(record: Mapping[str, Any]) -> list[tuple[str, FieldRole, str | None]]:
    """(field, role, value text) to validate: the primary value, every published threshold, and
    other source fields the policy names (promoted or excluded). Order is the record's order."""
    fields: list[tuple[str, FieldRole, str | None]] = [
        (record["value_field"], FieldRole.PRIMARY_VALUE, record["value_raw"])
    ]
    thresholds: Mapping[str, str | None] = record.get("threshold_values_raw") or {}
    fields += [(k, FieldRole.THRESHOLD, v) for k, v in thresholds.items()]
    seen = {f for f, _, _ in fields}
    for k, v in record["source_fields_raw"].items():
        if k not in seen and lookup(record["source"], record["dataset"], k)[0] is not None:
            fields.append((k, FieldRole.SOURCE_FIELD, v))
    return fields


def validate_record(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Derived rows for one raw record (``raw_record/v1``); the record is not modified."""
    rows = []
    for field, role, value in record_fields(record):
        res = validate_unit(
            source=record["source"],
            dataset=record["dataset"],
            source_field=field,
            field_role=role,
            value_raw=value,
            sensor_type=record["sensor_type"],
            raw_record_unit=record["unit"] if role is FieldRole.PRIMARY_VALUE else None,
        )
        rows.append(
            {
                "unit_schema_version": SCHEMA_VERSION,
                "unit_policy_version": POLICY_VERSION,
                "ingestion_batch_id": record["ingestion_batch_id"],
                "payload_sha256": record["payload_sha256"],
                "source": record["source"],
                "dataset": record["dataset"],
                "source_row_index": record["source_row_index"],
                "source_station_id": record["source_station_id"],
                "sensor_type": record["sensor_type"],
                "source_time_raw": record["source_time_raw"],
                "threshold_temporal_scope": (
                    record.get("threshold_temporal_scope") if role is FieldRole.THRESHOLD else None
                ),
                **asdict(res),
            }
        )
    return rows
