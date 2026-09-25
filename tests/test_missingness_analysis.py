"""Offline tests for the missingness analysis (Phase 3).

Every series here is SYNTHETIC (year 2030, invented sensor and batch IDs); none is evidence about
any Penang station.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from floodguard.analysis.dataset import AnalysisContractError
from floodguard.analysis.missingness import (
    ABSENT_NO_VALIDATED_ROW,
    ABSENT_SLOT,
    ABSENT_UNRESOLVED,
    CADENCE_OFF_GRID,
    CADENCE_VERIFIED,
    GAP_EXCEEDS_MAX_ABSENT,
    INSUFFICIENT,
    INSUFFICIENT_SAMPLE,
    MISSING,
    OK,
    POINT_IN_TIME,
    SCHEMA_VERSION,
    SEPARATE_CAPTURES,
    SUFFICIENT,
    WINDOW_DESCRIPTIVE,
    MissingnessConfig,
    analyze,
    segment_runs,
)

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
MYT = timezone(timedelta(hours=8))
START = datetime(2030, 1, 1, 0, 0, tzinfo=MYT)
Row = dict[str, Any]
M9999, ERR_VALUE, TIADA, BLANK, SEV_ERROR = "-9999", "ERROR", "Tiada Data", "", "SEV"
MARKERS = {
    M9999: ("SOURCE_MARKER", "-9999", "VALUE_MISSING_SENTINEL"),
    ERR_VALUE: ("SOURCE_MARKER", "ERROR", "VALUE_SOURCE_ERROR"),
    TIADA: ("SOURCE_MARKER", "Tiada Data", "VALUE_NO_DATA_MARKER"),
    BLANK: ("EMPTY", "", "VALUE_EMPTY"),
}
WL = {"measurement_type": "WATER_LEVEL", "unit": "m", "sensor_type": "WATER_LEVEL"}
RAIN = {"measurement_type": "RAINFALL_INTERVAL", "unit": "mm", "sensor_type": "RAINFALL"}


def row(
    minute: float,
    value: float | str | None,
    *,
    sensor: str = "S1",
    start: datetime = START,
    kind: dict[str, str] = WL,
    dataset: str | None = None,
    batch: str = "B1",
) -> Row:
    """SYNTHETIC canonical row at ``start + minute``. A float is usable; a key of ``MARKERS`` is
    that source marker; ``SEV_ERROR`` is ``-9999`` with JPS severity ERROR."""
    local = start + timedelta(minutes=minute)
    flags = ["TIMEZONE_ASSUMED"]
    if isinstance(value, float | int):
        status, raw, v = "NUMERIC", str(value), float(value)
    else:
        marker = M9999 if value == SEV_ERROR else value
        status, raw, flag = MARKERS[str(marker)]
        flags.append(flag)
        if value == SEV_ERROR:
            flags.append("SOURCE_SEVERITY_ERROR")
        v = None
    ds = dataset or ("water_level_history" if kind is WL else "rainfall_history")
    return {
        "observation_schema_version": "observations/v1",
        "source": "JPS_PUBLIC_INFOBANJIR",
        "fg_sensor_id": sensor,
        "fg_site_id": f"site-{sensor}",
        **kind,
        "observation_time_local": local.isoformat(),
        "observation_time_utc": local.astimezone(UTC).isoformat(),
        "value": v,
        "value_raw": raw,
        "value_parse_status": status,
        "usable": v is not None,
        "quality_flags": sorted(flags),
        "datasets": [ds],
        "provenance": [{"dataset": ds, "ingestion_batch_id": batch, "source_row_index": 0}],
    }


def series(values: Sequence[float | str | None], step: float = 5, **kw: Any) -> list[Row]:
    return [row(i * step, v, **kw) for i, v in enumerate(values)]


def run(rows: list[Row], config: MissingnessConfig | None = None, **kw: Any) -> dict[str, Any]:
    return analyze(rows, dataset_version="synthetic0000001", config=config, **kw)


def only(doc: dict[str, Any]) -> dict[str, Any]:
    assert len(doc["series"]) == 1
    result: dict[str, Any] = doc["series"][0]
    return result


def win(rows: list[Row], i: int = 0, **kw: Any) -> dict[str, Any]:
    result: dict[str, Any] = only(run(rows, **kw))["cadence_windows"][i]
    return result


def missing_runs(w: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in w["runs"] if r["state"] == MISSING]


# --- window-level counts --------------------------------------------------------------------


def test_fully_observed_window() -> None:
    w = win(series([1.0] * 289))
    assert w["cadence_status"] == CADENCE_VERIFIED
    assert (w["expected_slots"], w["usable_slots"], w["missing_slots"]) == (289, 289, 0)
    assert (w["coverage_percent"], w["missing_percent"]) == (100.0, 0.0)
    assert w["missing_runs"]["count"] == 0
    assert w["missing_runs"]["longest"] is None
    assert w["usable_runs"]["longest"]["slots"] == 289
    assert (w["first_missing_utc"], w["starts_with_missing"], w["ends_with_missing"]) == (
        None,
        False,
        False,
    )
    assert w["full_local_days"] == 1


def test_fully_missing_window() -> None:
    w = win(series([M9999] * 12))
    assert (w["usable_slots"], w["missing_slots"], w["coverage_percent"]) == (0, 12, 0.0)
    assert w["missing_by_type"]["SENTINEL_-9999"] == 12
    assert w["missing_runs"]["count"] == 1
    longest = w["missing_runs"]["longest"]
    assert (longest["at_window_start"], longest["at_window_end"]) == (True, True)
    assert w["usable_runs"]["count"] == 0
    assert (w["starts_with_missing"], w["ends_with_missing"]) == (True, True)


def test_one_missing_slot_in_the_middle() -> None:
    w = win(series([1.0, 1.0, M9999, 1.0, 1.0]))
    (m,) = missing_runs(w)
    assert m["slots"] == 1
    assert m["start_utc"] == m["end_utc"] == w["first_missing_utc"] == w["last_missing_utc"]
    assert (m["at_window_start"], m["at_window_end"]) == (False, False)
    assert w["usable_runs"]["count"] == 2
    assert w["missing_percent"] == 20.0


def test_missing_run_at_beginning_and_end() -> None:
    begin = win(series([M9999, M9999, 1.0, 1.0]))
    assert (begin["starts_with_missing"], begin["ends_with_missing"]) == (True, False)
    assert missing_runs(begin)[0]["at_window_start"]
    end = win(series([1.0, M9999, M9999]))
    assert (end["starts_with_missing"], end["ends_with_missing"]) == (False, True)
    assert missing_runs(end)[0]["at_window_end"]
    assert end["missing_runs"]["touching_window_boundary"] == 1


def test_multiple_runs_ordered_and_longest_is_earliest_of_ties() -> None:
    w = win(series([M9999, 1.0, M9999, M9999, 1.0, M9999, M9999, 1.0, 1.0, 1.0]))
    runs = w["runs"]
    assert [r["state"] for r in runs] == [MISSING, "USABLE", MISSING, "USABLE", MISSING, "USABLE"]
    assert [r["start_utc"] for r in runs] == sorted(r["start_utc"] for r in runs)
    assert [r["slots"] for r in missing_runs(w)] == [1, 2, 2]
    assert w["missing_runs"]["longest"]["start_utc"] == missing_runs(w)[1]["start_utc"]
    assert w["usable_runs"]["longest"]["slots"] == 3


def test_exact_run_duration_has_no_extra_interval() -> None:
    w = win(series([1.0, M9999, M9999, M9999, 1.0]))
    (m,) = missing_runs(w)
    assert m["slots"] == 3
    assert m["first_to_last_slot_minutes"] == 10  # 00:05 -> 00:15
    assert m["slot_minutes"] == 15
    assert m["start_local"] == "2030-01-01T00:05:00+08:00"
    assert m["end_local"] == "2030-01-01T00:15:00+08:00"
    single = missing_runs(win(series([1.0, M9999, 1.0])))[0]
    assert (single["first_to_last_slot_minutes"], single["slot_minutes"]) == (0, 5)


def test_segment_runs_partition_every_slot_once() -> None:
    t = [START + timedelta(minutes=5 * i) for i in range(6)]
    states = ["USABLE", ABSENT_SLOT, "SENTINEL_-9999", "USABLE", "USABLE", ABSENT_SLOT]
    runs = segment_runs(list(zip(t, states, strict=True)))
    assert sum(r["slots"] for r in runs) == 6
    assert runs[1]["slots_by_missing_type"] == {ABSENT_SLOT: 1, "SENTINEL_-9999": 1}


# --- source markers -------------------------------------------------------------------------


def test_markers_kept_distinct() -> None:
    w = win(series([M9999, ERR_VALUE, TIADA, BLANK, SEV_ERROR, 1.0]))
    t = w["missing_by_type"]
    assert (t["SENTINEL_-9999"], t["VALUE_ERROR"], t["TIADA_DATA"], t["BLANK"]) == (2, 1, 1, 1)
    assert t[ABSENT_SLOT] == 0
    sev = w["source_severity_error"]
    assert sev == {
        "rows": 1,
        "usable_rows": 0,
        "measurement_missing_rows_by_type": {"SENTINEL_-9999": 1},
    }
    assert w["missing_flags"]["VALUE_SOURCE_ERROR"] == 1


def test_error_is_a_source_state_never_a_hardware_outage() -> None:
    doc = run(series([SEV_ERROR, SEV_ERROR, 1.0]))
    assert doc["cause_attributed"] is False
    text = json.dumps(doc).lower()
    for claim in ("sensor failure", "hardware failure", "power failure", "offline sensor"):
        assert claim not in text
    assert "never read as a device" in doc["definitions"]["source_severity_error"]


def test_zero_is_observed_not_missing() -> None:
    wl = win(series([0.0, 0.0, 0.0]))
    rain = win(series([0.0] * 4, kind=RAIN))
    assert wl["missing_slots"] == rain["missing_slots"] == 0
    assert rain["usable_slots"] == 4


def test_absent_slot_distinct_from_marker_row() -> None:
    rows = [row(0, 1.0), row(5, M9999), row(15, 1.0)]  # 00:10 has no row at all
    w = win(rows)
    assert w["expected_slots"] == 4
    assert (w["missing_by_type"]["SENTINEL_-9999"], w["absent_slots"]) == (1, 1)
    assert w["missing_by_type"][ABSENT_SLOT] == 1
    assert w["source_rows"] == 3
    (m,) = missing_runs(w)
    assert m["slots_by_missing_type"] == {ABSENT_SLOT: 1, "SENTINEL_-9999": 1}


def test_absent_slot_attribution_from_quality_summary() -> None:
    rows = [row(0, 1.0), row(10, 1.0)]
    base = {"rows": 2, "usable": 2}
    s = only(run(rows, quality_summary={"series": {"S1/WATER_LEVEL": base}}))
    assert s["absent_slot_attribution"]["status"] == ABSENT_UNRESOLVED
    cad = {"history_cadence": {"history_rows_not_in_canonical": 0}}
    s = only(run(rows, quality_summary={"series": {"S1/WATER_LEVEL": base | cad}}))
    assert s["absent_slot_attribution"]["status"] == ABSENT_NO_VALIDATED_ROW
    with pytest.raises(AnalysisContractError, match="quality summary"):
        run(rows, quality_summary={"series": {"S1/WATER_LEVEL": {"rows": 9, "usable": 2}}})


# --- windows and gaps -----------------------------------------------------------------------


def test_irregular_gap_breaks_window_without_missing_slots() -> None:
    rows = series([1.0, 1.0]) + series([1.0, M9999], start=START + timedelta(hours=3))
    s = only(run(rows))
    assert len(s["cadence_windows"]) == 2
    (b,) = s["window_boundaries"]
    assert (b["reason"], b["gap_minutes"], b["slots_between_classified"]) == (
        GAP_EXCEEDS_MAX_ABSENT,
        175.0,
        False,
    )
    assert sum(w["absent_slots"] for w in s["cadence_windows"]) == 0
    # a gap within the guard is absent slots in one window
    s = only(run(rows, MissingnessConfig(max_absent_gap_minutes=180)))
    assert len(s["cadence_windows"]) == 1
    assert s["cadence_windows"][0]["absent_slots"] == 34


def test_captures_years_apart_are_separate_windows_not_one_outage() -> None:
    later = START + timedelta(days=730)
    rows = series([1.0, M9999, 1.0], batch="B2024") + series(
        [M9999, 1.0], start=later, batch="B2026"
    )
    s = only(run(rows, MissingnessConfig(max_absent_gap_minutes=10**7)))
    assert [w["expected_slots"] for w in s["cadence_windows"]] == [3, 2]
    (b,) = s["window_boundaries"]
    assert b["reason"] == SEPARATE_CAPTURES
    assert max(w["missing_slots"] for w in s["cadence_windows"]) == 1
    assert [w["ingestion_batch_ids"] for w in s["cadence_windows"]] == [["B2024"], ["B2026"]]


def test_touching_captures_merge_but_gapped_captures_do_not() -> None:
    a = series([1.0, 1.0], batch="A")
    b = series([1.0, 1.0], start=START + timedelta(minutes=10), batch="B")
    s = only(run(a + b))
    assert [w["expected_slots"] for w in s["cadence_windows"]] == [4]
    assert s["cadence_windows"][0]["ingestion_batch_ids"] == ["A", "B"]
    c = series([1.0, 1.0], start=START + timedelta(minutes=15), batch="C")
    s = only(run(a + c))  # 00:05 -> 00:15: one unobserved slot between two captures
    assert [w["expected_slots"] for w in s["cadence_windows"]] == [2, 2]
    assert s["window_boundaries"][0]["reason"] == SEPARATE_CAPTURES


def test_listing_rows_get_no_historical_cadence() -> None:
    listing = [
        row(0, 1.0, dataset="water_level_listing", batch="L1"),
        row(137, M9999, dataset="water_level_listing", batch="L2"),
    ]
    s = only(run(listing))
    assert s["cadence_windows"] == []
    assert s["window_boundaries"] == []
    pit = s["point_in_time"]
    assert pit["cadence_status"] == POINT_IN_TIME
    assert (pit["rows"], pit["usable_rows"]) == (2, 1)
    assert pit["measurement_missing_by_type"] == {"SENTINEL_-9999": 1}
    assert pit["outage_interpretation"].startswith("NONE")
    doc = run(listing)
    assert doc["network"]["WATER_LEVEL"]["expected_slots"] == 0
    assert doc["sufficiency"]["WATER_LEVEL"]["window_level_missingness"]["status"] == INSUFFICIENT


def test_history_plus_listing_years_later_stay_separate() -> None:
    later = START + timedelta(days=730)
    rows = [
        *series([1.0, M9999, 1.0]),
        row(0, 2.0, start=later, dataset="water_level_listing", batch="L"),
    ]
    s = only(run(rows))
    assert [w["expected_slots"] for w in s["cadence_windows"]] == [3]
    assert s["point_in_time"]["rows"] == 1
    assert s["cadence_windows"][0]["listing_only_rows_in_window"] == 0


def test_off_grid_rows_leave_cadence_unverified() -> None:
    rows = [row(0, 1.0), row(7, 1.0), row(10, M9999)]
    w = win(rows)
    assert w["cadence_status"] == CADENCE_OFF_GRID
    assert w["expected_slots"] is None
    assert "runs" not in w
    assert w["missing_by_type"]["SENTINEL_-9999"] == 1


# --- sensors and measurement types ----------------------------------------------------------


def test_sensors_and_measurement_types_are_separate() -> None:
    rows = (
        series([1.0, M9999], sensor="S1")
        + series([M9999, M9999, M9999], sensor="S2")
        + series([0.0, 0.0], sensor="S1", kind=RAIN)
    )
    doc = run(rows)
    keys = [(s["measurement_type"], s["fg_sensor_id"]) for s in doc["series"]]
    assert keys == [("RAINFALL_INTERVAL", "S1"), ("WATER_LEVEL", "S1"), ("WATER_LEVEL", "S2")]
    net = doc["network"]
    assert net["RAINFALL_INTERVAL"]["slot_weighted_coverage_percent"] == 100.0
    wl = net["WATER_LEVEL"]
    assert (wl["expected_slots"], wl["usable_slots"]) == (5, 1)
    assert wl["slot_weighted_coverage_percent"] == 20.0  # not mean(50%, 0%) = 25%
    assert "not an average" in net["calculation"]


# --- run-length statistics and sufficiency --------------------------------------------------


def test_run_length_quantiles_guarded() -> None:
    w = win(series([M9999, 1.0, M9999, M9999, 1.0]))
    length = w["missing_runs"]["length"]
    assert (length["count"], length["min_slots"], length["max_slots"]) == (2, 1, 2)
    assert length["mean_slots"]["status"] == INSUFFICIENT_SAMPLE
    assert length["quantiles_slots"]["p50"] == {
        "status": INSUFFICIENT_SAMPLE,
        "n": 2,
        "required_n": 10,
    }
    many = win(series([M9999, 1.0] * 10))
    q = many["missing_runs"]["length"]["quantiles_slots"]
    assert q["p50"] == {"status": OK, "value": 1.0}
    assert q["p90"]["status"] == INSUFFICIENT_SAMPLE


def test_one_day_supports_window_descriptive_only() -> None:
    pair: list[float | str | None] = [1.0, M9999]
    values = [*pair * 144, 1.0]
    doc = run(series(values))
    suf = doc["sufficiency"]["WATER_LEVEL"]
    assert suf["window_level_missingness"]["status"] == SUFFICIENT
    assert suf["run_length_analysis"]["status"] == SUFFICIENT
    for k in (
        "sensor_comparison",
        "network_wide_comparison",
        "seasonal_missingness",
        "monsoon_missingness",
        "long_term_reliability",
        "live_outage_detection",
    ):
        assert suf[k]["status"] == INSUFFICIENT, k
    assert doc["evidence_levels_supported"] == ["IMPLEMENTATION_VERIFICATION", WINDOW_DESCRIPTIVE]


def test_config_guards() -> None:
    with pytest.raises(ValueError, match="max_absent_gap"):
        MissingnessConfig(max_absent_gap_minutes=4)
    with pytest.raises(ValueError, match="quantiles"):
        MissingnessConfig(quantiles=(0.5, 0.25))


# --- contract -------------------------------------------------------------------------------


def test_duplicate_canonical_observation_rejected() -> None:
    rows = series([1.0, 1.0])
    rows.append(dict(rows[0]))
    with pytest.raises(AnalysisContractError, match="repeated canonical key"):
        run(rows)


def test_contract_violations_rejected() -> None:
    bad = series([1.0])
    bad[0]["provenance"] = []
    with pytest.raises(AnalysisContractError, match="provenance"):
        run(bad)
    bad = series([1.0])
    bad[0]["provenance"][0]["dataset"] = "water_level_forecast"
    with pytest.raises(AnalysisContractError, match="unknown source dataset"):
        run(bad)
    bad = series([M9999])
    bad[0]["quality_flags"] = ["TIMEZONE_ASSUMED"]
    with pytest.raises(AnalysisContractError, match="no blocking flag"):
        run(bad)
    with pytest.raises(AnalysisContractError, match="dataset_version"):
        analyze(series([1.0]), dataset_version="")


def test_version_and_hashes_propagate() -> None:
    manifest = {"station_master_origin": "sensors.csv@sha256:ab", "components": {"x": "y/v1"}}
    doc = run(
        series([1.0]),
        observations_sha256="o" * 64,
        station_master_sha256="s" * 64,
        manifest=manifest,
    )
    assert doc["analysis_schema_version"] == SCHEMA_VERSION
    assert doc["dataset_version"] == "synthetic0000001"
    inp = doc["input"]
    assert (inp["observations_sha256"], inp["station_master_sha256"]) == ("o" * 64, "s" * 64)
    assert inp["station_master_origin"] == "sensors.csv@sha256:ab"
    assert inp["dataset_components"] == {"x": "y/v1"}
    assert doc["imputation_performed"] is False


# --- processed dataset and the one-shot script ----------------------------------------------


def _dataset(root: Path, rows: list[Row], *, origin: str | None = None) -> Path:
    d = root / "synthv1"
    d.mkdir(parents=True)
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode("utf-8")
    (d / "observations.jsonl").write_bytes(data)
    (d / "quality_summary.json").write_text(
        json.dumps({"summary_schema_version": "quality_summary/v1", "series": {}}), "utf-8"
    )
    manifest = {
        "dataset_version": "synthv1",
        "observations_sha256": hashlib.sha256(data).hexdigest(),
        "observations_rows": len(rows),
        "checks": [{"name": "canonical_key_unique", "passed": True}],
        "station_master_origin": origin,
    }
    (d / "dataset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return d


def _master(master: Path) -> str:
    master.mkdir()
    (master / "sensors.csv").write_text(
        "fg_sensor_id,fg_site_id,sensor_type,jps_internal_id\nS1,site-S1,WATER_LEVEL,9\n", "utf-8"
    )
    (master / "sites.csv").write_text("fg_site_id,district,main_basin\nsite-S1,D,B\n", "utf-8")
    digest = hashlib.sha256((master / "sensors.csv").read_bytes()).hexdigest()
    return f"sensors.csv@sha256:{digest[:16]}"


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "analyze_missingness", ROOT / "scripts" / "analyze_missingness.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_script_offline_byte_identical_and_lineage(tmp_path: Path) -> None:
    master = tmp_path / "master"
    origin = _master(master)
    d = _dataset(tmp_path / "p", series([1.0, M9999, SEV_ERROR, 1.0]), origin=origin)
    main = _script().main

    def go(name: str, sm: Path = master) -> int:
        args = ["--dataset", str(d), "--output-root", str(tmp_path / name)]
        result: int = main([*args, "--station-master-dir", str(sm)])
        return result

    out = tmp_path / "r1" / "synthv1" / "missingness.json"
    assert go("r1") == 0
    assert go("r2") == 0
    assert out.read_bytes() == (tmp_path / "r2" / "synthv1" / out.name).read_bytes()
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert (
        doc["input"]["observations_sha256"]
        == hashlib.sha256((d / "observations.jsonl").read_bytes()).hexdigest()
    )
    assert len(doc["input"]["station_master_sha256"]) == 64
    assert doc["series"][0]["station"]["jps_internal_id"] == "9"
    assert go("r1") == 0  # identical rerun: no-op
    out.write_bytes(b"{}")
    assert go("r1") == 2  # existing output differs: refused
    (master / "sensors.csv").write_text(
        "fg_sensor_id,fg_site_id,sensor_type,jps_internal_id\nS1,site-S1,WATER_LEVEL,8\n", "utf-8"
    )
    assert go("r3") == 2  # a station master other than the dataset's: refused
    assert not (tmp_path / "r3").exists()
    (d / "observations.jsonl").write_bytes(b"{}\n")
    assert go("r4", tmp_path / "none") == 2  # tampered input: refused
    assert main(["--dataset", str(tmp_path / "missing")]) == 2


# --- review regressions ---------------------------------------------------------------------


def test_duplicate_conflict_wins_over_member_marker() -> None:
    # Regression: a conflict row carries the union of its captures' flags, so a -9999 capture
    # conflicting with a numeric one was counted as SENTINEL_-9999 and the conflict vanished.
    rows = series([1.0, M9999, 1.0])
    rows[1]["quality_flags"] = sorted([*rows[1]["quality_flags"], "DUPLICATE_CONFLICT"])
    w = win(rows)
    assert w["missing_by_type"]["DUPLICATE_CONFLICT"] == 1
    assert w["missing_by_type"]["SENTINEL_-9999"] == 0
    assert w["missing_flags"]["VALUE_MISSING_SENTINEL"] == 1  # member marker still visible


def test_non_numeric_marker() -> None:
    rows = series([1.0, M9999])
    rows[1]["quality_flags"] = ["TIMEZONE_ASSUMED", "VALUE_NON_NUMERIC"]
    assert win(rows)["missing_by_type"]["NON_NUMERIC"] == 1


def test_listing_only_row_inside_window_is_not_an_absent_slot() -> None:
    # Regression: a slot holding a listing-only canonical row was labelled ABSENT_SLOT.
    rows = [
        row(0, 1.0),
        row(5, 2.0, dataset="water_level_listing", batch="L"),
        row(10, 1.0),
    ]
    s = only(run(rows))
    w = s["cadence_windows"][0]
    assert (w["absent_slots"], w["missing_by_type"]["LISTING_ONLY_SLOT"]) == (0, 1)
    assert w["listing_only_rows_in_window"] == 1
    assert s["point_in_time"]["rows"] == 1


def test_nested_overlapping_captures_merge() -> None:
    outer = [row(0, 1.0, batch="A"), row(50, 1.0, batch="A")]
    inner = [row(10, M9999, batch="B"), row(20, 1.0, batch="B")]
    w = win(outer + inner)
    assert (w["expected_slots"], w["absent_slots"], w["source_rows"]) == (11, 7, 4)
    assert w["ingestion_batch_ids"] == ["A", "B"]


def test_merged_history_listing_row_with_real_provenance_keys() -> None:
    rows = series([1.0, 1.0, 1.0])
    rows[1]["datasets"] = ["water_level_history", "water_level_listing"]
    rows[1]["provenance"] = [
        {
            "dataset": d,
            "ingestion_batch_id": b,
            "payload_sha256": "0" * 64,
            "retrieved_at": "2030-01-01T00:10:00+00:00",
            "source_field": "final",
            "source_row_index": 1,
            "value_signature": "NUMERIC:1.0",
        }
        for d, b in (("water_level_history", "B1"), ("water_level_listing", "L"))
    ]
    s = only(run(rows))
    assert (s["history_rows"], s["point_in_time_rows"]) == (3, 0)
    assert s["cadence_windows"][0]["ingestion_batch_ids"] == ["B1"]


def test_quality_summary_must_cover_every_series() -> None:
    rows = series([1.0], sensor="S1") + series([1.0], sensor="S2")
    only_s1 = {"series": {"S1/WATER_LEVEL": {"rows": 1, "usable": 1}}}
    with pytest.raises(AnalysisContractError, match="no quality-summary entry"):
        run(rows, quality_summary=only_s1)
    other = {"canonical": {"rows_by_measurement_type": {"WATER_LEVEL": 5}}}
    with pytest.raises(AnalysisContractError, match="row counts"):
        run(rows, quality_summary=other)


def test_sensor_comparison_uses_best_pair() -> None:
    # Regression: the overlap was intersected over all eligible sensors, so one sensor with
    # other days hid two sensors sharing enough full days.
    day = 288
    a = series([1.0] * (2 * day + 1), sensor="A")
    b = series([1.0] * (2 * day + 1), sensor="B")
    c = series([1.0] * (2 * day + 1), sensor="C", start=START + timedelta(days=10))
    cfg = MissingnessConfig(min_full_days_comparison=2)
    suf = run(a + b + c, cfg)["sufficiency"]["WATER_LEVEL"]["sensor_comparison"]
    assert suf["status"] == SUFFICIENT
    assert suf["observed"]["max_pairwise_shared_full_days"] == 2


def test_station_master_lineage_statement() -> None:
    doc = run(series([1.0]), station_master_sha256="s" * 64)
    assert "sites.csv" in doc["input"]["station_master_lineage"]
    assert run(series([1.0]))["input"]["station_master_lineage"] is None
