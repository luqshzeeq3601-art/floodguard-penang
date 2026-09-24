"""Offline tests for scripts/probe_metmalaysia.py (no network).

Fixtures are REAL data.gov.my weather API captures (see tests/fixtures/metmalaysia/README.md).
Tests named ``test_synthetic_*`` mutate them to create cases not present in the captures.
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
FIXTURES = ROOT / "tests" / "fixtures" / "metmalaysia"


def _load() -> ModuleType:
    path = ROOT / "scripts" / "probe_metmalaysia.py"
    spec = importlib.util.spec_from_file_location("probe_metmalaysia", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


p = _load()
FORECAST: list[dict[str, Any]] = json.loads(
    (FIXTURES / "weather_forecast_trimmed_20260924T112926+0800.json").read_text("utf-8")
)
WARNING: list[dict[str, Any]] = json.loads(
    (FIXTURES / "weather_warning_20260924T112926+0800.json").read_text("utf-8")
)
AT = datetime(2026, 9, 24, 11, 29, 26, tzinfo=p.MYT)
PENANG = p.load_penang_ids()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_a: object, **_k: object) -> None:
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(p.urllib.request, "urlopen", _blocked)


def test_penang_inventory_is_28_unique_ids_with_known_categories() -> None:
    with p.PENANG_CSV.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    ids = [r["location_id"] for r in rows]
    assert len(ids) == len(set(ids)) == 28
    assert all(p.LOCATION_ID_RE.match(i) for i in ids)
    assert {r["state"] for r in rows} == {"Pulau Pinang"}
    assert PENANG["St003"] == "Pulau Pinang"
    assert PENANG["Ds012"] == "Timur Laut"


def test_forecast_filters_to_penang_and_keeps_source_fields_verbatim() -> None:
    rows = p.parse_forecast(FORECAST, PENANG, AT)
    assert len(rows) == 14  # St003 + Ds012, 7 dates each; Ds001 Langkawi dropped
    assert {r.location_id for r in rows} == {"St003", "Ds012"}
    r = next(r for r in rows if r.location_id == "Ds012" and r.forecast_date == "2026-09-24")
    assert r.texts["morning_forecast"] == "Hujan di kebanyakan tempat"
    assert r.texts["summary_when"] == "Pagi dan Petang"
    assert (r.min_temp_c, r.max_temp_c) == (24, 31)


def test_forecast_has_no_issue_time_and_retrieved_at_is_separate() -> None:
    rows = p.parse_forecast(FORECAST, PENANG, AT)
    assert all("issue" not in k for rec in FORECAST for k in rec)  # source publishes none
    assert {r.retrieved_at for r in rows} == {"2026-09-24T11:29:26+08:00"}
    assert sorted({r.forecast_date for r in rows}) == [f"2026-09-{d}" for d in range(24, 31)]


def test_warnings_parse_with_naive_times_and_nulls_kept() -> None:
    ws = p.parse_warnings(WARNING)
    assert len(ws) == 4
    assert ws[0].issued == "2026-09-24T09:00:00"
    no_adv = ws[3]
    assert (no_adv.title_en, no_adv.valid_from, no_adv.valid_to) == ("No Advisory", None, None)
    assert not any(w.fg_mentions_pulau_pinang for w in ws)


def test_warning_valid_from_before_issued_is_flagged_not_dropped() -> None:
    ws = p.parse_warnings(WARNING)
    assert [w.fg_valid_from_before_issued for w in ws] == [True, True, False, False]


def test_synthetic_zero_temperature_is_data_and_null_is_allowed() -> None:
    data = copy.deepcopy(FORECAST)
    st = [r for r in data if r["location"]["location_id"] == "St003"]
    st[0]["min_temp"] = 0
    st[1]["max_temp"] = None
    rows = {(r.location_id, r.forecast_date): r for r in p.parse_forecast(data, PENANG, AT)}
    assert rows[("St003", st[0]["date"])].min_temp_c == 0
    assert rows[("St003", st[1]["date"])].max_temp_c is None


@pytest.mark.parametrize(
    ("mutate", "msg"),
    [
        (lambda d: d[0].pop("date"), "bad date"),
        (lambda d: d[0]["location"].update(location_id="X1"), "bad location_id"),
        (lambda d: d[0].update(morning_forecast=None), "morning_forecast"),
        (lambda d: d[0].update(max_temp="32"), "max_temp"),
        (lambda d: d[0].pop("min_temp"), "min_temp"),
    ],
)
def test_synthetic_forecast_schema_violations_raise(mutate: Any, msg: str) -> None:
    data = copy.deepcopy(FORECAST)
    mutate(data)
    with pytest.raises(p.SchemaError, match=msg):
        p.parse_forecast(data, PENANG, AT)


def test_synthetic_forecast_top_level_must_be_list() -> None:
    with pytest.raises(p.SchemaError, match="expected list"):
        p.parse_forecast({"data": FORECAST}, PENANG, AT)


@pytest.mark.parametrize(
    ("mutate", "msg"),
    [
        (lambda d: d[0].pop("warning_issue"), "warning_issue"),
        (lambda d: d[0]["warning_issue"].update(issued="24/09/2026"), "unparseable"),
        (lambda d: d[0]["warning_issue"].update(issued=None), "expected ISO"),
        (lambda d: d[0].update(valid_to="2026-09-24T00:00:00+08:00"), "offset present"),
        (lambda d: d[0].pop("text_en"), "text_en"),
    ],
)
def test_synthetic_warning_schema_violations_raise(mutate: Any, msg: str) -> None:
    data = copy.deepcopy(WARNING)
    mutate(data)
    with pytest.raises(p.SchemaError, match=msg):
        p.parse_warnings(data)


def test_synthetic_penang_mention_is_detected() -> None:
    data = copy.deepcopy(WARNING)
    data[0]["text_bm"] = "Hujan berterusan dijangka di Pulau Pinang."
    assert p.parse_warnings(data)[0].fg_mentions_pulau_pinang


def test_raw_file_names() -> None:
    assert p._raw_name("forecast", AT) == "forecast_PNG_trimmed_20260924T112926+0800.json"
    assert p._raw_name("warning", AT) == "warning_20260924T112926+0800.json"


def test_run_uses_fetch_once_per_feed_and_writes_nothing_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []
    bodies = {
        f"{p.BASE}/forecast": json.dumps(FORECAST).encode(),
        f"{p.BASE}/warning": json.dumps(WARNING).encode(),
    }

    def fake_fetch(url: str) -> tuple[bytes, dict[str, str], datetime]:
        calls.append(url)
        return bodies[url], {"Date": "x", "Content-Type": "application/json"}, AT

    monkeypatch.setattr(p, "fetch", fake_fetch)
    monkeypatch.setattr(p.time, "sleep", lambda _s: None)
    assert p.run(["forecast", "warning"], write_raw=False) == 0
    assert calls == [f"{p.BASE}/forecast", f"{p.BASE}/warning"]
    out = capsys.readouterr().out
    assert "penang_rows=14" in out
    assert "issue_time=NOT_PUBLISHED" in out
    assert "wrote" not in out
