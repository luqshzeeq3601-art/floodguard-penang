"""Offline parser tests for scripts/discover_jps_rainfall_stations.py.

Fixtures under tests/fixtures/jps/ are trimmed REAL captures (see header comment in each).
Tests marked SYNTHETIC mutate those captures to simulate upstream schema changes.
"""

import csv
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "jps"
URL = "https://example.invalid/source"
AT = "2026-09-24T01:45:00+08:00"


def _load() -> ModuleType:
    path = ROOT / "scripts" / "discover_jps_rainfall_stations.py"
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))  # for `import _jps_common`
    spec = importlib.util.spec_from_file_location("discover_jps_rainfall_stations", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses need the module registered
    spec.loader.exec_module(mod)
    return mod


d = _load()
PAGE_HTML = (FIXTURES / "data_hujan_PNG_page_trimmed.html").read_text(encoding="utf-8")
RESULT_HTML = (FIXTURES / "searchresultrainfall_PNG_trimmed.html").read_text(encoding="utf-8")


def _records() -> list[Any]:
    records: list[Any] = d.parse_result_table(RESULT_HTML, d.parse_state_page(PAGE_HTML), URL, AT)
    return records


def test_state_page_parses_official_districts() -> None:
    page = d.parse_state_page(PAGE_HTML)
    assert page.state_label == "Pulau Pinang"
    assert page.districts == (
        "Barat Daya Pulau Pinang",
        "Seberang Perai Selatan",
        "Seberang Perai Tengah",
        "Seberang Perai Utara",
        "Timur Laut Pulau Pinang",
    )
    assert page.page_last_updated == "24/09/2026 01:45"


def test_result_rows_parse_exactly_as_published() -> None:
    by_key = {r.jps_internal_id: r for r in _records()}
    assert len(by_key) == 9
    r = by_key["27603"]
    assert (r.jps_display_station_id, r.station_name, r.district) == (
        "1910111RF",
        "Kolam Bersih (F2)",
        "Timur Laut Pulau Pinang",
    )
    assert r.latest_observation_time == "2026-09-24T01:15:00"
    assert (r.state, r.source_url, r.discovered_at, r.source_row) == ("Pulau Pinang", URL, AT, 1)
    # Leading space in the upstream link parameter is preserved, not normalised.
    assert by_key[" 5402002_"].jps_display_station_id == "5402002"


def test_station_id_problems_are_flagged_not_dropped() -> None:
    flags = {r.jps_internal_id: r.fg_display_station_id_flag for r in _records()}
    assert flags["27603"] == flags["27608"] == "duplicate"  # both 1910111RF
    assert flags["27616"] == flags["27666"] == "duplicate"  # both 0000000RF
    assert flags["26186"] == "missing"
    assert flags["26185"] == "no_data_text"
    assert flags["BUMBUNGLIMA"] == "ok"


def test_fg_freshness_is_relative_to_newest_row() -> None:
    fresh = {r.jps_internal_id: (r.fg_freshness_minutes, r.fg_freshness_status) for r in _records()}
    assert fresh["27616"] == (435, "stale")  # 23/09 18:00 vs newest 24/09 01:15
    assert fresh["27643"] == (195, "stale")  # 23/09 22:00
    assert fresh["27666"] == (15, "reporting")  # 24/09 01:00
    assert fresh["27603"] == (0, "reporting")


def test_records_sorted_and_csv_deterministic(tmp_path: Path) -> None:
    records = _records()
    keys = [r.jps_internal_id for r in records]
    assert keys == sorted(keys)
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    d.jc.write_csv(records, d.CSV_COLUMNS, a)
    d.jc.write_csv(records, d.CSV_COLUMNS, b)
    assert a.read_bytes() == b.read_bytes()
    with a.open(encoding="utf-8") as f:
        assert tuple(next(csv.reader(f))) == d.CSV_COLUMNS


# --- SYNTHETIC mutations of the real captures (simulated upstream changes) ---


def test_synthetic_missing_header_fails() -> None:
    html = RESULT_HTML.replace("Nama Stesen", "Station Name")
    with pytest.raises(d.SchemaError, match="Nama Stesen"):
        d.parse_result_table(html, d.parse_state_page(PAGE_HTML), URL, AT)


def test_synthetic_extra_cell_fails() -> None:
    html = RESULT_HTML.replace("<td>Kolam Bersih (F2)</td>", "<td>Kolam Bersih (F2)</td><td>x</td>")
    with pytest.raises(d.SchemaError, match="cells"):
        d.parse_result_table(html, d.parse_state_page(PAGE_HTML), URL, AT)


def test_synthetic_unknown_district_fails() -> None:
    html = RESULT_HTML.replace("<td>Seberang Perai Tengah</td>", "<td>Kuala Muda</td>", 1)
    with pytest.raises(d.SchemaError, match="not in official list"):
        d.parse_result_table(html, d.parse_state_page(PAGE_HTML), URL, AT)


def test_synthetic_wrong_state_fails() -> None:
    page = PAGE_HTML.replace("<option value='PNG' selected='selected'>", "<option value='PNG'>")
    page = page.replace("<option value='KDH'>", "<option value='KDH' selected='selected'>")
    with pytest.raises(d.SchemaError, match="Kedah"):
        d.parse_result_table(RESULT_HTML, d.parse_state_page(page), URL, AT)


def test_synthetic_duplicate_graph_key_fails() -> None:
    html = RESULT_HTML.replace("stationid=27608", "stationid=27603")
    with pytest.raises(d.SchemaError, match="duplicate"):
        d.parse_result_table(html, d.parse_state_page(PAGE_HTML), URL, AT)


def test_synthetic_bad_timestamp_fails() -> None:
    html = RESULT_HTML.replace("24/09/2026 01:15:00", "2026-09-24 01:15", 1)
    with pytest.raises(d.SchemaError, match="time"):
        d.parse_result_table(html, d.parse_state_page(PAGE_HTML), URL, AT)
