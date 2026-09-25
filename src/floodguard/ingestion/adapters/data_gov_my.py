"""data.gov.my Weather API forecast adapter (CC BY 4.0; data by MET Malaysia).

One raw record per forecast record (location x date), every key kept as published. The API has
no station master in FloodGuard, so mapping is NOT_APPLICABLE; Penang filtering (via
``data/metadata/metmalaysia/penang_locations.csv``) belongs to the validation layer.
Schema and caveats: data/metadata/metmalaysia/ACCESS.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from floodguard.ingestion.adapters.jps import decode
from floodguard.ingestion.contracts import (
    ParsedRow,
    ParseResult,
    PayloadError,
    QuarantineReason,
    SchemaError,
)

SOURCE = "DATA_GOV_MY_WEATHER_API"
FORECAST_URL = "https://api.data.gov.my/weather/forecast"
LICENCE = "CC-BY-4.0 (https://creativecommons.org/licenses/by/4.0/)"
ATTRIBUTION = (
    "Weather forecast data: MET Malaysia, via the data.gov.my Weather API "
    "(https://api.data.gov.my/weather), licensed under CC BY 4.0 "
    "(https://creativecommons.org/licenses/by/4.0/)."
)
REQUIRED_KEYS = ("location", "date")


def _text(v: Any) -> str | None:
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, bool):
        return "true" if v else "false"
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class WeatherForecastAdapter:
    source: str = SOURCE
    dataset: str = "weather_forecast"
    parser_name: str = "floodguard.ingestion.adapters.data_gov_my.weather_forecast"
    parser_version: str = "1.0.0"
    payload_extension: str = "json"
    requires_station_mapping: bool = False
    licence: str = LICENCE
    attribution: str | None = ATTRIBUTION
    partition: str | None = None

    def parse(self, payload: bytes) -> ParseResult:
        try:
            doc = json.loads(decode(payload), parse_float=str, parse_int=str)
        except json.JSONDecodeError as e:
            raise PayloadError(f"forecast: response is not JSON ({e.msg})") from e
        if not isinstance(doc, list):
            raise SchemaError(f"forecast: top level is {type(doc).__name__}, expected list")
        present = {k for r in doc if isinstance(r, dict) for k in r}
        absent = [k for k in REQUIRED_KEYS if k not in present]
        if doc and absent:
            raise SchemaError(f"forecast: expected keys missing from every record: {absent}")
        rows = []
        for i, r in enumerate(doc):
            rec = r if isinstance(r, dict) else {}
            loc = rec.get("location")
            loc = loc if isinstance(loc, dict) else {}
            fields = {str(k): _text(v) for k, v in rec.items()} if rec else {"value": _text(r)}
            day = rec.get("date")
            problem: QuarantineReason | None = None
            detail: str | None = None
            if not isinstance(loc.get("location_id"), str):
                problem = QuarantineReason.INVALID_ROW_STRUCTURE
                detail = "location.location_id missing"
            elif not isinstance(day, str) or not day.strip():
                problem, detail = QuarantineReason.MISSING_TIMESTAMP, "date blank or absent"
            else:
                try:
                    date.fromisoformat(day)
                except ValueError:
                    problem = QuarantineReason.UNPARSEABLE_TIMESTAMP
                    detail = f"date {day!r} not ISO"
            rows.append(
                ParsedRow(
                    source_row_index=i,
                    source_line=None,
                    source_station_id=_text(loc.get("location_id")),
                    source_display_station_id=None,
                    source_station_name=_text(loc.get("location_name")),
                    sensor_type=None,
                    measurement_type="weather_forecast",
                    source_time_raw=_text(day),
                    source_time_field="date",
                    observation_time_naive=None,  # forecast valid *date*; no time of day
                    value_field="summary_forecast",
                    value_raw=_text(rec.get("summary_forecast")),
                    unit=None,  # categorical text; min_temp/max_temp (degC) in source_fields_raw
                    unit_basis="NONE",
                    source_fields_raw=fields,
                    structural_error=problem,
                    structural_detail=detail,
                )
            )
        return ParseResult(tuple(rows))
