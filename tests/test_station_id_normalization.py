"""Offline tests for the derived station-ID layer (``floodguard.preprocessing.station_ids``).

Station masters are SYNTHETIC only: the golden
``tests/fixtures/station_master/expected/sensors.csv`` (``SYN…`` keys, cases in that directory's
README) or files built per test under ``tmp_path``.
Payloads for the end-to-end runs are the trimmed REAL JPS fixtures in ``tests/fixtures/jps``,
ingested into ``tmp_path``. data/local, data/raw and data/interim are never read; network is
blocked.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from floodguard.ingestion.adapters.data_gov_my import WeatherForecastAdapter
from floodguard.ingestion.adapters.jps import RAINFALL_LISTING, WATER_LEVEL_LISTING
from floodguard.ingestion.contracts import Adapter, BatchStatus
from floodguard.ingestion.pipeline import ingest_batch
from floodguard.ingestion.station_mapping import (
    IdMappingStatus,
    SensorMapper,
    StationMappingError,
)
from floodguard.preprocessing.station_ids import (
    SCHEMA_VERSION,
    normalize_record,
    raw_mapping_conflict,
    resolve_station_ids,
)
from floodguard.station_master import SOURCE_JPS, SensorType, review_site_id, sensor_id, site_id

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
SYN_SENSORS = ROOT / "tests" / "fixtures" / "station_master" / "expected" / "sensors.csv"
JPS = ROOT / "tests" / "fixtures" / "jps"
RF_HTML = (JPS / "searchresultrainfall_PNG_trimmed.html").read_bytes()
WL_HTML = (JPS / "aras_air_data_PNG_trimmed.html").read_bytes()
FORECAST = ROOT / "tests/fixtures/metmalaysia/weather_forecast_trimmed_20260924T112926+0800.json"
AT = datetime(2026, 9, 24, 8, 0, tzinfo=timezone(timedelta(hours=8)))
RF, WL = SensorType.RAINFALL.value, SensorType.WATER_LEVEL.value
Make = Callable[[Iterable[tuple[str, SensorType]]], Path]

# Pinned golden IDs from the synthetic station master (station_master UUIDv5 recipe).
SYN001_SITE = "e92e57cd-306b-5067-a757-b78cee051191"
SYN001_RF = "3f881755-e14a-5811-9f45-93b5dbf5ab31"
SYN001_WL = "4c2f443b-168a-54a1-88f8-83b2930ebff3"
SYN005_SITE = "24e48d55-20ac-5430-a35f-fe6380ac0f01"
SYN005_RF = "d2095531-020d-52c6-8702-3a52105837a3"


@pytest.fixture(scope="module")
def syn() -> SensorMapper:
    return SensorMapper.from_csv(SYN_SENSORS)


def res(
    m: SensorMapper, internal: str | None, st: str | None = RF, display: str | None = "X"
) -> Any:
    return resolve_station_ids(SOURCE_JPS, internal, display, st, m)


def record(**over: Any) -> dict[str, Any]:
    """SYNTHETIC raw_record/v1 subset (listing row for SYN001 rainfall)."""
    base: dict[str, Any] = {
        "source": SOURCE_JPS,
        "dataset": "rainfall_listing",
        "ingestion_batch_id": "00000000-0000-5000-8000-000000000001",
        "payload_sha256": "0" * 64,
        "source_row_index": 3,
        "measurement_type": "rainfall",
        "source_station_id": "SYN001",
        "source_display_station_id": "9990011RF",
        "source_station_name": "Synthetic Alpha (F2)",
        "sensor_type": RF,
        "source_time_raw": "01/01/2000 00:15:00",
        "value_raw": "0.5",
        "fg_sensor_id": SYN001_RF,
        "mapping_status": "MAPPED",
    }
    return {**base, **over}


# ---------------------------------------------------------------- mapping rules


def test_shared_site_same_site_different_sensors(syn: SensorMapper) -> None:
    rf, wl = res(syn, "SYN001", RF), res(syn, "SYN001", WL)
    assert (rf.fg_site_id, rf.fg_sensor_id) == (SYN001_SITE, SYN001_RF)
    assert (wl.fg_site_id, wl.fg_sensor_id) == (SYN001_SITE, SYN001_WL)
    assert rf.station_id_mapping_status is wl.station_id_mapping_status is IdMappingStatus.MAPPED
    assert rf.mapping_reason is wl.mapping_reason is None


def test_review_sites_come_from_master_not_rederived(syn: SensorMapper) -> None:
    rf, wl = res(syn, "SYN007", RF), res(syn, "SYN007", WL)  # WL failed the merge checks
    assert rf.fg_site_id == site_id(SOURCE_JPS, "SYN007")
    assert wl.fg_site_id == review_site_id(SOURCE_JPS, "SYN007", SensorType.WATER_LEVEL)
    assert rf.fg_site_id != wl.fg_site_id


def test_rainfall_only_and_water_level_only_sites(syn: SensorMapper) -> None:
    rf_only, wl_only = res(syn, "SYN008", RF), res(syn, "SYN006", WL)
    assert rf_only.fg_sensor_id == sensor_id(SOURCE_JPS, "SYN008", SensorType.RAINFALL)
    assert wl_only.fg_sensor_id == sensor_id(SOURCE_JPS, "SYN006", SensorType.WATER_LEVEL)
    for other in (res(syn, "SYN008", WL), res(syn, "SYN006", RF)):  # wrong sensor type
        assert other.station_id_mapping_status is IdMappingStatus.SENSOR_TYPE_MISMATCH
        assert (other.fg_site_id, other.fg_sensor_id) == (None, None)
        assert other.mapping_reason is not None
        assert "sensor for" in other.mapping_reason


def test_duplicate_blank_and_no_data_display_ids_are_ignored(syn: SensorMapper) -> None:
    a, b = res(syn, "SYN002", display="9990021RF"), res(syn, "SYN003", display="9990021RF")
    assert a.fg_sensor_id != b.fg_sensor_id  # same display ID, different sensors
    assert a.jps_display_station_id_raw == b.jps_display_station_id_raw == "9990021RF"
    no_data, blank = res(syn, "SYN004", display="No Data"), res(syn, "SYN005_", display="")
    assert no_data.station_id_mapping_status is blank.station_id_mapping_status
    assert no_data.station_id_mapping_status is IdMappingStatus.MAPPED
    assert (no_data.jps_display_station_id_raw, blank.jps_display_station_id_raw) == ("No Data", "")
    # A display ID that equals another sensor's display ID never redirects the lookup.
    assert res(syn, "SYN001", display="9990021RF").fg_sensor_id == SYN001_RF


def test_outer_whitespace_internal_id(syn: SensorMapper) -> None:
    for raw in (" SYN005_", "SYN005_", "\tSYN005_  "):
        r = res(syn, raw, display="")
        assert r.jps_internal_id_raw == raw  # preserved exactly
        assert r.lookup_key == "SYN005_"
        assert (r.fg_site_id, r.fg_sensor_id) == (SYN005_SITE, SYN005_RF)  # as in the master


def test_unknown_internal_id_unmapped(syn: SensorMapper) -> None:
    r = res(syn, "SYN999")
    assert r.station_id_mapping_status is IdMappingStatus.UNMAPPED
    assert (r.lookup_key, r.fg_site_id, r.fg_sensor_id) == ("SYN999", None, None)
    assert "SYN999" in (r.mapping_reason or "")
    assert res(syn, "syn001").station_id_mapping_status is IdMappingStatus.UNMAPPED  # case kept


@pytest.mark.parametrize("raw", [None, "", "   ", "\t", "SYN 001"])
def test_invalid_source_id(syn: SensorMapper, raw: str | None) -> None:
    r = res(syn, raw)
    assert r.station_id_mapping_status is IdMappingStatus.INVALID_SOURCE_ID
    assert (r.jps_internal_id_raw, r.lookup_key, r.fg_sensor_id) == (raw, None, None)


@pytest.mark.parametrize("st", [None, "", "TEMPERATURE", "rainfall"])
def test_missing_or_unknown_sensor_type(syn: SensorMapper, st: str | None) -> None:
    r = res(syn, "SYN001", st)
    assert r.station_id_mapping_status is IdMappingStatus.INVALID_SENSOR_TYPE
    assert (r.sensor_type, r.lookup_key, r.fg_site_id, r.fg_sensor_id) == (st, "SYN001", None, None)


def test_mapping_is_deterministic_and_ids_follow_the_recipe(syn: SensorMapper) -> None:
    again = SensorMapper.from_csv(SYN_SENSORS)
    rows = list(csv.DictReader(SYN_SENSORS.read_text(encoding="utf-8").splitlines()))
    for row in rows:
        a = res(syn, row["jps_internal_id"], row["sensor_type"])
        assert a == res(again, row["jps_internal_id"], row["sensor_type"])
        key = row["jps_internal_id"].strip()
        assert a.fg_sensor_id == row["fg_sensor_id"]
        assert a.fg_sensor_id == sensor_id(SOURCE_JPS, key, SensorType(row["sensor_type"]))
        assert a.fg_site_id == row["fg_site_id"]
    assert len(rows) == 14


def test_ids_do_not_depend_on_name_value_time_or_display(syn: SensorMapper) -> None:
    base = normalize_record(record(), syn)
    changed = normalize_record(
        record(
            source_station_name="Renamed Station",
            value_raw="-9999",
            source_time_raw="31/12/2099 23:59:59",
            source_display_station_id="No Data",
        ),
        syn,
    )
    assert (changed["fg_site_id"], changed["fg_sensor_id"]) == (SYN001_SITE, SYN001_RF)
    assert (base["fg_site_id"], base["fg_sensor_id"]) == (SYN001_SITE, SYN001_RF)
    assert changed["jps_display_station_id_raw"] == "No Data"


def test_normalize_record_contract(syn: SensorMapper) -> None:
    rec = record(source_station_id=" SYN001 ")
    row = normalize_record(rec, syn)
    assert rec["source_station_id"] == " SYN001 "  # input not modified
    assert row["station_id_schema_version"] == SCHEMA_VERSION
    assert row["jps_internal_id_raw"] == " SYN001 "
    assert row["lookup_key"] == "SYN001"
    assert row["station_id_mapping_status"] == "MAPPED"
    assert row["station_master_origin"].startswith("sensors.csv@sha256:")
    assert (row["raw_fg_sensor_id"], row["fg_sensor_id"]) == (SYN001_RF, SYN001_RF)
    assert set(row) >= {"ingestion_batch_id", "payload_sha256", "source_row_index", "dataset"}
    assert not {"observation_time_utc", "timestamp_quality_flag", "value"} & set(row)


def test_raw_mapping_conflict_rule() -> None:
    assert not raw_mapping_conflict({"raw_fg_sensor_id": "a", "fg_sensor_id": "a"})
    assert not raw_mapping_conflict({"raw_fg_sensor_id": None, "fg_sensor_id": "a"})
    assert not raw_mapping_conflict({"raw_fg_sensor_id": "a", "fg_sensor_id": None})
    assert raw_mapping_conflict({"raw_fg_sensor_id": "a", "fg_sensor_id": "b"})


def test_consistent_with_raw_ingestion_resolver(syn: SensorMapper) -> None:
    for internal in ("SYN001", " SYN005_", "SYN006", "SYN008", "SYN999", "", None, "SYN 1"):
        for st in (RF, WL):
            derived = res(syn, internal, st)
            raw = syn.resolve(SOURCE_JPS, internal, st)
            assert raw.fg_sensor_id == derived.fg_sensor_id
            assert (raw.reason is None) == (derived.station_id_mapping_status == "MAPPED")


# ---------------------------------------------------------------- inconsistent masters


def _edited_master(tmp_path: Path, edit: Callable[[list[list[str]]], list[list[str]]]) -> Path:
    rows = list(csv.reader(SYN_SENSORS.read_text(encoding="utf-8").splitlines()))
    path = tmp_path / "sensors.csv"
    with path.open("w", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(edit(rows))
    return path


def _swap_sensor_ids(rows: list[list[str]]) -> list[list[str]]:
    rows[1][0], rows[2][0] = rows[2][0], rows[1][0]  # SYN001 RF row carries the WL sensor ID
    return rows


def _duplicate_row(rows: list[list[str]]) -> list[list[str]]:
    return [*rows, rows[1]]  # same (source, key, type) and same fg_sensor_id twice


def _foreign_site(rows: list[list[str]]) -> list[list[str]]:
    rows[3][1] = rows[1][1]  # SYN002 RF attached to SYN001's site: 2 RF sensors on one site
    return rows


def _whitespace_variant_duplicate(rows: list[list[str]]) -> list[list[str]]:
    dup = list(rows[1])
    dup[4] = " SYN001 "  # normalises to an existing key
    return [*rows, dup]


def _drop_site_column(rows: list[list[str]]) -> list[list[str]]:
    return [r[:1] + r[2:] for r in rows]


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (_swap_sensor_ids, "fg_sensor_id does not match"),
        (_duplicate_row, "duplicate sensor"),
        (_foreign_site, "fg_site_id does not match"),
        (_whitespace_variant_duplicate, "duplicate sensor"),
        (_drop_site_column, "missing columns"),
    ],
)
def test_inconsistent_master_is_a_hard_error(
    tmp_path: Path, edit: Callable[[list[list[str]]], list[list[str]]], message: str
) -> None:
    with pytest.raises(StationMappingError, match=message):
        SensorMapper.from_csv(_edited_master(tmp_path, edit))


# ---------------------------------------------------------------- batch script (end to end)


def _script() -> ModuleType:
    path = ROOT / "scripts" / "normalize_station_ids.py"
    spec = importlib.util.spec_from_file_location("normalize_station_ids", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _ingest(raw: Path, payload: bytes, adapter: Adapter, mapper: SensorMapper | None) -> list[str]:
    rep = ingest_batch(
        payload,
        adapter,
        source_reference="https://example.invalid/listing",
        retrieved_at=AT,
        raw_root=raw,
        mapper=mapper,
    )
    assert rep.status is BatchStatus.SUCCEEDED
    return rep.artifact_paths  # payload, records, quarantine


# 26185 (RF) deliberately absent; 27608 and BUMBUNGLIMA are RF + WL; " 5402002_" has a space.
RF_IDS = ["27603", "27608", "27616", "27643", "27666", "BUMBUNGLIMA", "26186", "5402002_"]
WL_IDS = ["27587", "27608", "27620", "BUMBUNGLIMA", "5302004_", "26189", "26460"]
MASTER = [(i, SensorType.RAINFALL) for i in RF_IDS] + [(i, SensorType.WATER_LEVEL) for i in WL_IDS]


def _run(raw: Path, records: str, out: Path, master: Path) -> int:
    args = ["--records", str(raw / records), "--raw-root", str(raw), "--out-root", str(out)]
    code: int = _script().main([*args, "--station-master", str(master)])
    return code


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_script_end_to_end_listings(
    tmp_path: Path, make_sensors_csv: Make, capsys: pytest.CaptureFixture[str]
) -> None:
    master = make_sensors_csv(MASTER)
    mapper = SensorMapper.from_csv(master)
    raw = tmp_path / "raw"
    rf = _ingest(raw, RF_HTML, RAINFALL_LISTING, mapper)
    wl = _ingest(raw, WL_HTML, WATER_LEVEL_LISTING, mapper)
    before = _hashes(raw)
    assert len(before) == 7  # 2 x (payload, records, quarantine) + manifest

    out_a, out_b = tmp_path / "a", tmp_path / "b"
    reports = []
    for records in (rf[1], wl[1], rf[2]):
        assert _run(raw, records, out_a, master) == 0
        reports.append(json.loads(capsys.readouterr().out))
    assert _hashes(raw) == before  # raw payloads, records, quarantine, manifest untouched

    first = _hashes(out_a)
    for records in (rf[1], wl[1], rf[2]):  # rerun: write-once no-op, identical bytes
        assert _run(raw, records, out_a, master) == 0
        assert json.loads(capsys.readouterr().out)["written"] is False
        assert _run(raw, records, out_b, master) == 0  # fresh root: byte-identical output
        assert json.loads(capsys.readouterr().out)["written"] is True
    assert len(first) == 3
    assert _hashes(out_a) == _hashes(out_b) == first
    assert _hashes(raw) == before

    rf_rows = _rows(out_a / reports[0]["output_path"])
    wl_rows = _rows(out_a / reports[1]["output_path"])
    q_rows = _rows(out_a / reports[2]["output_path"])
    rf_recs, wl_recs = _rows(raw / rf[1]), _rows(raw / wl[1])
    assert len(rf_rows) == len(rf_recs) == 8
    assert len(wl_rows) == len(wl_recs) == 7
    for rec, row in zip([*rf_recs, *wl_recs], [*rf_rows, *wl_rows], strict=True):
        assert row["jps_internal_id_raw"] == rec["source_station_id"]  # exact, incl. whitespace
        assert row["jps_display_station_id_raw"] == rec["source_display_station_id"]
        assert row["source_row_index"] == rec["source_row_index"]
        assert row["station_id_mapping_status"] == "MAPPED"
        assert row["fg_sensor_id"] == row["raw_fg_sensor_id"] == rec["fg_sensor_id"]
        assert row["fg_site_id"] is not None
    assert reports[0]["raw_mapping_changed"] == reports[1]["raw_mapping_changed"] == 0

    padded = next(r for r in rf_rows if r["lookup_key"] == "5402002_")
    assert padded["jps_internal_id_raw"] == " 5402002_"
    assert padded["fg_sensor_id"] == sensor_id(SOURCE_JPS, "5402002_", SensorType.RAINFALL)

    shared = {r["fg_site_id"] for r in [*rf_rows, *wl_rows] if r["lookup_key"] == "27608"}
    assert shared == {site_id(SOURCE_JPS, "27608")}  # one site, two sensors
    sensors = {r["fg_sensor_id"] for r in [*rf_rows, *wl_rows] if r["lookup_key"] == "27608"}
    assert len(sensors) == 2

    # Quarantined at ingest (26185 not in the master): kept, still unmapped, no ID invented.
    assert [r["station_id_mapping_status"] for r in q_rows] == ["UNMAPPED"]
    assert (q_rows[0]["jps_internal_id_raw"], q_rows[0]["fg_sensor_id"]) == ("26185", None)


def test_script_re_resolves_with_a_newer_master(
    tmp_path: Path, make_sensors_csv: Make, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    paths = _ingest(raw, RF_HTML, RAINFALL_LISTING, SensorMapper.from_csv(make_sensors_csv(MASTER)))
    newer = make_sensors_csv([*MASTER, ("26185", SensorType.RAINFALL)])  # sensor added later
    assert _run(raw, paths[2], tmp_path / "out", newer) == 0
    report = json.loads(capsys.readouterr().out)
    (row,) = _rows(tmp_path / "out" / report["output_path"])
    assert row["raw_mapping_status"] == "UNMAPPED"
    assert row["raw_fg_sensor_id"] is None
    assert row["fg_sensor_id"] == sensor_id(SOURCE_JPS, "26185", SensorType.RAINFALL)
    assert report["raw_mapping_changed"] == 1


def test_script_rejects_unusable_inputs(
    tmp_path: Path, make_sensors_csv: Make, capsys: pytest.CaptureFixture[str]
) -> None:
    master = make_sensors_csv(MASTER)
    raw = tmp_path / "raw"
    rf = _ingest(
        raw,
        RF_HTML,
        RAINFALL_LISTING,
        SensorMapper.from_csv(master),
    )
    fc = _ingest(raw, FORECAST.read_bytes(), WeatherForecastAdapter(), None)
    before = _hashes(raw)
    out = tmp_path / "o"
    assert _run(raw, fc[1], out, master) == 2  # data.gov.my: no station master
    assert _run(raw, rf[1], out, tmp_path / "absent.csv") == 2  # master missing
    assert _run(raw, rf[1], raw / "derived", master) == 2  # output inside the raw root
    assert _run(raw, rf[0], out, master) == 2  # payload, not a records file
    stray = raw / "jps" / "x.records.jsonl"  # synthetic: inside raw root, not in the manifest
    stray.write_bytes((raw / rf[1]).read_bytes())
    assert _run(raw, "jps/x.records.jsonl", out, master) == 2
    stray.unlink()
    assert "REJECTED" in capsys.readouterr().err
    assert not out.exists()
    assert _hashes(raw) == before
    # A different master changes station_master_origin: the existing output is not overwritten.
    assert _run(raw, rf[1], out, master) == 0
    other = make_sensors_csv([*MASTER, ("26185", SensorType.RAINFALL)])
    written = _hashes(out)
    assert _run(raw, rf[1], out, other) == 2
    assert _hashes(out) == written
