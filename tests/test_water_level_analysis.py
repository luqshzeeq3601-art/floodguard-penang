"""Offline tests for the water-level trend analysis (Phase 3).

Every water-level series here is SYNTHETIC (year 2030, invented sensor IDs and thresholds); none
is evidence about any Penang river gauge.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from floodguard.analysis.dataset import AnalysisContractError, to_json_bytes
from floodguard.analysis.water_level import (
    CADENCE_UNVERIFIED,
    CADENCE_VERIFIED,
    CURRENT_REFERENCE_ONLY,
    GAP_EXCEEDS_MAX,
    INSUFFICIENT,
    INSUFFICIENT_SAMPLE,
    NETWORK_HISTORICAL,
    NOT_ESTABLISHED,
    NOT_USABLE_ROW_BETWEEN,
    SCHEMA_VERSION,
    SPAN_EXCEEDS_GUARD,
    SPANS_BREAKS,
    STATION_WINDOW_DESCRIPTIVE,
    SUFFICIENT,
    WaterLevelAnalysisConfig,
    analyze,
    consecutive_changes,
    load_threshold_reference,
)

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
MYT = timezone(timedelta(hours=8))
START = datetime(2030, 1, 1, 0, 0, tzinfo=MYT)
CFG = WaterLevelAnalysisConfig()
Row = dict[str, Any]
MARKER = object()  # a -9999 source marker
ERROR = object()  # JPS severity ERROR with -9999


def row(
    minute: float,
    value: float | object | None,
    *,
    sensor: str = "S1",
    start: datetime = START,
    measurement_type: str = "WATER_LEVEL",
    unit: str = "m",
    sensor_type: str = "WATER_LEVEL",
    flags: Sequence[str] = (),
) -> Row:
    """SYNTHETIC canonical row at ``start + minute``. ``MARKER``/``ERROR`` are ``-9999`` rows,
    ``None`` a blank value; any float is a usable level in metres."""
    local = start + timedelta(minutes=minute)
    usable = isinstance(value, float | int)
    fl = ["TIMEZONE_ASSUMED", *flags]
    if value is MARKER or value is ERROR:
        fl.append("VALUE_MISSING_SENTINEL")
        status, raw = "SOURCE_MARKER", "-9999"
    elif value is None:
        fl.append("VALUE_MISSING")
        status, raw = "BLANK", ""
    else:
        status, raw = "NUMERIC", str(value)
    if value is ERROR:
        fl.append("SOURCE_SEVERITY_ERROR")
    return {
        "observation_schema_version": "observations/v1",
        "source": "JPS_PUBLIC_INFOBANJIR",
        "fg_sensor_id": sensor,
        "fg_site_id": f"site-{sensor}",
        "sensor_type": sensor_type,
        "measurement_type": measurement_type,
        "datasets": ["water_level_history"],
        "observation_time_local": local.isoformat(),
        "observation_time_utc": local.astimezone(UTC).isoformat(),
        "value": value if usable else None,
        "value_raw": raw,
        "value_parse_status": status,
        "unit": unit,
        "quality_flags": sorted(fl),
        "usable": usable,
    }


def series(values: Sequence[float | object | None], step: float = 5, **kw: Any) -> list[Row]:
    return [row(i * step, v, **kw) for i, v in enumerate(values)]


def station(
    rows: Sequence[Row], config: WaterLevelAnalysisConfig = CFG, **kw: Any
) -> dict[str, Any]:
    doc = analyze(rows, dataset_version="synthetic0000001", config=config, **kw)
    assert len(doc["stations"]) == 1
    result: dict[str, Any] = doc["stations"][0]
    return result


def win(s: dict[str, Any], i: int = 0) -> dict[str, Any]:
    result: dict[str, Any] = s["observation_windows"][i]
    return result


def changes(s: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = s["consecutive_changes"]
    return result


# --- level statistics and consecutive changes ----------------------------------------------


def test_constant_level() -> None:
    s = station(series([2.5] * 10))
    lv, c = win(s)["levels"], changes(s)
    assert (lv["mean_m"], lv["min_m"], lv["max_m"], lv["range_m"]) == (2.5, 2.5, 2.5, 0.0)
    assert lv["std_m"] == {"status": "OK", "value": 0.0}
    assert c["valid_pairs"] == 9
    assert c["direction_counts"] == {"RISING": 0, "FALLING": 0, "STABLE": 9}
    assert {p["rate_m_per_h"] for p in c["pairs"]} == {0.0}
    assert win(s)["net_change_first_to_last_usable_m"] == {
        "status": "OK",
        "value": 0.0,
        "span_minutes": 45.0,
    }


def test_steadily_rising_level_and_rate() -> None:
    s = station(series([1.0 + 0.01 * i for i in range(13)]))
    c = changes(s)
    assert c["direction_counts"] == {"RISING": 12, "FALLING": 0, "STABLE": 0}
    assert {p["change_m"] for p in c["pairs"]} == {0.01}
    assert {p["rate_m_per_h"] for p in c["pairs"]} == {0.12}  # 0.01 m per 5 min
    assert {p["gap_minutes"] for p in c["pairs"]} == {5.0}
    assert win(s)["net_change_first_to_last_usable_m"]["value"] == 0.12
    assert s["continuity"]["longest_run"]["observations"] == 13


def test_steadily_falling_level() -> None:
    s = station(series([3.0 - 0.02 * i for i in range(6)]))
    c = changes(s)
    assert c["direction_counts"] == {"RISING": 0, "FALLING": 5, "STABLE": 0}
    assert {p["change_m"] for p in c["pairs"]} == {-0.02}
    assert {p["rate_m_per_h"] for p in c["pairs"]} == {-0.24}
    assert c["max_abs_change_m"] == 0.02


def test_alternating_values() -> None:
    s = station(series([1.0, 1.1] * 5))
    c = changes(s)
    assert c["direction_counts"] == {"RISING": 5, "FALLING": 4, "STABLE": 0}
    assert c["change"]["mean_m"] == pytest.approx(0.1 / 9, abs=1e-6)
    assert win(s)["net_change_first_to_last_usable_m"]["value"] == 0.1


def test_stable_tolerance_is_configurable() -> None:
    cfg = WaterLevelAnalysisConfig(stable_tolerance_m=0.01)
    c = changes(station(series([1.0, 1.01, 1.03]), cfg))
    assert [p["direction"] for p in c["pairs"]] == ["STABLE", "RISING"]


def test_single_observation() -> None:
    s = station(series([1.5]))
    assert win(s)["levels"]["count"] == 1
    assert win(s)["levels"]["std_m"] == {"status": INSUFFICIENT_SAMPLE, "n": 1, "required_n": 2}
    assert win(s)["net_change_first_to_last_usable_m"]["status"] == INSUFFICIENT_SAMPLE
    assert changes(s)["valid_pairs"] == 0
    assert changes(s)["change"] == {"count": 0, "status": "NO_DATA"}
    assert s["continuity"]["runs"] == 1
    assert s["continuity"]["largest_gap_between_usable_minutes"] is None


def test_all_missing_values() -> None:
    s = station(series([MARKER, ERROR, None, MARKER]))
    assert win(s)["levels"] == {"count": 0, "status": "NO_DATA"}
    assert s["observation_windows"][0]["first_usable_utc"] is None
    assert s["coverage"]["usable_rows"] == 0
    assert s["coverage"]["usable_percent_of_rows"] == 0.0
    assert changes(s)["valid_pairs"] == 0
    assert s["continuity"]["runs"] == 0
    assert s["continuity"]["longest_run"] is None


def test_missing_markers_are_traceable_and_never_zero() -> None:
    s = station(series([1.0, MARKER, ERROR, None, 1.2]))
    cov = s["coverage"]
    assert (cov["canonical_rows"], cov["usable_rows"], cov["not_usable_rows"]) == (5, 2, 3)
    assert cov["usable_percent_of_rows"] == 40.0
    assert cov["not_usable_by_source_value"] == {"BLANK:": 1, "SOURCE_MARKER:-9999": 2}
    assert cov["not_usable_flags"]["SOURCE_SEVERITY_ERROR"] == 1
    assert cov["not_usable_flags"]["VALUE_MISSING_SENTINEL"] == 2
    assert win(s)["levels"]["min_m"] == 1.0  # nothing was filled with 0


@pytest.mark.parametrize("gap", [MARKER, ERROR, None])
def test_no_change_across_an_unusable_row(gap: object) -> None:
    # A 15-min gap tolerance would admit 1.0 -> 1.5; the unusable row between still breaks it.
    cfg = WaterLevelAnalysisConfig(max_gap_minutes=15)
    c = changes(station(series([1.0, gap, 1.5]), cfg))
    assert c["valid_pairs"] == 0
    assert c["breaks"] == [
        {
            "from_utc": row(0, 1.0)["observation_time_utc"],
            "to_utc": row(10, 1.0)["observation_time_utc"],
            "gap_minutes": 10.0,
            "reason": NOT_USABLE_ROW_BETWEEN,
        }
    ]


def test_usable_row_with_error_severity_breaks_continuity() -> None:
    rows = series([1.0, 1.1, 1.2])
    rows[1] = row(5, 1.1, flags=["SOURCE_SEVERITY_ERROR"])
    s = station(rows)
    assert changes(s)["valid_pairs"] == 0
    assert s["coverage"]["usable_rows_with_continuity_breaking_flags"] == 1
    assert win(s)["levels"]["count"] == 3  # still a usable level (Phase 2 semantics)


def test_irregular_gaps_and_rate_uses_actual_elapsed_time() -> None:
    rows = [row(0, 1.0), row(5, 1.1), row(15, 1.3), row(20, 1.2)]
    c = changes(station(rows))
    assert [(p["gap_minutes"], p["change_m"]) for p in c["pairs"]] == [(5.0, 0.1), (5.0, -0.1)]
    assert c["breaks"][0]["reason"] == GAP_EXCEEDS_MAX
    assert c["breaks"][0]["gap_minutes"] == 10.0
    wide = changes(station(rows, WaterLevelAnalysisConfig(max_gap_minutes=10)))
    assert [p["rate_m_per_h"] for p in wide["pairs"]] == [1.2, 1.2, -1.2]  # 0.2 m / (10/60 h)
    assert wide["pair_gap_minutes"] == {"5": 2, "10": 1}


def test_long_missing_gap_breaks_trend() -> None:
    rows = series([1.0, 1.1, 1.2]) + [row(180 + 5 * i, 2.0 + 0.1 * i) for i in range(3)]
    s = station(rows)
    c = changes(s)
    assert c["valid_pairs"] == 4
    assert all(p["gap_minutes"] == 5.0 for p in c["pairs"])  # no 170-min slope
    assert c["breaks"] == [
        {
            "from_utc": rows[2]["observation_time_utc"],
            "to_utc": rows[3]["observation_time_utc"],
            "gap_minutes": 170.0,
            "reason": GAP_EXCEEDS_MAX,
        }
    ]
    assert s["continuity"]["runs"] == 2
    assert s["continuity"]["largest_gap_between_usable_minutes"] == 170.0
    assert s["continuity"]["longest_run"]["start_utc"] == rows[0]["observation_time_utc"]


def test_longest_run_and_break_counts() -> None:
    s = station(series([1.0, 1.0, MARKER, 1.0, 1.0, 1.0, MARKER, MARKER, 1.0]))
    cont = s["continuity"]
    assert (cont["runs"], cont["breaks"]) == (3, 2)
    assert cont["breaks_by_reason"] == {NOT_USABLE_ROW_BETWEEN: 2}
    assert cont["longest_run"]["observations"] == 3
    assert cont["longest_run"]["duration_minutes"] == 10.0


def test_net_change_refused_beyond_span_guard() -> None:
    rows = series([1.0, 1.1, 1.2, 1.5, 1.4], step=720)  # one window (gaps <= 1 day), 2 days long
    s = station(rows, WaterLevelAnalysisConfig(max_gap_minutes=720))  # one continuous run
    assert len(s["observation_windows"]) == 1
    net = win(s)["net_change_first_to_last_usable_m"]
    assert net == {"status": SPAN_EXCEEDS_GUARD, "span_minutes": 2880.0}


@pytest.mark.parametrize(
    "rows",
    [
        series([1.0, 1.1, MARKER, 1.3]),  # a -9999 between the endpoints
        series([1.0, 1.1, ERROR, 1.3]),
        [row(0, 1.0), row(5, 1.1), row(60, 1.3)],  # absent slots between the endpoints
        [row(0, 1.0), row(360, 1.2)],  # two listing-style snapshots 6 h apart
    ],
)
def test_net_change_refused_across_breaks(rows: list[Row]) -> None:
    # Regression: net change was OK across missing values and long gaps.
    net = win(station(rows))["net_change_first_to_last_usable_m"]
    assert net["status"] == SPANS_BREAKS
    assert net["breaks_between"] == 1
    assert "value" not in net


def test_net_change_refused_when_an_endpoint_run_has_error_flag() -> None:
    rows = series([1.0, 1.1, 1.2])
    rows[1] = row(5, 1.1, flags=["SOURCE_SEVERITY_ERROR"])
    net = win(station(rows))["net_change_first_to_last_usable_m"]
    assert net["status"] == SPANS_BREAKS
    assert net["usable_rows_with_continuity_breaking_flags"] == 1


def test_levels_not_pooled_across_separate_captures() -> None:
    # Regression: a history day and listing readings two years later formed one level sample
    # (artefactual range and std). Separate captures are separate windows.
    rows = series([19.18, 19.17, MARKER, 19.19])
    later = row(2 * 365 * 1440, 15.43)
    later["datasets"] = ["water_level_listing"]
    rows += [later, row(2 * 365 * 1440 + 120, 15.43)]
    s = station(rows)
    assert s["levels_pooled_across_windows"] is False
    first, second = s["observation_windows"]
    assert (first["levels"]["min_m"], first["levels"]["max_m"]) == (19.17, 19.19)
    assert first["levels"]["range_m"] == 0.02
    assert first["rows_by_dataset"] == {"water_level_history": 4}
    assert (second["canonical_rows"], second["levels"]["mean_m"]) == (2, 15.43)
    assert second["rows_by_dataset"] == {"water_level_history": 1, "water_level_listing": 1}
    assert "levels" not in s
    assert changes(s)["valid_pairs"] == 1  # 19.18 -> 19.17 only; nothing across the 2 years


def test_negative_levels_are_kept() -> None:
    s = station(series([-0.5, -0.4]))
    assert win(s)["levels"]["min_m"] == -0.5
    assert changes(s)["pairs"][0]["direction"] == "RISING"


def test_deterministic_quantiles() -> None:
    values = [i / 100 for i in range(100)]
    q = win(station(series(values)))["levels"]["quantiles_m"]
    assert q["p5"] == {"status": "OK", "value": 0.0495}  # linear (type 7)
    assert q["p25"] == {"status": "OK", "value": 0.2475}
    assert q["p50"] == {"status": "OK", "value": 0.495}
    assert q["p95"] == {"status": "OK", "value": 0.9405}
    q99 = win(station(series(values[:99])))["levels"]["quantiles_m"]
    assert q99["p5"] == {"status": INSUFFICIENT_SAMPLE, "n": 99, "required_n": 100}
    assert q99["p25"]["status"] == "OK"


def test_repeated_output_is_byte_identical_regardless_of_row_order() -> None:
    rows = series([1.0, 1.2, MARKER, 1.1, 1.3]) + series([5.0, 5.1], sensor="S2")
    shuffled = rows[:]
    random.Random(7).shuffle(shuffled)
    a = to_json_bytes(analyze(rows, dataset_version="v"))
    assert a == to_json_bytes(analyze(rows, dataset_version="v"))
    assert a == to_json_bytes(analyze(shuffled, dataset_version="v"))


def test_future_observations_do_not_change_earlier_changes() -> None:
    base = [1.0, 1.1, MARKER, 1.2, 1.4, 1.3]
    prefix = series(base)
    future = series([*base, 9.0, -3.0, MARKER, 7.5])
    p1, b1, _ = consecutive_changes(prefix, CFG)
    p2, b2, _ = consecutive_changes(future, CFG)
    assert p2[: len(p1)] == p1
    assert b2[: len(b1)] == b1
    altered = series([*base[:4], 50.0, 1.3])  # change a later value only
    p3, _, _ = consecutive_changes(altered, CFG)
    assert p3[0] == p1[0]  # the 1.0 -> 1.1 change ignores anything after it


# --- contract -------------------------------------------------------------------------------


def test_duplicate_timestamps_rejected() -> None:
    rows = series([1.0, 1.1])
    rows.append(row(5, 1.1))
    with pytest.raises(AnalysisContractError, match="repeated"):
        analyze(rows, dataset_version="v")


def test_duplicate_instant_in_another_text_form_rejected() -> None:
    rows = series([1.0, 1.1])
    dup = row(5, 1.1)
    dup["observation_time_utc"] = dup["observation_time_utc"].replace("+00:00", "Z")
    rows.append(dup)
    with pytest.raises(AnalysisContractError, match="repeated"):
        analyze(rows, dataset_version="v")


def test_rainfall_rows_cannot_enter() -> None:
    rows = series([1.0, 1.1]) + series(
        [0.0, 5.0], measurement_type="RAINFALL_INTERVAL", unit="mm", sensor_type="RAINFALL"
    )
    doc = analyze(rows, dataset_version="v")
    assert doc["input"]["water_level_rows"] == 2
    assert doc["input"]["excluded_rows_by_measurement_type"] == {"RAINFALL_INTERVAL": 2}
    assert [win(s)["levels"]["count"] for s in doc["stations"]] == [2]
    rain_sensor = series([1.0], sensor_type="RAINFALL")
    with pytest.raises(AnalysisContractError, match="sensor type"):
        analyze(rain_sensor, dataset_version="v")


@pytest.mark.parametrize("unit", ["mm", "cm", ""])
def test_wrong_unit_rejected(unit: str) -> None:
    with pytest.raises(AnalysisContractError, match="unit"):
        analyze(series([1.0], unit=unit), dataset_version="v")


def test_threshold_and_excluded_fields_cannot_enter_as_observations() -> None:
    for mt in ("WATER_LEVEL_THRESHOLD", "WATER_LEVEL_RAW", "WATER_LEVEL_CLEAN"):
        with pytest.raises(AnalysisContractError, match="unknown measurement type"):
            analyze(series([2.8], measurement_type=mt), dataset_version="v")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "1.0"])
def test_invalid_usable_value_rejected(value: object) -> None:
    rows = series([1.0])
    rows[0]["value"] = value
    with pytest.raises(AnalysisContractError, match="invalid"):
        analyze(rows, dataset_version="v")


def test_local_and_utc_must_be_the_same_instant() -> None:
    rows = series([1.0])
    rows[0]["observation_time_utc"] = row(5, 1.0)["observation_time_utc"]
    with pytest.raises(AnalysisContractError, match="different instants"):
        analyze(rows, dataset_version="v")


def test_config_validation() -> None:
    for kw in (
        {"max_gap_minutes": 0},
        {"max_gap_minutes": float("inf")},
        {"stable_tolerance_m": -0.01},
        {"quantiles": (0.5, 0.25)},
        {"expected_interval_minutes": 7},
        {"min_valid_pairs": 0},
        {"max_gap_minutes": 1500},  # a pair could join two observation windows
    ):
        with pytest.raises(ValueError, match="must"):
            WaterLevelAnalysisConfig(**kw)


# --- multiple stations ----------------------------------------------------------------------


def test_stations_analysed_separately_without_cross_station_averaging() -> None:
    rows = series([1.0, 1.2], sensor="S1") + series([10.0, 10.4], sensor="S2")
    doc = analyze(rows, dataset_version="v")
    by = {s["fg_sensor_id"]: s for s in doc["stations"]}
    assert win(by["S1"])["levels"]["mean_m"] == 1.1
    assert win(by["S2"])["levels"]["mean_m"] == 10.2
    assert by["S1"]["fg_site_id"] == "site-S1"
    net = doc["network"]
    assert net["cross_station_level_aggregation"].startswith("NONE")
    assert (net["canonical_rows"], net["usable_rows"]) == (4, 4)
    assert not any(k.endswith("_m") for k in net)
    pooled = 5.65  # mean of all four levels: must not appear anywhere
    assert str(pooled) not in to_json_bytes(doc).decode("utf-8")
    # no pair ever joins two sensors, even at identical times
    for s in doc["stations"]:
        assert changes(s)["valid_pairs"] == 1


def test_sensor_with_two_sites_rejected() -> None:
    rows = series([1.0, 1.1])
    rows[1]["fg_site_id"] = "other"
    with pytest.raises(AnalysisContractError, match="fg_site_id"):
        analyze(rows, dataset_version="v")


# --- cadence and sufficiency ----------------------------------------------------------------


def test_cadence_status_from_quality_summary() -> None:
    rows = series([1.0 + 0.01 * i for i in range(40)])
    entry = {"rows": 40, "usable": 40, "history_cadence": {"off_grid_rows": 0}}
    qs = {"series": {"S1/WATER_LEVEL": entry}}
    doc = analyze(rows, dataset_version="v", quality_summary=qs)
    assert doc["stations"][0]["continuity"]["cadence_status"] == CADENCE_VERIFIED
    assert doc["sufficiency"]["rate_of_change"]["status"] == SUFFICIENT
    doc = analyze(rows, dataset_version="v")
    assert doc["stations"][0]["continuity"]["cadence_status"] == CADENCE_UNVERIFIED
    assert doc["sufficiency"]["consecutive_change"]["status"] == SUFFICIENT
    assert doc["sufficiency"]["rate_of_change"]["status"] == INSUFFICIENT


def test_small_window_sufficiency() -> None:
    # 289 slots, 35 usable, scattered: the shape of the limited local captures
    values: list[float | object] = [MARKER] * 289
    for i in range(0, 289, 8)[:35]:
        values[i] = 1.0
    doc = analyze(series(values), dataset_version="v")
    suff = {k: v["status"] for k, v in doc["sufficiency"].items()}
    assert suff["basic_descriptive"] == SUFFICIENT
    for k in (
        "quantiles",
        "consecutive_change",
        "rate_of_change",
        "station_comparison",
        "seasonal_trend",
        "monsoon_comparison",
        "threshold_event_analysis",
        "long_term_trend",
    ):
        assert suff[k] == INSUFFICIENT, k
    assert doc["evidence_levels_supported"] == [
        "IMPLEMENTATION_VERIFICATION",
        STATION_WINDOW_DESCRIPTIVE,
    ]


def test_multi_year_sufficiency_paths() -> None:
    # One reading per day (config: daily slots) for two stations over three years.
    cfg = WaterLevelAnalysisConfig(
        expected_interval_minutes=1440,
        min_day_coverage=1.0,
        max_gap_minutes=1440,
        min_complete_years_long_term=2,
        min_usable_descriptive=30,
    )
    days = (datetime(2033, 1, 1, tzinfo=MYT) - START).days
    rows = series([1.0] * days, step=1440, sensor="A") + series([2.0] * days, step=1440, sensor="B")
    doc = analyze(rows, dataset_version="v", config=cfg)
    suff = {k: v["status"] for k, v in doc["sufficiency"].items()}
    assert suff["seasonal_trend"] == SUFFICIENT
    assert suff["station_comparison"] == SUFFICIENT
    assert suff["long_term_trend"] == SUFFICIENT
    assert suff["monsoon_comparison"] == INSUFFICIENT  # no verified season definition
    assert suff["threshold_event_analysis"] == INSUFFICIENT  # never from unversioned thresholds
    assert NETWORK_HISTORICAL in doc["evidence_levels_supported"]
    cfg_m = WaterLevelAnalysisConfig(**{**cfg.__dict__, "monsoon_definition_source": "doc-x"})
    doc_m = analyze(rows, dataset_version="v", config=cfg_m)
    assert doc_m["sufficiency"]["monsoon_comparison"]["status"] == SUFFICIENT


# --- threshold reference --------------------------------------------------------------------


def _thresholds(captured: str = "2030-06-01T02:00:00+08:00") -> list[dict[str, Any]]:
    return [
        {
            "threshold_type": t,
            "value_m": v,
            "threshold_source": "JPS_NATIONAL_LISTING",
            "captured_at": captured,
            "valid_from": None,
        }
        for t, v in (("NORMAL", 0.0), ("WASPADA", 2.8), ("AMARAN", 3.2), ("BAHAYA", 3.6))
    ]


def test_thresholds_are_reference_metadata_only() -> None:
    rows = series([2.7, 2.9, 3.3, 3.7])  # crosses every synthetic threshold
    doc = analyze(rows, dataset_version="v", threshold_reference={"S1": _thresholds()})
    ref = doc["stations"][0]["threshold_reference"]
    assert [t["threshold_type"] for t in ref["thresholds"]] == ["WASPADA", "AMARAN", "BAHAYA"]
    assert ref["excluded_threshold_types"] == {"NORMAL": 1}  # never a target level
    assert ref["used_as_label"] is False
    for t in ref["thresholds"]:
        assert t["temporal_validity"] == CURRENT_REFERENCE_ONLY
        assert t["valid_at_observation_times"] == NOT_ESTABLISHED
        assert (t["threshold_source"], t["captured_at"]) == (
            "JPS_NATIONAL_LISTING",
            "2030-06-01T02:00:00+08:00",
        )

    def keys(x: Any) -> set[str]:
        if isinstance(x, dict):
            return set(x) | {k for v in x.values() for k in keys(v)}
        return {k for v in x for k in keys(v)} if isinstance(x, list) else set()

    produced = keys(doc) - {"used_as_label"}
    for word in ("exceed", "flood", "label", "target", "event"):
        assert not [k for k in produced if word in k.lower() and k != "threshold_event_analysis"]
    assert doc["sufficiency"]["threshold_event_analysis"]["status"] == INSUFFICIENT
    assert doc["sufficiency"]["threshold_event_analysis"]["observed"] == {
        "versioned_thresholds": 0,
        "current_reference_thresholds": 3,
    }


def test_history_thresholds_not_assumed_valid_at_observation_time() -> None:
    # A history response returns today's thresholds beside old observations.
    rows = series([2.0, 2.1])
    doc = analyze(
        rows,
        dataset_version="v",
        threshold_reference={"S1": _thresholds(captured="2032-01-01T00:00:00+08:00")},
    )
    for t in doc["stations"][0]["threshold_reference"]["thresholds"]:
        assert t["captured_after_last_usable_observation"] is True
        assert t["valid_at_observation_times"] == NOT_ESTABLISHED
        assert t["valid_from"] is None


def test_no_threshold_input_means_no_reference() -> None:
    assert station(series([1.0]))["threshold_reference"] is None
    assert station(series([1.0]), threshold_reference={})["threshold_reference"]["thresholds"] == []


def _write_master(master: Path, unit: str = "m") -> None:
    master.mkdir(exist_ok=True)
    (master / "sensors.csv").write_text(
        "fg_sensor_id,fg_site_id,sensor_type,jps_internal_id\nS1,site-S1,WATER_LEVEL,9\n",
        encoding="utf-8",
    )
    (master / "sites.csv").write_text(
        "fg_site_id,district,main_basin\nsite-S1,D,B\n", encoding="utf-8"
    )
    (master / "thresholds.csv").write_text(
        "fg_threshold_id,fg_sensor_id,threshold_type,value,unit,threshold_source,captured_at,"
        "valid_from,fg_label_eligible\n"
        f"t1,S1,WASPADA,2.80,{unit},JPS_NATIONAL_LISTING,2030-06-01T02:00:00+08:00,,true\n"
        f"t2,S1,NORMAL,0.00,{unit},JPS_NATIONAL_LISTING,2030-06-01T02:00:00+08:00,,false\n",
        encoding="utf-8",
    )


def test_load_threshold_reference(tmp_path: Path) -> None:
    _write_master(tmp_path / "m")
    refs, digest = load_threshold_reference(tmp_path / "m")
    assert len(digest) == 64
    assert [t["threshold_type"] for t in refs["S1"]] == ["WASPADA", "NORMAL"]
    assert "fg_label_eligible" not in refs["S1"][0]  # the station-master flag is not read
    _write_master(tmp_path / "bad", unit="cm")
    with pytest.raises(AnalysisContractError, match="unit"):
        load_threshold_reference(tmp_path / "bad")


# --- processed dataset and the one-shot script ----------------------------------------------


def _dataset(
    root: Path,
    rows: list[Row],
    version: str = "synthv1",
    *,
    origin: str | None = None,
    series_summary: dict[str, Any] | None = None,
) -> Path:
    d = root / version
    d.mkdir(parents=True)
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode("utf-8")
    (d / "observations.jsonl").write_bytes(data)
    (d / "quality_summary.json").write_text(
        json.dumps(
            {"summary_schema_version": "quality_summary/v1", "series": series_summary or {}}
        ),
        encoding="utf-8",
    )
    manifest = {
        "dataset_version": version,
        "observations_sha256": hashlib.sha256(data).hexdigest(),
        "observations_rows": len(rows),
        "checks": [{"name": "canonical_key_unique", "passed": True}],
        "station_master_origin": origin,
    }
    (d / "dataset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return d


def _origin(master: Path) -> str:
    return (
        "sensors.csv@sha256:"
        + hashlib.sha256((master / "sensors.csv").read_bytes()).hexdigest()[:16]
    )


def test_script_refuses_other_station_master(tmp_path: Path) -> None:
    master = tmp_path / "master"
    _write_master(master)
    d = _dataset(tmp_path / "p", series([1.0]), origin="sensors.csv@sha256:0000000000000000")
    args = ["--dataset", str(d), "--output-root", str(tmp_path / "o")]
    assert _script().main([*args, "--station-master-dir", str(master)]) == 2
    assert not (tmp_path / "o").exists()


def test_script_refuses_quality_summary_of_other_rows(tmp_path: Path) -> None:
    # Regression: the unhashed summary alone set the cadence status.
    rows = series([1.0, 1.1])
    stale = {
        "S1/WATER_LEVEL": {"rows": 289, "usable": 289, "history_cadence": {"off_grid_rows": 0}}
    }
    d = _dataset(tmp_path / "p", rows, series_summary=stale)
    args = ["--dataset", str(d), "--output-root", str(tmp_path / "o")]
    assert _script().main([*args, "--station-master-dir", str(tmp_path / "none")]) == 2
    ok = {"S1/WATER_LEVEL": {"rows": 2, "usable": 2, "history_cadence": {"off_grid_rows": 0}}}
    d2 = _dataset(tmp_path / "p2", rows, series_summary=ok)
    args = ["--dataset", str(d2), "--output-root", str(tmp_path / "o2")]
    assert _script().main([*args, "--station-master-dir", str(tmp_path / "none")]) == 0


def test_threshold_captured_at_without_offset_rejected(tmp_path: Path) -> None:
    # Regression: a naive captured_at crashed the comparison with a raw TypeError.
    _write_master(tmp_path / "m")
    path = tmp_path / "m" / "thresholds.csv"
    path.write_text(path.read_text("utf-8").replace("+08:00", ""), "utf-8")
    with pytest.raises(AnalysisContractError, match="offset"):
        load_threshold_reference(tmp_path / "m")


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "analyze_water_level", ROOT / "scripts" / "analyze_water_level.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_script_offline_byte_identical_and_lineage(tmp_path: Path) -> None:
    rows = series([1.0, 1.1, MARKER, 1.2]) + series(
        [0.0], measurement_type="RAINFALL_INTERVAL", unit="mm", sensor_type="RAINFALL"
    )
    master = tmp_path / "master"
    _write_master(master)
    d = _dataset(tmp_path / "processed", rows, origin=_origin(master))
    main = _script().main

    def run(name: str) -> int:
        args = ["--dataset", str(d), "--output-root", str(tmp_path / name)]
        result: int = main([*args, "--station-master-dir", str(master)])
        return result

    out1 = tmp_path / "run1" / "synthv1" / "water_level_trends.json"
    assert run("run1") == 0
    assert run("run2") == 0
    assert out1.read_bytes() == (tmp_path / "run2" / "synthv1" / out1.name).read_bytes()
    doc = json.loads(out1.read_text(encoding="utf-8"))
    obs_sha = hashlib.sha256((d / "observations.jsonl").read_bytes()).hexdigest()
    assert doc["analysis_schema_version"] == SCHEMA_VERSION
    assert doc["dataset_version"] == "synthv1"
    assert doc["input"]["observations_sha256"] == obs_sha
    assert len(doc["input"]["station_master_sha256"]) == 64
    assert len(doc["input"]["threshold_reference_sha256"]) == 64
    assert doc["stations"][0]["station"]["jps_internal_id"] == "9"
    assert doc["stations"][0]["threshold_reference"]["used_as_label"] is False
    assert run("run1") == 0  # identical rerun: no-op
    out1.write_bytes(b"{}")
    assert run("run1") == 2  # existing output differs: refused
    (d / "observations.jsonl").write_bytes(b"{}\n")
    assert run("run3") == 2  # tampered input: refused
    assert main(["--dataset", str(tmp_path / "missing")]) == 2
