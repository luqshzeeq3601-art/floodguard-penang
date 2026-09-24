"""Offline parser tests for scripts/discover_jps_water_level_stations.py.

Fixtures under tests/fixtures/jps/ are trimmed REAL captures (see header comment in each).
Tests marked SYNTHETIC mutate those captures to simulate upstream changes or cases not
present in the Penang capture (e.g. duplicate or blank display IDs).
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
AT = "2026-09-24T01:53:00+08:00"


def _load() -> ModuleType:
    path = ROOT / "scripts" / "discover_jps_water_level_stations.py"
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))  # for `import _jps_common`
    spec = importlib.util.spec_from_file_location("discover_jps_water_level_stations", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses need the module registered
    spec.loader.exec_module(mod)
    return mod


d = _load()
PAGE_HTML = (FIXTURES / "data_paras_air_PNG_page_trimmed.html").read_text(encoding="utf-8")
RESULT_HTML = (FIXTURES / "aras_air_data_PNG_trimmed.html").read_text(encoding="utf-8")


def _parse(html: str = RESULT_HTML, page_html: str = PAGE_HTML) -> list[Any]:
    records: list[Any] = d.parse_result_table(html, d.parse_state_page(page_html), URL, AT)
    return records


def _by_id(html: str = RESULT_HTML) -> dict[str, Any]:
    return {r.jps_internal_id: r for r in _parse(html)}


def test_state_page_parses_official_districts() -> None:
    page = d.parse_state_page(PAGE_HTML)
    assert page.state_label == "Pulau Pinang"
    assert len(page.districts) == 5
    assert "Seberang Perai Utara" in page.districts
    assert page.page_last_updated == "24/09/2026 02:00"


def test_valid_parse_unique_sorted_internal_ids() -> None:
    records = _parse()
    ids = [r.jps_internal_id for r in records]
    assert len(ids) == 7
    assert len(set(ids)) == 7
    assert ids == sorted(ids)
    assert {r.state for r in records} == {"Pulau Pinang"}


def test_fields_parse_verbatim() -> None:
    r = _by_id()["27587"]
    assert (r.jps_display_station_id, r.station_name) == (
        "1910131WL",
        "Sg. Air Itam di Lorong Batu Lanchang (F2)",
    )
    assert (r.district, r.main_basin, r.sub_river_basin) == (
        "Timur Laut Pulau Pinang",
        "Sungai Pinang",
        "Sg. Air Itam",
    )
    assert r.latest_observation_time == "2026-09-24T01:45:00"
    assert r.water_level_m == "5.00"  # text as published, not re-formatted
    assert (r.source_row, r.source_url, r.discovered_at) == (1, URL, AT)


def test_thresholds_as_published_and_order_flag() -> None:
    by_id = _by_id()
    r = by_id["27587"]
    assert (r.threshold_normal, r.threshold_alert, r.threshold_warning, r.threshold_danger) == (
        "4.00",
        "5.20",
        "5.50",
        "6.00",
    )
    assert r.fg_threshold_order_flag == "ok"
    # Normal above the current level is published as-is and not judged.
    assert by_id["5302004_"].threshold_normal == "19.50"
    assert {x.fg_threshold_order_flag for x in by_id.values()} == {"ok"}


def test_no_data_display_id_flagged_and_code_style_internal_ids() -> None:
    by_id = _by_id()
    assert by_id["26189"].jps_display_station_id == "No Data"
    assert by_id["26189"].fg_display_station_id_flag == "no_data_text"
    assert by_id["BUMBUNGLIMA"].fg_display_station_id_flag == "ok"


def test_fg_freshness() -> None:
    by_id = _by_id()
    assert (by_id["26460"].fg_freshness_minutes, by_id["26460"].fg_freshness_status) == (
        630,
        "stale",
    )  # 23/09 15:15 vs newest 24/09 01:45
    assert (
        by_id["BUMBUNGLIMA"].fg_freshness_minutes,
        by_id["BUMBUNGLIMA"].fg_freshness_status,
    ) == (
        45,
        "reporting",
    )


def test_threshold_order_flag_rule() -> None:
    assert d.fg_threshold_order_flag(1.0, 1.0, 2.0) == "ok"
    assert d.fg_threshold_order_flag(2.0, 1.5, 3.0) == "not_ascending"
    assert d.fg_threshold_order_flag(None, 1.5, 3.0) == "missing"


def test_csv_deterministic(tmp_path: Path) -> None:
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    d.jc.write_csv(_parse(), d.CSV_COLUMNS, a)
    d.jc.write_csv(_parse(), d.CSV_COLUMNS, b)
    assert a.read_bytes() == b.read_bytes()
    with a.open(encoding="utf-8") as f:
        assert tuple(next(csv.reader(f))) == d.CSV_COLUMNS


# --- SYNTHETIC mutations of the real captures ---


def test_synthetic_duplicate_display_ids_preserved() -> None:
    html = RESULT_HTML.replace(">1910111WL<", ">1910131WL<")
    by_id = _by_id(html)
    assert by_id["27587"].jps_display_station_id == by_id["27608"].jps_display_station_id
    assert by_id["27587"].fg_display_station_id_flag == "duplicate"
    assert by_id["27608"].fg_display_station_id_flag == "duplicate"


def test_synthetic_blank_display_id_flagged() -> None:
    by_id = _by_id(RESULT_HTML.replace(">5504401<", "><"))
    assert by_id["BUMBUNGLIMA"].jps_display_station_id == ""
    assert by_id["BUMBUNGLIMA"].fg_display_station_id_flag == "missing"


def test_synthetic_non_ascending_thresholds_flagged_not_repaired() -> None:
    html = RESULT_HTML.replace(
        "<td data-th='Alert'>5.20</td><td data-th='Warning'>5.50</td>",
        "<td data-th='Alert'>5.60</td><td data-th='Warning'>5.50</td>",
    )
    r = _by_id(html)["27587"]
    assert (r.threshold_alert, r.threshold_warning) == ("5.60", "5.50")
    assert r.fg_threshold_order_flag == "not_ascending"


def test_synthetic_blank_threshold_flagged_missing() -> None:
    html = RESULT_HTML.replace("<td data-th='Danger'>6.00</td>", "<td data-th='Danger'></td>")
    assert _by_id(html)["27587"].fg_threshold_order_flag == "missing"


def test_synthetic_non_numeric_level_fails() -> None:
    html = RESULT_HTML.replace("5.00</a>", "OFF</a>", 1)
    with pytest.raises(d.SchemaError, match="non-numeric water level"):
        _parse(html)


def test_synthetic_malformed_row_fails() -> None:
    html = RESULT_HTML.replace("<td data-th='Danger'>6.00</td>", "", 1)
    with pytest.raises(d.SchemaError, match="cells"):
        _parse(html)


def test_synthetic_header_change_fails() -> None:
    with pytest.raises(d.SchemaError, match="Bahaya"):
        _parse(RESULT_HTML.replace(">Bahaya<", ">Danger<"))


def test_synthetic_non_penang_district_fails() -> None:
    html = RESULT_HTML.replace(
        "<td data-th='District'>Seberang Perai Selatan</td>",
        "<td data-th='District'>Kerian</td>",
        1,
    )
    with pytest.raises(d.SchemaError, match="not in official list"):
        _parse(html)


def test_synthetic_non_penang_state_fails() -> None:
    page = PAGE_HTML.replace("<option value='PNG' selected='selected'>", "<option value='PNG'>")
    page = page.replace("<option value='PRK'>", "<option value='PRK' selected='selected'>")
    with pytest.raises(d.SchemaError, match="Perak"):
        _parse(page_html=page)


def test_synthetic_empty_table_fails() -> None:
    head = RESULT_HTML[: RESULT_HTML.index("<tbody>")]
    with pytest.raises(d.SchemaError, match="no station rows"):
        _parse(head + "<tbody></tbody></table>")
