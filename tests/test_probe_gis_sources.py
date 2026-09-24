"""Offline tests for scripts/probe_gis_sources.py (no network).

Fixtures are REAL captures (see tests/fixtures/gis/README.md). Tests named ``test_synthetic_*``
mutate them to create cases not present in the captures.
"""

import copy
import csv
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "gis"


def _load() -> ModuleType:
    path = ROOT / "scripts" / "probe_gis_sources.py"
    spec = importlib.util.spec_from_file_location("probe_gis_sources", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text("utf-8"))


p = _load()
FEED: list[dict[str, str]] = _fixture(
    "jps_latestreadingstrendabc_penang_plus2_trimmed_20260924T041054Z.json"
)
LAYERS: dict[str, Any] = _fixture("pegis_sejarah_banjir_layers_trimmed_20260924T043139Z.json")
COUNTS: dict[str, Any] = _fixture("pegis_sejarah_banjir_counts_20260924T042413Z.json")
L26: dict[str, Any] = _fixture(
    "pegis_sejarah_banjir_layer26_groupby_tarikh_masa_20260924T042428Z.json"
)
L7: dict[str, Any] = _fixture("pegis_sejarah_banjir_layer7_groupby_tarikh_20260924T043429Z.json")
AT = datetime(2026, 9, 24, 12, 10, 54, tzinfo=p.MYT)
RF = p.load_inventory_ids(p.RF_CSV)
WL = p.load_inventory_ids(p.WL_CSV)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_a: object, **_k: object) -> None:
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(p.urllib.request, "urlopen", _blocked)
    monkeypatch.setattr(p.time, "sleep", lambda _s: None)


def _rows(feed: list[dict[str, str]] = FEED) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = p.build_station_rows(
        p.parse_station_feed(feed), RF, WL, last_modified="x", retrieved_at=AT
    )
    return rows


def test_every_inventory_id_has_official_coordinates() -> None:
    rows = _rows()
    assert len(RF) == 56
    assert len(WL) == 22
    assert len(rows) == len(set(RF) | set(WL)) == 65
    assert sum(r["in_rainfall_inventory"] == "true" for r in rows) == 56
    assert sum(r["in_water_level_inventory"] == "true" for r in rows) == 22
    assert {r["source_state"] for r in rows} == {"PULAU PINANG"}


def test_coordinates_and_ids_are_verbatim() -> None:
    by_id = {r["jps_internal_id"]: r for r in _rows()}
    assert " 5402002_" in by_id  # leading space preserved, never stripped
    assert (by_id["27587"]["latitude"], by_id["27587"]["longitude"]) == ("5.402158", "100.29808")
    assert by_id["27587"]["source_sensor_types"] == "RF,WL"
    assert by_id["27587"]["retrieved_at"] == "2026-09-24T12:10:54+08:00"


def test_committed_coordinate_csv_matches_capture() -> None:
    with p.STATIONS_OUT.open(encoding="utf-8", newline="") as f:
        committed = {r["jps_internal_id"]: r for r in csv.DictReader(f)}
    fixture = {r["jps_internal_id"]: r for r in _rows()}
    assert committed.keys() == fixture.keys()
    for sid, r in fixture.items():
        assert (committed[sid]["latitude"], committed[sid]["longitude"]) == (
            r["latitude"],
            r["longitude"],
        )


def test_run_stations_writes_csv(tmp_path: Path) -> None:
    body = json.dumps(FEED).encode()
    out = tmp_path / "coords.csv"
    assert p.run_stations(lambda _u: (body, {"Last-Modified": "LM"}, AT), out) == 0
    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert tuple(rows[0]) == p.STATION_COLUMNS
    assert len(rows) == 65
    assert rows[0]["source_last_modified"] == "LM"


def test_synthetic_missing_inventory_id_is_schema_change() -> None:
    feed = [r for r in FEED if r["a"] != "27587"]
    with pytest.raises(p.SchemaError, match="absent"):
        _rows(feed)


