"""JPS Public Infobanjir adapters: state listings (HTML) and station history (JSON).

Input is the bytes of one captured response; no network I/O happens here (fetching JPS needs
permission, see ``floodguard.ingestion.fetch``). Every cell/key is kept as published: ``-9999``,
``ERROR``, blanks, ``Tiada Data`` and ``0`` are data, not errors. Only structure is checked:

- document-level contract broken (headers, JSON shape, a key missing from every row) ->
  ``SchemaError`` -> the whole batch FAILS;
- one row broken (cell count, no graph link, key missing, time blank/unparseable) -> that row is
  quarantined with a ``QuarantineReason`` and the rest of the batch continues.

HTML cell text is taken with outer whitespace stripped (the payload file keeps the exact bytes).
JSON numbers keep their token text (``parse_int=str``/``parse_float=str``); JSON ``null`` -> None.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from floodguard.ingestion.adapters.jps_common import (
    HISTORY_TIME_FORMAT,
    HISTORY_VALUE_KEYS,
    NO_DATA_MARKER,
    NO_RESULT_MARKER,
    ResultTableParser,
)
from floodguard.ingestion.contracts import (
    ParsedRow,
    ParseResult,
    PayloadError,
    QuarantineReason,
    SchemaError,
)
from floodguard.station_master import MEASUREMENT, SOURCE_JPS, SensorType

PARSER_VERSION = "1.0.0"
LICENCE = "JPS copyright notice: PERMISSION REQUIRED (docs/DATA_LICENSING_AND_ACCESS.md)"
CURRENT_AT_RETRIEVAL = "CURRENT_AT_RETRIEVAL"
# History responses carry today's thresholds for any requested window (HISTORICAL_AVAILABILITY.md).
CURRENT_NOT_HISTORICAL = "CURRENT_NOT_HISTORICAL"
SOURCE_HEADER = "SOURCE_HEADER"
SOURCE_DOCUMENTATION = "SOURCE_DOCUMENTATION"  # unit from official graph-page labels, not payload
# Observed jps_internal_id shapes (scripts/probe_jps_history.py STATION_RE), whitespace stripped.
PARTITION_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")


def decode(payload: bytes) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as e:
        raise PayloadError(f"payload is not valid UTF-8 ({e.reason} at byte {e.start})") from e


def _parse_time(
    text: str | None, fmt: str
) -> tuple[str | None, QuarantineReason | None, str | None]:
    """(naive ISO, problem, detail). Naive on purpose: JPS declares no timezone."""
    if text is None or text.strip() == "":
        return None, QuarantineReason.MISSING_TIMESTAMP, "observation time blank or absent"
    try:
        return datetime.strptime(text, fmt).isoformat(), None, None  # noqa: DTZ007
    except ValueError:
        return None, QuarantineReason.UNPARSEABLE_TIMESTAMP, f"time {text!r} not {fmt!r}"


# ---------------------------------------------------------------- listings (HTML)


def _rainfall_labels(h: list[str]) -> list[str]:
    # Bil, ID, name, district, last update | daily-group | since-midnight | 1 h | 6 dates
    return [*h[0:5], *(f"{h[5]} {d}" for d in h[8:14]), h[6], h[7]]


def _water_level_labels(h: list[str]) -> list[str]:
    # Bil .. level (8) | threshold group | Normal, Waspada, Amaran, Bahaya
    return [*h[0:8], *(f"{h[8]} {t}" for t in h[9:13])]


@dataclass(frozen=True)
class JpsListingAdapter:
    dataset: str
    sensor: SensorType
    link_marker: str
    required_headers: tuple[str, ...]
    header_count: int
    labels: Callable[[list[str]], list[str]]
    time_col: int
    time_format: str
    value_col: int
    unit_basis: str
    threshold_cols: tuple[int, ...] = ()
    source: str = SOURCE_JPS
    parser_version: str = PARSER_VERSION
    payload_extension: str = "html"
    requires_station_mapping: bool = True
    licence: str = LICENCE
    attribution: str | None = None
    partition: str | None = None

    @property
    def parser_name(self) -> str:
        return f"floodguard.ingestion.adapters.jps.{self.dataset}"

    def parse(self, payload: bytes) -> ParseResult:
        html = decode(payload)
        p = ResultTableParser(self.link_marker)
        p.feed(html)
        p.close()
        missing = [h for h in self.required_headers if not any(h in x for x in p.headers)]
        if missing:
            raise SchemaError(f"listing: expected headers not found: {missing}")
        if len(p.headers) != self.header_count:
            raise SchemaError(
                f"listing: {len(p.headers)} header cells, expected {self.header_count}"
            )
        if not p.rows:
            if NO_DATA_MARKER in html:
                raise SchemaError(f"listing: source returned '{NO_DATA_MARKER}' (no station rows)")
            raise SchemaError("listing: no station rows found")
        labels = self.labels(p.headers)
        measurement, unit = MEASUREMENT[self.sensor]
        rows = []
        for i, (cells, link_id, line) in enumerate(
            zip(p.rows, p.link_ids, p.row_lines, strict=True)
        ):
            ok_shape = len(cells) == len(labels)
            fields: dict[str, str | None] = (
                dict(zip(labels, cells, strict=True))
                if ok_shape
                else {f"cell_{n}": c for n, c in enumerate(cells)}
            )
            problem: QuarantineReason | None = None
            detail: str | None = None
            naive = None
            if not ok_shape:
                problem = QuarantineReason.INVALID_ROW_STRUCTURE
                detail = f"{len(cells)} cells, expected {len(labels)}"
            elif not link_id:
                problem = QuarantineReason.INVALID_ROW_STRUCTURE
                detail = f"{self.link_marker} stationid link missing"
            else:
                naive, problem, detail = _parse_time(cells[self.time_col], self.time_format)

            def cell(col: int, cells: list[str] = cells, ok: bool = ok_shape) -> str | None:
                return cells[col] if ok else None

            rows.append(
                ParsedRow(
                    source_row_index=i,
                    source_line=line,
                    source_station_id=link_id or None,
                    source_display_station_id=cell(1),
                    source_station_name=cell(2),
                    sensor_type=self.sensor.value,
                    measurement_type=measurement,
                    source_time_raw=cell(self.time_col),
                    source_time_field=labels[self.time_col],
                    observation_time_naive=naive,
                    value_field=labels[self.value_col],
                    value_raw=cell(self.value_col),
                    unit=unit,
                    unit_basis=self.unit_basis,
                    source_fields_raw=fields,
                    threshold_values_raw=(
                        {labels[c]: cell(c) for c in self.threshold_cols}
                        if self.threshold_cols
                        else None
                    ),
                    threshold_temporal_scope=CURRENT_AT_RETRIEVAL if self.threshold_cols else None,
                    structural_error=problem,
                    structural_detail=detail,
                )
            )
        return ParseResult(tuple(rows))


RAINFALL_LISTING = JpsListingAdapter(
    dataset="rainfall_listing",
    sensor=SensorType.RAINFALL,
    link_marker="rf-graph",
    required_headers=("ID Stesen", "Nama Stesen", "Daerah", "Kemaskini Terakhir", "Jumlah 1 Jam"),
    header_count=14,
    labels=_rainfall_labels,
    time_col=4,
    time_format="%d/%m/%Y %H:%M:%S",
    value_col=12,  # "Jumlah 1 Jam (Terkini)"; daily/since-midnight totals stay in source_fields_raw
    unit_basis=SOURCE_DOCUMENTATION,  # listing headers carry no unit; mm per rf-graph labels
)

WATER_LEVEL_LISTING = JpsListingAdapter(
    dataset="water_level_listing",
    sensor=SensorType.WATER_LEVEL,
    link_marker="wl-graph",
    required_headers=(
        "ID Stesen",
        "Nama Stesen",
        "Daerah",
        "Lembangan",
        "Sub Lembangan",
        "Kemaskini Terakhir",
        "Aras Air (m)",
        "Tahap Nilai Ambang",
        "Normal",
        "Waspada",
        "Amaran",
        "Bahaya",
    ),
    header_count=13,
    labels=_water_level_labels,
    time_col=6,
    time_format="%d/%m/%Y %H:%M",
    value_col=7,
    unit_basis=SOURCE_HEADER,  # "Aras Air (m)"
    threshold_cols=(8, 9, 10, 11),
)


# ---------------------------------------------------------------- history (JSON)


def _json_text(v: Any) -> str | None:
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "true" if v else "false"
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"))


HISTORY_THRESHOLD_KEYS = {
    SensorType.RAINFALL: ("light", "moderate", "heavy", "veryheavy"),  # unit/period unlabelled
    SensorType.WATER_LEVEL: ("normal", "alert", "warning", "danger"),  # metres
}


@dataclass(frozen=True)
class JpsHistoryAdapter:
    """One station's date-range history response. The payload has no station ID, so the ID
    requested (``source_station_id``) is supplied by the caller and checked against the
    ``station`` parameter of ``source_reference`` when that is a URL carrying one. Identical
    bodies occur for different stations (e.g. "No result"), so the station key is the batch
    ``partition``: part of the idempotency key and of the storage path."""

    dataset: str
    sensor: SensorType
    value_field: str
    source_station_id: str
    source_reference: str
    source: str = SOURCE_JPS
    parser_version: str = PARSER_VERSION
    payload_extension: str = "json"
    requires_station_mapping: bool = True
    licence: str = LICENCE
    attribution: str | None = None

    @property
    def parser_name(self) -> str:
        return f"floodguard.ingestion.adapters.jps.{self.dataset}"

    @property
    def partition(self) -> str:
        return self.source_station_id.strip()

    def parse(self, payload: bytes) -> ParseResult:
        url_station = parse_qs(urlparse(self.source_reference).query, keep_blank_values=True).get(
            "station"
        )
        if url_station and url_station[0] != self.source_station_id:
            raise PayloadError(
                f"source_station_id {self.source_station_id!r} does not match the "
                f"source_reference station parameter {url_station[0]!r}"
            )
        text = decode(payload)
        try:
            doc = json.loads(text, parse_float=str, parse_int=str)
        except json.JSONDecodeError as e:
            if NO_RESULT_MARKER in text:  # observed reply for ranges without stored data
                return ParseResult((), source_no_result=True)
            raise PayloadError(f"history: response is not JSON: {text.strip()[:80]!r}") from e
        if not isinstance(doc, dict) or not isinstance(doc.get("info"), dict):
            raise SchemaError("history: response lacks an 'info' object")
        values = doc.get("values")
        if not isinstance(values, list):
            raise SchemaError("history: 'values' list missing")
        keys = HISTORY_VALUE_KEYS[MEASUREMENT[self.sensor][0]]
        present = {k for v in values if isinstance(v, dict) for k in v}
        absent = [k for k in keys if k not in present]
        if values and absent:
            raise SchemaError(f"history: expected keys missing from every row: {absent}")
        info = {str(k): _json_text(v) for k, v in doc["info"].items()}
        thresholds = {k: info[k] for k in HISTORY_THRESHOLD_KEYS[self.sensor] if k in info}
        measurement, unit = MEASUREMENT[self.sensor]
        rows = []
        for i, v in enumerate(values):
            if isinstance(v, dict):
                fields = {str(k): _json_text(x) for k, x in v.items()}
                lacking = [k for k in keys if k not in v]
            else:
                fields, lacking = {"value": _json_text(v)}, list(keys)
            naive, problem, detail = None, None, None
            if lacking:
                problem = QuarantineReason.INVALID_ROW_STRUCTURE
                detail = f"row missing keys {lacking}"
            else:
                naive, problem, detail = _parse_time(fields["dt"], HISTORY_TIME_FORMAT)
            rows.append(
                ParsedRow(
                    source_row_index=i,
                    source_line=None,
                    source_station_id=self.source_station_id,
                    source_display_station_id=None,  # not published in history responses
                    source_station_name=info.get("name"),
                    sensor_type=self.sensor.value,
                    measurement_type=measurement,
                    source_time_raw=fields.get("dt"),
                    source_time_field="dt",
                    observation_time_naive=naive,
                    value_field=self.value_field,
                    value_raw=fields.get(self.value_field),
                    unit=unit,
                    unit_basis=SOURCE_DOCUMENTATION,
                    source_fields_raw=fields,
                    threshold_values_raw=thresholds or None,
                    threshold_temporal_scope=CURRENT_NOT_HISTORICAL if thresholds else None,
                    source_metadata_raw=info,
                    structural_error=problem,
                    structural_detail=detail,
                )
            )
        return ParseResult(tuple(rows))


def history_adapter(
    sensor: SensorType, source_station_id: str, source_reference: str
) -> JpsHistoryAdapter:
    """Primary value: rainfall ``raw`` (5-min increment; ``clean`` depends on ``datafreq``),
    water level ``final`` (the field the official page plots). Raises ``ValueError`` for an ID
    that cannot name a partition (checked before any batch starts)."""
    if not PARTITION_RE.match(source_station_id.strip()):
        raise ValueError(f"source_station_id {source_station_id!r} is not a jps_internal_id")
    if sensor is SensorType.RAINFALL:
        return JpsHistoryAdapter(
            "rainfall_history", sensor, "raw", source_station_id, source_reference
        )
    return JpsHistoryAdapter(
        "water_level_history", sensor, "final", source_station_id, source_reference
    )
