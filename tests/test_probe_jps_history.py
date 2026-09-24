"""Offline tests for scripts/probe_jps_history.py (no network).

Fixtures: trimmed REAL captures, provenance in tests/fixtures/jps/README.md.
Tests named ``test_synthetic_*`` mutate those captures to create cases not captured.
"""

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "jps"


def _load() -> ModuleType:
    path = ROOT / "scripts" / "probe_jps_history.py"
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))  # for `import _jps_common`
    spec = importlib.util.spec_from_file_location("probe_jps_history", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


p = _load()
RF = (FIXTURES / "history_rainfall_27608_20260918_trimmed.json").read_text(encoding="utf-8")
WL_26460 = (FIXTURES / "history_water_level_26460_20260923_trimmed.json").read_text(
    encoding="utf-8"
)
WL_27608 = (FIXTURES / "history_water_level_27608_20240924_trimmed.json").read_text(
    encoding="utf-8"
)
NO_RESULT = (FIXTURES / "history_no_result.txt").read_text(encoding="utf-8")


def _summary(text: str, sensor: str) -> dict[str, Any]:
    info, rows = p.parse_history(text, sensor)
    result: dict[str, Any] = p.summarize(info, rows, sensor)
    return result


def _mutate(text: str, fn: Any) -> str:
    doc = json.loads(text)
    fn(doc)
    return json.dumps(doc)


def test_rainfall_history_parses_and_keeps_source_strings() -> None:
    info, rows = p.parse_history(RF, "rainfall")
    assert info["name"] == "Kolam Takungan Sg. Dondang M/S (F2)"
    assert len(rows) == 61
    assert rows[0] == {
        "dt": "18/09/2026 00:00",
        "raw": "0",
        "clean": "0",
        "chourly": "0",
        "cdaily": "4.5",
        "tdaily": "0",
        "cyearly": "1115",
        "c15min": "0",
    }


def test_rainfall_summary_cadence_and_semantics() -> None:
    s = _summary(RF, "rainfall")
    assert (s["rows"], s["first_dt"], s["last_dt"]) == (61, "18/09/2026 00:00", "18/09/2026 05:00")
    assert (s["dominant_interval_min"], s["irregular_interval_pct"]) == (5, 0.0)
    assert (s["duplicate_timestamps"], s["largest_gap_min"], s["primary_missing"]) == (0, 5, 0)
    assert s["info_count_matches_rows"] is True
    # Per-5-min increments: raw equals the step in the yearly cumulative total.
    assert s["semantics_checks"]["raw_eq_cyearly_step"] == "60/60"
    assert s["semantics_checks"]["cdaily_eq_prev_plus_raw"] == "59/59"
    assert (s["cdaily_at_0000"], s["cdaily_at_0005"]) == (["4.5"], ["0"])
    assert s["primary_zero"] == 51  # zero rainfall kept as zero, not missing
    assert s["raw_nonzero"] == 10


def test_water_level_sentinel_and_blank_severity() -> None:
    s = _summary(WL_26460, "water_level")
    assert s["rows"] == 10
    assert s["primary_missing"] == 5
    assert s["sentinel_counts"]["final"] == {"-9999": 5, "blank_or_null": 0}
    assert s["severity_counts"] == {"": 5, "SL_NML": 5}
    assert s["days_with_observations"] == 1


def test_water_level_error_rows_keep_raw_value() -> None:
    _, rows = p.parse_history(WL_27608, "water_level")
    assert rows[0]["severity"] == "ERROR"
    assert (rows[0]["raw"], rows[0]["final"]) == ("23.13", "-9999")
    s = p.summarize({}, rows, "water_level")
    assert s["severity_counts"] == {"": 3, "ERROR": 2, "SL_NML": 3}
    assert s["primary_missing"] == 5


def test_no_result_body_is_empty_not_schema_error() -> None:
    info, rows = p.parse_history(NO_RESULT, "rainfall")
    assert (info, rows) == ({p.NO_RESULT_KEY: "true"}, [])
    s = p.summarize(info, rows, "rainfall")
    assert (s["rows"], s["dominant_interval_min"], s["primary_missing_pct"]) == (0, None, None)


def test_build_url_matches_page_js_parameters() -> None:
    a, b = datetime(2026, 9, 18), datetime(2026, 9, 19)  # noqa: DTZ001 - source-local
    rf = p.build_url("rainfall", "27608", a, b, 5)
    wl = p.build_url("water_level", "27608", a, b, 5)
    assert "searchresultrainfalldthourlylead.php?extra=&station=27608" in rf
    assert "from=18%2F09%2F2026+00%3A00" in rf
    assert "searchresultwaterleveldtlead.php?station=27608&from=" in wl


@pytest.mark.parametrize(
    ("station", "days", "message"),
    [
        ("27608", 8, "exceeds 7 days"),
        ("27608", 0, "after start"),
        ("27608&x=1", 1, "jps_internal_id"),
        ("", 1, "jps_internal_id"),
    ],
)
def test_window_guard_rejects(station: str, days: int, message: str) -> None:
    a = datetime(2026, 9, 1)  # noqa: DTZ001
    b = datetime(2026, 9, 1 + days)  # noqa: DTZ001
    with pytest.raises(p.RequestError, match=message):
        p.validate_request(station, a, b, p.DEFAULT_MAX_DAYS)


def test_wide_cap_and_leading_space_id_accepted() -> None:
    a, b = datetime(2026, 8, 1), datetime(2026, 9, 1)  # noqa: DTZ001
    p.validate_request(" 5402002_", a, b, p.WIDE_MAX_DAYS)
    with pytest.raises(p.RequestError):
        p.validate_request("27608", a, datetime(2026, 9, 2), p.WIDE_MAX_DAYS)  # noqa: DTZ001


def test_main_rejects_wide_window_without_network(capsys: pytest.CaptureFixture[str]) -> None:
    assert p.main(["rainfall", "27608", "2026-08-01", "2026-09-01"]) == 4
    assert "REQUEST REJECTED" in capsys.readouterr().err


# --- SYNTHETIC mutations of the real captures ---


def test_synthetic_duplicate_timestamps_counted() -> None:
    def dup(doc: dict[str, Any]) -> None:
        doc["values"].insert(1, dict(doc["values"][0]))

    s = _summary(_mutate(RF, dup), "rainfall")
    assert s["duplicate_timestamps"] == 1
    assert s["info_count_matches_rows"] is False


def test_synthetic_irregular_interval_and_gap() -> None:
    def drop(doc: dict[str, Any]) -> None:
        del doc["values"][10:16]  # remove 30 minutes of rows

    s = _summary(_mutate(RF, drop), "rainfall")
    assert s["largest_gap_min"] == 35
    assert s["largest_gap_after"] == "18/09/2026 00:45"
    assert s["interval_counts_min"] == {5: 53, 35: 1}
    assert s["irregular_interval_pct"] == round(100 / 54, 2)


def test_synthetic_null_and_blank_values_are_missing() -> None:
    def blank(doc: dict[str, Any]) -> None:
        doc["values"][6]["final"] = None
        doc["values"][7]["final"] = ""

    s = _summary(_mutate(WL_26460, blank), "water_level")
    assert s["sentinel_counts"]["final"]["blank_or_null"] == 2
    assert s["primary_missing"] == 7


def test_synthetic_missing_key_is_schema_change() -> None:
    def drop_key(doc: dict[str, Any]) -> None:
        del doc["values"][0]["cyearly"]

    with pytest.raises(p.SchemaError, match="cyearly"):
        p.parse_history(_mutate(RF, drop_key), "rainfall")


def test_synthetic_changed_dt_format_is_schema_change() -> None:
    def iso(doc: dict[str, Any]) -> None:
        doc["values"][0]["dt"] = "2026-09-18T00:00"

    with pytest.raises(p.SchemaError, match="unparseable dt"):
        p.parse_history(_mutate(RF, iso), "rainfall")


def test_synthetic_malformed_body_is_schema_change() -> None:
    with pytest.raises(p.SchemaError, match="not JSON"):
        p.parse_history(RF[:200], "rainfall")
    with pytest.raises(p.SchemaError, match="info"):
        p.parse_history("[]", "water_level")


def test_synthetic_empty_values_list() -> None:
    s = _summary(_mutate(WL_26460, lambda d: d.update(values=[])), "water_level")
    assert (s["rows"], s["days_with_observations"], s["severity_counts"]) == (0, 0, {})
