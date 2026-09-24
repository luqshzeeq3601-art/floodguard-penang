"""Offline tests for scripts/probe_jps_live.py and the live-freshness rule (no network).

Snapshot fixtures are the trimmed REAL listing captures (provenance: tests/fixtures/jps/README.md).
Tests named ``test_synthetic_*`` mutate them to create cases not present in the captures.
"""

import importlib.util
import re
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "jps"


def _load() -> ModuleType:
    path = ROOT / "scripts" / "probe_jps_live.py"
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))  # for `import _jps_common` and discovery modules
    spec = importlib.util.spec_from_file_location("probe_jps_live", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


p = _load()
jc = p.jc


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


RF_HTML = _read("searchresultrainfall_PNG_trimmed.html")
RF_PAGE = jc.parse_state_page(_read("data_hujan_PNG_page_trimmed.html"))
WL_HTML = _read("aras_air_data_PNG_trimmed.html")
WL_PAGE = jc.parse_state_page(_read("data_paras_air_PNG_page_trimmed.html"))
# Capture times of the fixtures (see fixture header comments).
RF_AT = datetime(2026, 9, 24, 1, 39, tzinfo=jc.MYT)
WL_AT = datetime(2026, 9, 24, 1, 53, tzinfo=jc.MYT)


def _rf(html: str = RF_HTML) -> dict[str, Any]:
    return {o.jps_internal_id: o for o in p.parse_listing(html, "rainfall", RF_PAGE, RF_AT)}


def _wl(html: str = WL_HTML) -> dict[str, Any]:
    return {o.jps_internal_id: o for o in p.parse_listing(html, "water_level", WL_PAGE, WL_AT)}


def test_rainfall_snapshot_fields_and_times_kept_separate() -> None:
    o = _rf()["27603"]
    assert (o.source, o.measurement_type, o.jps_display_station_id) == (
        "jps_publicinfobanjir",
        "rainfall",
        "1910111RF",
    )
    assert o.observation_time_raw == "24/09/2026 01:15:00"
    assert o.observation_time == "2026-09-24T01:15:00"
    assert o.retrieved_at == "2026-09-24T01:39:00+08:00"
    assert o.values == {"rainfall_since_midnight_mm": "0.0", "rainfall_1h_mm": "0.0"}
    assert (o.fg_age_minutes, o.fg_live_status) == (24, "FRESH")  # zero rain is data


def test_rainfall_zero_values_are_not_no_data() -> None:
    obs = _rf()
    assert all(o.values["rainfall_1h_mm"] == "0.0" for o in obs.values())
    assert "NO_DATA" not in {o.fg_live_status for o in obs.values()}


def test_rainfall_stale_rows_kept_and_classified() -> None:
    obs = _rf()
    assert len(obs) == 9
    assert (obs["27616"].fg_age_minutes, obs["27616"].fg_live_status) == (459, "STALE")
    assert (obs["27643"].fg_age_minutes, obs["27643"].fg_live_status) == (219, "STALE")


def test_water_level_snapshot_thresholds_and_status() -> None:
    obs = _wl()
    o = obs["27587"]
    assert o.values == {
        "water_level_m": "5.00",
        "threshold_normal": "4.00",
        "threshold_alert": "5.20",
        "threshold_warning": "5.50",
        "threshold_danger": "6.00",
    }
    assert (o.fg_age_minutes, o.fg_live_status) == (8, "FRESH")
    assert obs["26460"].fg_live_status == "STALE"  # 23/09 15:15
    assert all(all(v for v in x.values.values()) for x in obs.values())


def test_station_ids_sorted_and_unique() -> None:
    ids = [o.jps_internal_id for o in p.parse_listing(WL_HTML, "water_level", WL_PAGE, WL_AT)]
    assert ids == sorted(set(ids))


@pytest.mark.parametrize(
    ("age", "value_ok", "expected"),
    [
        (None, True, "INVALID"),
        (-6, True, "INVALID"),
        (-5, True, "FRESH"),
        (0, False, "NO_DATA"),
        (30, True, "FRESH"),
        (31, True, "DELAYED"),
        (180, True, "DELAYED"),
        (181, True, "STALE"),
        (500, False, "NO_DATA"),
    ],
)
def test_fg_live_status_boundaries(age: int | None, value_ok: bool, expected: str) -> None:
    rule = jc.LiveRule(
        expected_interval_minutes=15, allowed_lag_minutes=15, stale_after_minutes=180
    )
    assert jc.fg_live_status(age, value_ok, rule) == expected


def test_fg_age_minutes_assumes_kuala_lumpur_and_floors() -> None:
    at = datetime(2026, 9, 24, 8, 0, 59, tzinfo=jc.MYT)
    assert jc.fg_age_minutes(datetime(2026, 9, 24, 7, 45), at) == 15  # noqa: DTZ001
    assert jc.fg_age_minutes(None, at) is None


def test_live_rules_single_source_of_stale_threshold() -> None:
    assert {r.stale_after_minutes for r in jc.LIVE_RULES.values()} == {jc.FG_STALE_AFTER_MINUTES}


def test_main_rejects_unbounded_sampling(capsys: pytest.CaptureFixture[str]) -> None:
    assert p.main(["rainfall", "--samples", "21"]) == 4
    assert p.main(["rainfall", "--samples", "2", "--interval", "30"]) == 4
    assert "REQUEST REJECTED" in capsys.readouterr().err


# --- SYNTHETIC mutations of the real captures ---


def test_synthetic_no_data_values() -> None:
    html = re.sub(r">\s*5\.00</a>", ">-9999</a>", WL_HTML, count=1)
    html = re.sub(r">\s*15\.43</a>", "></a>", html, count=1)
    obs = _wl(html)
    assert (obs["27587"].values["water_level_m"], obs["27587"].fg_live_status) == (
        "-9999",
        "NO_DATA",
    )
    assert (obs["27608"].values["water_level_m"], obs["27608"].fg_live_status) == ("", "NO_DATA")


def test_synthetic_missing_timestamp_is_invalid_not_dropped() -> None:
    html = RF_HTML.replace("<td>24/09/2026 01:15:00</td>", "<td></td>", 1)
    o = _rf(html)["27603"]
    assert (o.observation_time_raw, o.observation_time) == ("", None)
    assert (o.fg_age_minutes, o.fg_live_status) == (None, "INVALID")


def test_synthetic_future_timestamp_is_invalid() -> None:
    html = RF_HTML.replace("<td>24/09/2026 01:15:00</td>", "<td>24/09/2026 02:15:00</td>", 1)
    assert _rf(html)["27603"].fg_live_status == "INVALID"


def test_synthetic_schema_change_raises() -> None:
    with pytest.raises(p.SchemaError, match="Bahaya"):
        _wl(WL_HTML.replace(">Bahaya<", ">Danger<"))


def test_synthetic_malformed_response_raises() -> None:
    with pytest.raises(p.SchemaError):
        _rf("<html><body>Service temporarily unavailable</body></html>")
    with pytest.raises(p.SchemaError, match="cells"):
        _rf(RF_HTML.replace("<td>Kolam Bersih (F2)</td>", "<td>Kolam Bersih (F2)</td><td>x</td>"))


def test_synthetic_tiada_data_reply_is_reported() -> None:
    # Row markup copied from the observed reply to state=XXX (HTTP 200, 2026-09-24).
    head = RF_HTML[: RF_HTML.index("<tbody>")]
    html = head + "<tbody>\n<tr><td colspan='15'>Tiada Data</td>\n</tbody></table></div>"
    with pytest.raises(p.SchemaError, match="Tiada Data"):
        _rf(html)