def test_synthetic_duplicate_key_is_schema_change() -> None:
    with pytest.raises(p.SchemaError, match="duplicate"):
        p.parse_station_feed([*FEED, FEED[-1]])


def test_synthetic_missing_coordinate_key_is_schema_change() -> None:
    feed = copy.deepcopy(FEED)
    del feed[5]["c"]
    with pytest.raises(p.SchemaError, match="'c'"):
        p.parse_station_feed(feed)


@pytest.mark.parametrize(("key", "value"), [("c", "117.59"), ("d", "5.30"), ("c", "")])
def test_synthetic_coordinate_outside_penang_or_non_numeric(key: str, value: str) -> None:
    feed = copy.deepcopy(FEED)
    next(r for r in feed if r["a"] == "27587")[key] = value
    with pytest.raises(p.SchemaError, match="27587"):
        _rows(feed)


def test_synthetic_inventory_station_in_other_state_is_schema_change() -> None:
    feed = copy.deepcopy(FEED)
    next(r for r in feed if r["a"] == "27587")["f"] = "KEDAH"
    with pytest.raises(p.SchemaError, match="state"):
        _rows(feed)


def test_layers_parse_including_source_typo() -> None:
    layers = p.parse_layers(LAYERS)
    assert [(x["id"], x["year"], x["tarikh_type"]) for x in layers] == [
        (0, "1991", ""),
        (7, "1999", "String"),
        (16, "2011", "Date"),
        (26, "2017", "Date"),
    ]
    assert layers[1]["name"] == "Kawasan Banjr Tahun 1999"


def test_counts_parse() -> None:
    counts = p.parse_counts(COUNTS)
    assert len(counts) == 27
    assert counts[26] == 342
    assert sum(counts.values()) == 2222


def test_date_summary_for_date_field() -> None:
    s = p.summarise_dates(L26, "Date")
    assert s == {
        "fg_dated_count": "342",
        "fg_undated_count": "0",
        "fg_distinct_dates": "2",
        "fg_min_date": "2017-09-15",
        "fg_max_date": "2017-11-05",
    }


def test_date_summary_for_free_text_field_is_not_parsed() -> None:
    s = p.summarise_dates(L7, "String")
    assert (s["fg_dated_count"], s["fg_undated_count"], s["fg_distinct_dates"]) == ("28", "52", "5")
    assert s["fg_min_date"] == s["fg_max_date"] == ""


def test_synthetic_unexpected_layer_name_is_schema_change() -> None:
    bad = copy.deepcopy(LAYERS)
    bad["layers"][0]["name"] = "Something Else"
    with pytest.raises(p.SchemaError, match="unexpected name"):
        p.parse_layers(bad)


def test_synthetic_service_error_is_schema_change() -> None:
    err = json.dumps({"error": {"code": 400, "message": "x"}}).encode()
    with pytest.raises(p.SchemaError, match="service error"):
        p.run_flood_history(lambda _u: (err, {}, AT), Path("unused.csv"))


def test_synthetic_run_flood_history_end_to_end(tmp_path: Path) -> None:
    layers = copy.deepcopy(LAYERS)  # synthetic: drop layer 16 (no captured statistics for it)
    layers["layers"] = [x for x in layers["layers"] if x["id"] != 16]
    responses = {"/layers?": layers, "returnCountOnly": COUNTS, "/26/query": L26, "/7/query": L7}

    def fake(url: str) -> tuple[bytes, dict[str, str], datetime]:
        key = next(k for k in responses if k in url)
        return json.dumps(responses[key]).encode(), {}, AT

    out = tmp_path / "layers.csv"
    assert p.run_flood_history(fake, out) == 0
    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert tuple(rows[0]) == p.LAYER_COLUMNS
    assert [r["layer_id"] for r in rows] == ["0", "7", "26"]
    assert rows[0]["feature_count"] == "40"
    assert rows[0]["fg_dated_count"] == ""
    assert rows[2]["fg_max_date"] == "2017-11-05"
