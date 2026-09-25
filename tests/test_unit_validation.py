"""Offline tests for the derived unit-validation layer (docs/UNIT_POLICY.md).

Payloads are the trimmed REAL fixtures in tests/fixtures/jps and tests/fixtures/metmalaysia.
Records built by ``record()`` and values such as ``"1,2"``, ``"ft"`` or wrong sensor types are
SYNTHETIC, constructed here to exercise failure states.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from floodguard.ingestion.adapters.data_gov_my import SOURCE as GOV
from floodguard.ingestion.adapters.data_gov_my import WeatherForecastAdapter
from floodguard.ingestion.adapters.jps import (
    RAINFALL_LISTING,
    WATER_LEVEL_LISTING,
    history_adapter,
)
from floodguard.ingestion.contracts import Adapter, BatchStatus
from floodguard.ingestion.pipeline import ingest_batch
from floodguard.ingestion.station_mapping import SensorMapper
from floodguard.preprocessing.units import (
    EXCLUDED_FIELDS,
    UNIT_POLICIES,
    FieldRole,
    MeasurementType,
    SemanticsStatus,
    UnitPolicy,
    UnitProvenance,
    UnitStatus,
    ValueParseStatus,
    check_policy,
    parse_value,
    validate_record,
    validate_unit,
)
from floodguard.station_master import SOURCE_JPS, SensorType

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
JPS_DIR = ROOT / "tests" / "fixtures" / "jps"
FORECAST = ROOT / "tests/fixtures/metmalaysia/weather_forecast_trimmed_20260924T112926+0800.json"
AT = datetime(2026, 9, 24, 8, 0, tzinfo=timezone(timedelta(hours=8)))
RF, WL = SensorType.RAINFALL.value, SensorType.WATER_LEVEL.value
WL_LABEL = "Aras Air (m)(Graf)"
RF_LABEL = "Jumlah 1 Jam(Terkini)"


def v(
    dataset: str,
    field: str,
    value: str | None = "1.5",
    sensor: str | None = RF,
    role: FieldRole = FieldRole.PRIMARY_VALUE,
    unit: str | None = None,
    source: str = SOURCE_JPS,
) -> Any:
    return validate_unit(
        source=source,
        dataset=dataset,
        source_field=field,
        field_role=role,
        value_raw=value,
        sensor_type=sensor,
        raw_record_unit=unit,
    )


def record(**over: Any) -> dict[str, Any]:
    """SYNTHETIC raw_record/v1 subset: a water-level listing row."""
    base: dict[str, Any] = {
        "source": SOURCE_JPS,
        "dataset": "water_level_listing",
        "ingestion_batch_id": "00000000-0000-5000-8000-000000000001",
        "payload_sha256": "0" * 64,
        "source_row_index": 2,
        "source_station_id": " SYN001",
        "sensor_type": WL,
        "source_time_raw": "01/01/2000 00:15",
        "value_field": WL_LABEL,
        "value_raw": "0.00",
        "unit": "m",
        "threshold_values_raw": {
            "Tahap Nilai Ambang Normal": "0.00",
            "Tahap Nilai Ambang Waspada": "2.50",
            "Tahap Nilai Ambang Amaran": "2.80",
            "Tahap Nilai Ambang Bahaya": "3.10",
        },
        "threshold_temporal_scope": "CURRENT_AT_RETRIEVAL",
        "source_fields_raw": {"ID Stesen": "9990011WL", WL_LABEL: "0.00"},
    }
    return {**base, **over}


# ---------------------------------------------------------------- verified units


def test_jps_rainfall_listing_mm_and_zero_stays_zero() -> None:
    r = v("rainfall_listing", RF_LABEL, "0.0", unit="mm")
    assert r.unit_validation_status is UnitStatus.VALID
    assert (r.measurement_type, r.canonical_unit) == (MeasurementType.RAINFALL_1H_TOTAL, "mm")
    assert r.unit_provenance is UnitProvenance.OFFICIAL_UI_OR_DOCS
    assert r.source_unit_raw is None  # the listing header prints no unit
    assert (r.value_parse_status, r.parsed_value, r.value_raw) == (
        ValueParseStatus.NUMERIC,
        0.0,
        "0.0",
    )


def test_jps_water_level_listing_unit_from_payload_label_and_zero() -> None:
    r = v("water_level_listing", WL_LABEL, "0.00", sensor=WL, unit="m")
    assert r.unit_validation_status is UnitStatus.VALID
    assert (r.measurement_type, r.canonical_unit, r.source_unit_raw) == (
        MeasurementType.WATER_LEVEL,
        "m",
        "m",
    )
    assert r.unit_provenance is UnitProvenance.IN_PAYLOAD
    assert r.parsed_value == 0.0
    neg = v("water_level_listing", WL_LABEL, "-0.31", sensor=WL, unit="m")  # observed, kept
    assert neg.parsed_value == -0.31


def test_missing_unit_with_verified_external_provenance_is_valid() -> None:
    r = v("rainfall_history", "raw", "0", unit=None)
    assert r.unit_validation_status is UnitStatus.VALID
    assert r.measurement_type is MeasurementType.RAINFALL_INTERVAL
    assert (r.source_unit_raw, r.raw_record_unit, r.canonical_unit) == (None, None, "mm")
    assert r.parsed_value == 0.0


@pytest.mark.parametrize(
    ("dataset", "field", "category"),
    [
        ("water_level_listing", "Tahap Nilai Ambang Normal", "NORMAL"),
        ("water_level_listing", "Tahap Nilai Ambang Waspada", "WASPADA"),
        ("water_level_listing", "Tahap Nilai Ambang Amaran", "AMARAN"),
        ("water_level_listing", "Tahap Nilai Ambang Bahaya", "BAHAYA"),
        ("water_level_history", "normal", "NORMAL"),
        ("water_level_history", "alert", "WASPADA"),
        ("water_level_history", "warning", "AMARAN"),
        ("water_level_history", "danger", "BAHAYA"),
    ],
)
def test_every_threshold_category(dataset: str, field: str, category: str) -> None:
    r = v(dataset, field, "21.2", sensor=WL, role=FieldRole.THRESHOLD)
    assert r.unit_validation_status is UnitStatus.VALID
    assert r.measurement_type is MeasurementType.WATER_LEVEL_THRESHOLD
    assert (r.canonical_unit, r.threshold_category, r.parsed_value) == ("m", category, 21.2)


# ---------------------------------------------------------------- value status (separate)


@pytest.mark.parametrize(
    ("raw", "status", "number"),
    [
        ("-9999", ValueParseStatus.SOURCE_MARKER, None),
        ("-9999.00", ValueParseStatus.SOURCE_MARKER, None),
        ("ERROR", ValueParseStatus.SOURCE_MARKER, None),
        ("Tiada Data", ValueParseStatus.SOURCE_MARKER, None),
        ("", ValueParseStatus.EMPTY, None),
        ("   ", ValueParseStatus.EMPTY, None),
        (None, ValueParseStatus.EMPTY, None),
        (" 1.5", ValueParseStatus.NUMERIC, 1.5),
        ("0.0", ValueParseStatus.NUMERIC, 0.0),
        ("0", ValueParseStatus.NUMERIC, 0.0),
        ("-0.04", ValueParseStatus.NUMERIC, -0.04),
        ("1,2", ValueParseStatus.NON_NUMERIC, None),
        ("abc", ValueParseStatus.NON_NUMERIC, None),
        ("nan", ValueParseStatus.NON_NUMERIC, None),
        ("inf", ValueParseStatus.NON_NUMERIC, None),
        ("1_0", ValueParseStatus.NON_NUMERIC, None),
    ],
)
def test_parse_value(raw: str | None, status: ValueParseStatus, number: float | None) -> None:
    assert parse_value(raw) == (status, number)


@pytest.mark.parametrize("marker", ["-9999", "ERROR", "", "Tiada Data", "1,2", "abc"])
def test_markers_keep_a_valid_unit_but_no_number(marker: str) -> None:
    r = v("water_level_history", "final", marker, sensor=WL)
    assert r.unit_validation_status is UnitStatus.VALID  # the unit is not the problem
    assert r.value_parse_status is not ValueParseStatus.NUMERIC
    assert (r.parsed_value, r.value_raw) == (None, marker)  # never imputed, text unchanged


# ---------------------------------------------------------------- failures


def test_unknown_unit_and_mismatched_unit() -> None:
    ft = v("water_level_listing", "Aras Air (ft)(Graf)", sensor=WL, unit="m")
    assert (ft.unit_validation_status, ft.source_unit_raw) == (UnitStatus.UNKNOWN_UNIT, "ft")
    mm_label = v("water_level_listing", "Aras Air (mm)(Graf)", sensor=WL, unit="m")
    assert mm_label.unit_validation_status is UnitStatus.UNIT_MISMATCH
    wl_on_rain = v("rainfall_listing", RF_LABEL, unit="m")  # WL unit on a rainfall value
    assert wl_on_rain.unit_validation_status is UnitStatus.UNIT_MISMATCH
    record_unit = v("water_level_history", "final", sensor=WL, unit="cm")
    assert record_unit.unit_validation_status is UnitStatus.UNKNOWN_UNIT
    for r in (ft, mm_label, wl_on_rain, record_unit):
        assert r.parsed_value is None
        assert r.reason


def test_missing_unit_in_payload_label() -> None:
    r = v("water_level_listing", "Aras Air ()(Graf)", sensor=WL, unit="m")
    assert r.unit_validation_status is UnitStatus.MISSING_UNIT
    assert r.parsed_value is None


def test_sensor_type_mismatch() -> None:
    rain_on_wl = v("rainfall_history", "raw", "2", sensor=WL)
    threshold_on_rain = v(
        "water_level_listing", "Tahap Nilai Ambang Bahaya", "6.00", role=FieldRole.THRESHOLD
    )
    level_without_sensor = v("water_level_history", "final", "1.0", sensor=None)
    temp_on_sensor = v("weather_forecast", "min_temp", "25", sensor=RF, source=GOV)
    for r in (rain_on_wl, threshold_on_rain, level_without_sensor, temp_on_sensor):
        assert r.unit_validation_status is UnitStatus.SENSOR_TYPE_MISMATCH
        assert r.parsed_value is None
    assert threshold_on_rain.threshold_category == "BAHAYA"  # category kept apart from unit


def test_unknown_semantics_field() -> None:
    r = v("water_level_history", "severity", "SL_NML", sensor=WL, role=FieldRole.SOURCE_FIELD)
    assert r.unit_validation_status is UnitStatus.UNKNOWN_MEASUREMENT_SEMANTICS
    assert (r.measurement_type, r.canonical_unit, r.parsed_value) == (None, None, None)
    assert r.semantics_status is SemanticsStatus.UNVERIFIED
    other = v("rainfall_listing", "Jumlah 3 Jam", "1.0")  # synthetic unregistered header
    assert other.unit_validation_status is UnitStatus.UNKNOWN_MEASUREMENT_SEMANTICS


@pytest.mark.parametrize(
    ("dataset", "field", "sensor"),
    [
        ("rainfall_history", "clean", RF),
        ("rainfall_history", "chourly", RF),
        ("rainfall_history", "c15min", RF),
        ("rainfall_history", "tdaily", RF),
        ("rainfall_history", "cdaily", RF),
        ("rainfall_history", "cyearly", RF),
        ("rainfall_history", "heavy", RF),
        ("rainfall_listing", "Taburan Hujan Harian 18/09/2026", RF),
        ("rainfall_listing", "Taburan Hujan dari Tengah Malam (24/09/2026)", RF),
        ("water_level_history", "raw", WL),
        ("water_level_history", "ecm", WL),
        ("water_level_history", "clean", WL),
    ],
)
def test_unverified_fields_are_not_promoted(dataset: str, field: str, sensor: str) -> None:
    r = v(dataset, field, "3.5", sensor=sensor, role=FieldRole.SOURCE_FIELD)
    assert r.unit_validation_status is UnitStatus.UNKNOWN_MEASUREMENT_SEMANTICS
    assert r.reason is not None
    assert r.reason.startswith("excluded:")
    assert (r.measurement_type, r.canonical_unit, r.parsed_value) == (None, None, None)
    assert r.value_parse_status is ValueParseStatus.NUMERIC  # still classified, not exposed


def test_data_gov_my_temperature_is_documented_celsius() -> None:
    # ACCESS.md section 1A marks the unit [doc] (official API docs), not [inferred].
    for key, mt in (
        ("min_temp", MeasurementType.FORECAST_TEMPERATURE_MIN),
        ("max_temp", MeasurementType.FORECAST_TEMPERATURE_MAX),
    ):
        r = v("weather_forecast", key, "25", sensor=None, role=FieldRole.SOURCE_FIELD, source=GOV)
        assert (r.unit_validation_status, r.measurement_type, r.canonical_unit) == (
            UnitStatus.VALID,
            mt,
            "°C",
        )
        assert r.unit_provenance is UnitProvenance.OFFICIAL_UI_OR_DOCS
    summary = v("weather_forecast", "summary_forecast", "Tiada Hujan", sensor=None, source=GOV)
    assert summary.unit_validation_status is UnitStatus.UNKNOWN_MEASUREMENT_SEMANTICS


def test_policy_rejects_inferred_or_unverified_canonical_entries() -> None:
    base = UnitPolicy(
        GOV,
        "synthetic",
        "temperature",
        MeasurementType.FORECAST_TEMPERATURE_MIN,
        "°C",
        UnitProvenance.INFERRED,
        None,
        "synthetic",
    )
    with pytest.raises(ValueError, match="inferred"):
        check_policy([base], [])
    unverified = replace(
        base,
        unit_provenance=UnitProvenance.OFFICIAL_UI_OR_DOCS,
        semantics_status=SemanticsStatus.UNVERIFIED,
    )
    with pytest.raises(ValueError, match="unverified"):
        check_policy([unverified], [])
    with pytest.raises(ValueError, match="twice"):
        check_policy(UNIT_POLICIES, [*EXCLUDED_FIELDS, EXCLUDED_FIELDS[0]])
    # The shipped registry: every canonical entry verified, never INFERRED.
    assert all(p.semantics_status is SemanticsStatus.VERIFIED for p in UNIT_POLICIES)
    assert all(p.unit_provenance is not UnitProvenance.INFERRED for p in UNIT_POLICIES)
    assert all(p.evidence for p in UNIT_POLICIES)
    assert all(e.evidence and e.reason for e in EXCLUDED_FIELDS)


# ---------------------------------------------------------------- record rows


def test_validate_record_rows_and_threshold_scope() -> None:
    rec = record()
    before = json.dumps(rec, sort_keys=True)
    rows = validate_record(rec)
    assert json.dumps(rec, sort_keys=True) == before  # the raw record is not modified
    assert [r["source_field"] for r in rows] == [WL_LABEL, *rec["threshold_values_raw"]]
    assert [r["field_role"] for r in rows] == ["PRIMARY_VALUE", *["THRESHOLD"] * 4]
    assert all(r["unit_validation_status"] == "VALID" for r in rows)
    assert rows[0]["threshold_temporal_scope"] is None
    assert {r["threshold_temporal_scope"] for r in rows[1:]} == {"CURRENT_AT_RETRIEVAL"}
    assert [r["threshold_category"] for r in rows[1:]] == ["NORMAL", "WASPADA", "AMARAN", "BAHAYA"]
    for r in rows:  # regression: identifiers and text exactly as in the raw record
        assert r["source_station_id"] == " SYN001"
        assert r["source_time_raw"] == "01/01/2000 00:15"
        assert (r["ingestion_batch_id"], r["source_row_index"]) == (
            rec["ingestion_batch_id"],
            2,
        )
    thresholds_on_rain = validate_record(record(sensor_type=RF))
    assert {r["unit_validation_status"] for r in thresholds_on_rain} == {"SENSOR_TYPE_MISMATCH"}


def test_validate_record_is_deterministic() -> None:
    a = json.dumps(validate_record(record()), sort_keys=True).encode()
    b = json.dumps(validate_record(record()), sort_keys=True).encode()
    assert a == b


# ---------------------------------------------------------------- script (end to end)


def _script() -> ModuleType:
    path = ROOT / "scripts" / "validate_units.py"
    spec = importlib.util.spec_from_file_location("validate_units", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _run(raw: Path, records: Path, out: Path) -> int:
    code: int = _script().main(
        ["--records", str(records), "--raw-root", str(raw), "--out-root", str(out)]
    )
    return code


def _hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _ingest(raw: Path, payload: bytes, adapter: Adapter, mapper: SensorMapper | None) -> list[str]:
    ref = getattr(adapter, "source_reference", "https://example.invalid/listing")
    rep = ingest_batch(
        payload, adapter, source_reference=ref, retrieved_at=AT, raw_root=raw, mapper=mapper
    )
    assert rep.status is BatchStatus.SUCCEEDED
    return rep.artifact_paths  # payload, records, quarantine


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


RF_IDS = ["27603", "27608", "27616", "27643", "27666", "BUMBUNGLIMA", "26186", "5402002_"]
WL_IDS = ["27587", "27608", "27620", "BUMBUNGLIMA", "5302004_", "26189", "26460"]


def test_script_end_to_end(
    tmp_path: Path,
    make_sensors_csv: Any,
    capsys: pytest.CaptureFixture[str],
) -> None:
    master = [(i, SensorType.RAINFALL) for i in RF_IDS] + [
        (i, SensorType.WATER_LEVEL) for i in WL_IDS
    ]
    mapper = SensorMapper.from_csv(make_sensors_csv(master))
    raw = tmp_path / "raw"
    batches = [
        _ingest(raw, (JPS_DIR / f).read_bytes(), a, m)
        for f, a, m in (
            ("searchresultrainfall_PNG_trimmed.html", RAINFALL_LISTING, mapper),
            ("aras_air_data_PNG_trimmed.html", WATER_LEVEL_LISTING, mapper),
            (
                "history_rainfall_27608_20260918_trimmed.json",
                history_adapter(SensorType.RAINFALL, "27608", "https://example.invalid/rf"),
                mapper,
            ),
            (
                "history_water_level_27608_20240924_trimmed.json",
                history_adapter(SensorType.WATER_LEVEL, "27608", "https://example.invalid/wl"),
                mapper,
            ),
        )
    ]
    batches.append(_ingest(raw, FORECAST.read_bytes(), WeatherForecastAdapter(), None))
    before = _hashes(raw)
    inputs = [b[1] for b in batches] + [batches[0][2]]  # every records file + one quarantine

    out_a, out_b = tmp_path / "a", tmp_path / "b"
    reports = []
    for rel in inputs:
        assert _run(raw, raw / rel, out_a) == 0
        reports.append(json.loads(capsys.readouterr().out))
    assert _hashes(raw) == before  # raw payloads, records, quarantine, manifest untouched
    for rel in inputs:  # rerun is a no-op; a fresh root gives byte-identical output
        assert _run(raw, raw / rel, out_a) == 0
        assert json.loads(capsys.readouterr().out)["written"] is False
        assert _run(raw, raw / rel, out_b) == 0
        capsys.readouterr()
    assert _hashes(out_a) == _hashes(out_b)
    assert len(_hashes(out_a)) == len(inputs)
    assert _hashes(raw) == before

    rf_list, wl_list, rf_hist, wl_hist, fc, rf_q = (
        _rows(out_a / r["output_path"]) for r in reports
    )
    # Raw value text, station IDs and time text are carried exactly.
    raw_rf = _rows(raw / batches[0][1])
    prim = [r for r in rf_list if r["field_role"] == "PRIMARY_VALUE"]
    assert [(r["value_raw"], r["source_station_id"], r["source_time_raw"]) for r in prim] == [
        (x["value_raw"], x["source_station_id"], x["source_time_raw"]) for x in raw_rf
    ]
    assert {r["unit_validation_status"] for r in prim} == {"VALID"}
    assert {r["parsed_value"] for r in prim} == {0.0}  # zero rainfall stays 0
    daily = [r for r in rf_list if r["source_field"].startswith("Taburan Hujan")]
    assert len(daily) == 7 * len(raw_rf)
    assert {r["unit_validation_status"] for r in daily} == {"UNKNOWN_MEASUREMENT_SEMANTICS"}
    assert {r["parsed_value"] for r in daily} == {None}

    assert {r["measurement_type"] for r in wl_list if r["unit_validation_status"] == "VALID"} == {
        "WATER_LEVEL",
        "WATER_LEVEL_THRESHOLD",
    }

    promoted = {r["source_field"] for r in rf_hist if r["unit_validation_status"] == "VALID"}
    assert promoted == {"raw"}  # interval field only; clean/chourly/c15min/tdaily excluded
    assert {r["source_field"] for r in rf_hist} >= {"clean", "chourly", "c15min", "tdaily"}
    rf_thr = [r for r in rf_hist if r["field_role"] == "THRESHOLD"]
    assert {r["unit_validation_status"] for r in rf_thr} == {"UNKNOWN_MEASUREMENT_SEMANTICS"}

    thr = [r for r in wl_hist if r["field_role"] == "THRESHOLD"]
    assert {r["threshold_temporal_scope"] for r in thr} == {"CURRENT_NOT_HISTORICAL"}
    assert {r["unit_validation_status"] for r in thr} == {"VALID"}
    final = [r for r in wl_hist if r["source_field"] == "final"]
    assert {r["value_parse_status"] for r in final} == {"SOURCE_MARKER", "NUMERIC"}
    assert all(
        (r["parsed_value"] is None) == (r["value_parse_status"] == "SOURCE_MARKER") for r in final
    )

    temps = [r for r in fc if r["unit_validation_status"] == "VALID"]
    assert {r["canonical_unit"] for r in temps} == {"°C"}
    assert len(temps) == 2 * len(_rows(raw / batches[4][1]))

    assert [r["source_station_id"] for r in rf_q if r["field_role"] == "PRIMARY_VALUE"] == ["26185"]


def test_script_rejects_unusable_inputs(
    tmp_path: Path, make_sensors_csv: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    fc = _ingest(raw, FORECAST.read_bytes(), WeatherForecastAdapter(), None)
    before = _hashes(raw)
    out = tmp_path / "o"
    assert _run(raw, raw / fc[1], raw / "derived") == 2  # output inside the raw root
    assert _run(raw, raw / fc[0], out) == 2  # payload, not a records file
    stray = raw / "data_gov_my" / "x.records.jsonl"  # synthetic: not in the manifest
    stray.write_bytes((raw / fc[1]).read_bytes())
    assert _run(raw, stray, out) == 2
    stray.unlink()
    assert "REJECTED" in capsys.readouterr().err
    assert not out.exists()
    assert _hashes(raw) == before
