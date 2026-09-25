"""Offline tests for raw-ingestion adapters, station mapping and the fetch permission boundary.

Fixtures: trimmed REAL JPS / data.gov.my captures (tests/fixtures/jps, tests/fixtures/metmalaysia;
provenance in their READMEs) and the SYNTHETIC station master (tests/fixtures/station_master).
Tests named ``test_synthetic_*`` mutate captures to create cases that were not captured.
Network is blocked for every test here (``no_network``).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from floodguard.ingestion.adapters.data_gov_my import ATTRIBUTION, WeatherForecastAdapter
from floodguard.ingestion.adapters.jps import (
    CURRENT_AT_RETRIEVAL,
    CURRENT_NOT_HISTORICAL,
    RAINFALL_LISTING,
    WATER_LEVEL_LISTING,
    history_adapter,
)
from floodguard.ingestion.adapters.jps_common import HISTORY_VALUE_KEYS
from floodguard.ingestion.contracts import PayloadError, QuarantineReason, SchemaError
from floodguard.ingestion.fetch import (
    OPEN_DATA_GOV_MY,
    AccessPermission,
    PermissionedFetcher,
    PermissionNotGrantedError,
    load_permission,
)
from floodguard.ingestion.station_mapping import SensorMapper, StationMappingError
from floodguard.station_master import SOURCE_JPS, SensorType, sensor_id

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
JPS = ROOT / "tests" / "fixtures" / "jps"
RF_HTML = (JPS / "searchresultrainfall_PNG_trimmed.html").read_bytes()
WL_HTML = (JPS / "aras_air_data_PNG_trimmed.html").read_bytes()
RF_HIST = (JPS / "history_rainfall_27608_20260918_trimmed.json").read_bytes()
WL_HIST = (JPS / "history_water_level_27608_20240924_trimmed.json").read_bytes()
NO_RESULT = (JPS / "history_no_result.txt").read_bytes()
FORECAST = (
    ROOT / "tests/fixtures/metmalaysia/weather_forecast_trimmed_20260924T112926+0800.json"
).read_bytes()
SYN_SENSORS = ROOT / "tests" / "fixtures" / "station_master" / "expected" / "sensors.csv"
WL_URL = "https://example.invalid/wl?station=27608&from=24/09/2024 00:00&datafreq=5"


# ---------------------------------------------------------------- JPS listings


def test_rainfall_listing_rows_verbatim() -> None:
    res = RAINFALL_LISTING.parse(RF_HTML)
    assert len(res.rows) == 9
    by_id = {r.source_station_id: r for r in res.rows}
    assert " 5402002_" in by_id  # leading whitespace kept as published
    r = by_id["27608"]
    assert r.source_display_station_id == "1910111RF"
    assert r.source_time_raw == "24/09/2026 01:15:00"
    assert r.observation_time_naive == "2026-09-24T01:15:00"  # naive: no timezone applied
    assert r.value_field == "Jumlah 1 Jam(Terkini)"
    assert r.value_raw == "0.0"  # zero rainfall is data
    assert r.source_fields_raw["Taburan Hujan Harian 18/09/2026"] == "38.0"
    assert (r.unit, r.unit_basis, r.measurement_type) == ("mm", "SOURCE_DOCUMENTATION", "rainfall")
    assert r.source_line is not None
    assert r.structural_error is None
    assert by_id["26185"].source_display_station_id == "No Data"


def test_water_level_listing_thresholds_are_source_metadata() -> None:
    res = WATER_LEVEL_LISTING.parse(WL_HTML)
    assert len(res.rows) == 7
    r = {x.source_station_id: x for x in res.rows}["27608"]
    assert (r.value_raw, r.unit, r.unit_basis) == ("15.43", "m", "SOURCE_HEADER")
    assert r.observation_time_naive == "2026-09-24T01:45:00"
    assert r.threshold_values_raw == {
        "Tahap Nilai Ambang Normal": "0.00",
        "Tahap Nilai Ambang Waspada": "21.00",
        "Tahap Nilai Ambang Amaran": "21.20",
        "Tahap Nilai Ambang Bahaya": "21.50",
    }
    assert r.threshold_temporal_scope == CURRENT_AT_RETRIEVAL


@pytest.mark.parametrize("marker", ["-9999", "ERROR", "", "Tiada Data", "0"])
def test_synthetic_listing_value_markers_preserved(marker: str) -> None:
    html = WL_HTML.decode().replace("\n          15.43</a>", f"{marker}</a>", 1)
    r = {x.source_station_id: x for x in WATER_LEVEL_LISTING.parse(html.encode()).rows}["27608"]
    assert r.value_raw == marker
    assert r.structural_error is None  # values are never judged at the raw layer


def test_synthetic_listing_tiada_data_body_fails() -> None:
    html = RF_HTML.decode()
    head = html[: html.index("<td data-th='No'>")]
    body = head + "<td colspan='15'>Tiada Data</td></tr></tbody></table>"
    with pytest.raises(SchemaError, match="Tiada Data"):
        RAINFALL_LISTING.parse(body.encode())


def test_synthetic_listing_schema_change_fails() -> None:
    html = WL_HTML.decode().replace(">Kemaskini Terakhir<", ">Masa Kemaskini<")
    with pytest.raises(SchemaError, match="Kemaskini Terakhir"):
        WATER_LEVEL_LISTING.parse(html.encode())


def test_synthetic_listing_row_structure_and_missing_time_quarantined() -> None:
    html = RF_HTML.decode()
    html = html.replace("<td>24/09/2026 01:15:00</td><td>50.5</td>", "<td></td><td>50.5</td>", 1)
    html = html.replace("<td>Bakar Kapor (F2)</td>", "", 1)  # one cell short
    rows = RAINFALL_LISTING.parse(html.encode()).rows
    reasons = {r.source_station_id: r.structural_error for r in rows}
    assert reasons["27603"] is QuarantineReason.MISSING_TIMESTAMP
    assert reasons["27643"] is QuarantineReason.INVALID_ROW_STRUCTURE
    assert sum(r is None for r in reasons.values()) == 7


def test_malformed_bytes_fail() -> None:
    with pytest.raises(PayloadError, match="UTF-8"):
        RAINFALL_LISTING.parse(b"\xff\xfe<table>")


# ---------------------------------------------------------------- JPS history


def test_rainfall_history_uses_raw_and_keeps_zero() -> None:
    a = history_adapter(SensorType.RAINFALL, "27608", "https://example.invalid/rf?station=27608")
    res = a.parse(RF_HIST)
    assert len(res.rows) == 61
    first = res.rows[0]
    assert (first.value_field, first.value_raw) == ("raw", "0")
    assert first.source_fields_raw["cdaily"] == "4.5"  # number token text kept
    assert first.observation_time_naive == "2026-09-18T00:00:00"
    assert first.threshold_temporal_scope == CURRENT_NOT_HISTORICAL
    assert first.source_display_station_id is None


def test_water_level_history_sentinels_and_error_preserved() -> None:
    res = history_adapter(SensorType.WATER_LEVEL, "27608", WL_URL).parse(WL_HIST)
    assert [r.value_raw for r in res.rows][:3] == ["-9999", "-9999", "19.18"]
    assert res.rows[0].source_fields_raw["severity"] == "ERROR"
    assert res.rows[0].source_fields_raw["raw"] == "23.13"
    assert res.rows[4].source_fields_raw["severity"] == ""  # blank kept, not None
    assert res.rows[0].threshold_values_raw == {
        "normal": "0",
        "alert": "21",
        "warning": "21.2",
        "danger": "21.5",
    }
    assert res.rows[0].threshold_temporal_scope == CURRENT_NOT_HISTORICAL


def test_history_no_result_is_zero_rows() -> None:
    res = history_adapter(SensorType.RAINFALL, "27608", "f").parse(NO_RESULT)
    assert res.rows == ()
    assert res.source_no_result


def test_synthetic_history_schema_change_fails() -> None:
    doc = json.loads(WL_HIST)
    for v in doc["values"]:
        v["final_value"] = v.pop("final")
    with pytest.raises(SchemaError, match="final"):
        history_adapter(SensorType.WATER_LEVEL, "27608", WL_URL).parse(json.dumps(doc).encode())


def test_synthetic_history_row_problems_quarantined() -> None:
    doc = json.loads(WL_HIST)
    doc["values"][1]["dt"] = ""
    doc["values"][2]["dt"] = "2024-09-24 13:55"
    doc["values"][3]["dt"] = None
    del doc["values"][5]["ecm"]
    doc["values"][6]["final"] = None
    rows = history_adapter(SensorType.WATER_LEVEL, "27608", WL_URL).parse(json.dumps(doc).encode())
    got = [r.structural_error for r in rows.rows]
    assert got[1] is QuarantineReason.MISSING_TIMESTAMP
    assert got[2] is QuarantineReason.UNPARSEABLE_TIMESTAMP
    assert got[3] is QuarantineReason.MISSING_TIMESTAMP
    assert got[5] is QuarantineReason.INVALID_ROW_STRUCTURE
    assert got[6] is None
    assert rows.rows[6].value_raw is None  # JSON null kept distinct from ""


def test_history_station_must_match_request() -> None:
    with pytest.raises(PayloadError, match="does not match"):
        history_adapter(SensorType.WATER_LEVEL, "26460", WL_URL).parse(WL_HIST)


def test_malformed_history_json_fails() -> None:
    with pytest.raises(PayloadError, match="not JSON"):
        history_adapter(SensorType.RAINFALL, "27608", "f").parse(b'{"info": {')


def test_history_value_keys_shared_with_probe_script() -> None:
    path = ROOT / "scripts" / "probe_jps_history.py"
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))  # for `import _jps_common`
    spec = importlib.util.spec_from_file_location("probe_jps_history_keys", path)
    assert spec is not None
    assert spec.loader is not None
    probe = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = probe  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(probe)
    assert probe.SENSORS["rainfall"].value_keys == HISTORY_VALUE_KEYS["rainfall"]
    assert probe.SENSORS["water_level"].value_keys == HISTORY_VALUE_KEYS["water_level"]


# ---------------------------------------------------------------- data.gov.my


def test_forecast_records_keep_attribution_fields() -> None:
    a = WeatherForecastAdapter()
    rows = a.parse(FORECAST).rows
    assert len(rows) == 21
    assert a.attribution == ATTRIBUTION
    assert "CC BY 4.0" in ATTRIBUTION
    assert "CC-BY-4.0" in a.licence
    r = rows[0]
    assert (r.source_station_id, r.source_time_raw) == ("Ds001", "2026-09-30")
    assert r.observation_time_naive is None  # a valid date, no time of day
    assert r.source_fields_raw["min_temp"] == "25"
    assert r.structural_error is None


def test_synthetic_forecast_schema_change_fails() -> None:
    doc = [
        {("tarikh" if k == "date" else k): v for k, v in r.items()} for r in json.loads(FORECAST)
    ]
    with pytest.raises(SchemaError, match="date"):
        WeatherForecastAdapter().parse(json.dumps(doc).encode())


# ---------------------------------------------------------------- station mapping


def test_mapping_shared_internal_id_gives_distinct_sensors() -> None:
    m = SensorMapper.from_csv(SYN_SENSORS)  # SYNTHETIC station master (SYN001 is RF + WL)
    rf = m.resolve(SOURCE_JPS, "SYN001", "RAINFALL")
    wl = m.resolve(SOURCE_JPS, "SYN001", "WATER_LEVEL")
    assert rf.fg_sensor_id == "3f881755-e14a-5811-9f45-93b5dbf5ab31"
    assert wl.fg_sensor_id == "4c2f443b-168a-54a1-88f8-83b2930ebff3"
    assert rf.fg_sensor_id != wl.fg_sensor_id


def test_mapping_whitespace_normalised_and_unknown_quarantined() -> None:
    m = SensorMapper.from_csv(SYN_SENSORS)
    assert m.resolve(SOURCE_JPS, "SYN005_", "RAINFALL").fg_sensor_id == sensor_id(
        SOURCE_JPS, "SYN005_", SensorType.RAINFALL
    )
    assert m.resolve(SOURCE_JPS, "  SYN005_ ", "RAINFALL").reason is None
    unknown = m.resolve(SOURCE_JPS, "SYN999", "RAINFALL")
    assert (unknown.fg_sensor_id, unknown.reason) == (None, QuarantineReason.UNMAPPED_SENSOR)
    wrong_type = m.resolve(SOURCE_JPS, "SYN006", "RAINFALL")  # SYN006 is WL only
    assert wrong_type.reason is QuarantineReason.UNMAPPED_SENSOR
    bad = m.resolve(SOURCE_JPS, "SYN 001", "RAINFALL")
    assert bad.reason is QuarantineReason.INVALID_SOURCE_ID
    assert m.resolve(SOURCE_JPS, None, "RAINFALL").reason is QuarantineReason.INVALID_SOURCE_ID


def test_mapping_rejects_inconsistent_or_missing_master(tmp_path: Path) -> None:
    text = SYN_SENSORS.read_text(encoding="utf-8").replace(
        "3f881755-e14a-5811-9f45-93b5dbf5ab31", "00000000-0000-5000-8000-000000000000"
    )
    edited = tmp_path / "sensors.csv"
    edited.write_text(text, encoding="utf-8")
    with pytest.raises(StationMappingError, match="does not match ID rules"):
        SensorMapper.from_csv(edited)
    with pytest.raises(StationMappingError, match="not found"):
        SensorMapper.from_csv(tmp_path / "absent.csv")


# ---------------------------------------------------------------- fetch permission boundary


def test_jps_fetch_refused_without_permission(tmp_path: Path) -> None:
    assert load_permission(tmp_path / "jps.json") is None
    with pytest.raises(PermissionNotGrantedError, match="disabled"):
        PermissionedFetcher(SOURCE_JPS, None).fetch("https://example.invalid/jps")
    with pytest.raises(PermissionNotGrantedError):  # another source's permission does not count
        PermissionedFetcher(SOURCE_JPS, OPEN_DATA_GOV_MY).fetch("https://example.invalid/jps")
    wrong_scope = AccessPermission(SOURCE_JPS, "store_only", "x", "y", "2026-01-01")
    with pytest.raises(PermissionNotGrantedError):
        PermissionedFetcher(SOURCE_JPS, wrong_scope).fetch("https://example.invalid/jps")


def test_permission_record_must_be_explicit(tmp_path: Path) -> None:
    p = tmp_path / "perm.json"
    p.write_text(json.dumps({"source": SOURCE_JPS}), encoding="utf-8")
    with pytest.raises(ValueError, match="permission record"):
        load_permission(p)


def test_network_guard_is_active() -> None:
    with pytest.raises(AssertionError, match="network access"):
        PermissionedFetcher(OPEN_DATA_GOV_MY.source, OPEN_DATA_GOV_MY).fetch(
            "https://example.invalid/"
        )
