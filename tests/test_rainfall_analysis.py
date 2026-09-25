"""Offline tests for the rainfall-distribution analysis (Phase 3).

Every rainfall series here is SYNTHETIC (year 2030, invented sensor IDs); none is evidence about
Penang rainfall.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import random
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from floodguard.analysis.rainfall import (
    INSUFFICIENT,
    INSUFFICIENT_SAMPLE,
    NETWORK_HISTORICAL,
    SCHEMA_VERSION,
    STATION_WINDOW_DESCRIPTIVE,
    SUFFICIENT,
    RainfallAnalysisConfig,
    RainfallContractError,
    analyze,
    assess_sufficiency,
    covered_days,
    load_processed_dataset,
    to_json_bytes,
    write_summary,
)

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
MYT = timezone(timedelta(hours=8))
START = datetime(2030, 1, 1, 0, 5, tzinfo=MYT)  # first interval: 00:00-00:05 local
CFG = RainfallAnalysisConfig()
Row = dict[str, Any]


def row(
    i: int,
    value: float | None,
    *,
    sensor: str = "S1",
    start: datetime = START,
    measurement_type: str = "RAINFALL_INTERVAL",
    unit: str = "mm",
    sensor_type: str = "RAINFALL",
) -> Row:
    """SYNTHETIC canonical row; ``value=None`` is a ``-9999`` marker (not usable)."""
    local = start + timedelta(minutes=5 * i)
    flags = ["TIMEZONE_ASSUMED"] + ([] if value is not None else ["VALUE_MISSING_SENTINEL"])
    return {
        "observation_schema_version": "observations/v1",
        "source": "JPS_PUBLIC_INFOBANJIR",
        "fg_sensor_id": sensor,
        "fg_site_id": f"site-{sensor}",
        "sensor_type": sensor_type,
        "measurement_type": measurement_type,
        "observation_time_local": local.isoformat(),
        "observation_time_utc": local.astimezone(UTC).isoformat(),
        "value": value,
        "unit": unit,
        "quality_flags": sorted(flags),
        "usable": value is not None,
    }


def series(values: Sequence[float | None], **kw: Any) -> list[Row]:
    return [row(i, v, **kw) for i, v in enumerate(values)]


def station(rows: Sequence[Row], config: RainfallAnalysisConfig = CFG) -> dict[str, Any]:
    doc = analyze(rows, dataset_version="synthetic0000001", config=config)
    assert len(doc["stations"]) == 1
    result: dict[str, Any] = doc["stations"][0]
    return result


def q(summary: dict[str, Any], label: str) -> dict[str, Any]:
    result: dict[str, Any] = summary["quantiles_mm"][label]
    return result


MIXED = [0.0] * 90 + [0.5] * 6 + [1.0] * 3 + [2.0]  # n=100, 10 wet, total 8 mm


# --- statistics ---------------------------------------------------------------------------


def test_all_zero_period() -> None:
    s = station(series([0.0] * 288))
    assert s["occurrence"] == {
        "zero_count": 288,
        "zero_proportion": 1.0,
        "wet_count": 0,
        "wet_proportion": 0.0,
        "nonzero_below_wet_threshold_count": 0,
    }
    assert s["all_intervals"]["total_mm"] == 0.0
    assert s["all_intervals"]["skewness"]["status"] == "UNDEFINED_ZERO_VARIANCE"
    assert s["wet_only"] == {"count": 0, "status": "NO_DATA"}
    assert s["concentration"] is None


def test_mixed_dry_wet_intervals() -> None:
    s = station(series(MIXED))
    a, w = s["all_intervals"], s["wet_only"]
    assert s["occurrence"]["wet_count"] == 10
    assert s["occurrence"]["wet_proportion"] == 0.1
    assert s["occurrence"]["zero_proportion"] == 0.9
    assert (a["count"], a["total_mm"], a["mean_mm"]) == (100, 8.0, 0.08)
    assert a["median_mm"] == {"status": "OK", "value": 0.0}
    assert (a["min_mm"], a["max_mm"]) == (0.0, 2.0)
    assert q(a, "p50") == {"status": "OK", "value": 0.0}
    assert q(a, "p90") == {"status": "OK", "value": 0.05}  # linear between a[89]=0, a[90]=0.5
    assert q(a, "p95") == {"status": "OK", "value": 0.5}
    assert q(a, "p99") == {"status": INSUFFICIENT_SAMPLE, "n": 100, "required_n": 500}
    assert (w["count"], w["mean_mm"], w["max_mm"]) == (10, 0.8, 2.0)
    assert w["median_mm"] == {"status": "OK", "value": 0.5}
    assert s["concentration"] == {
        "largest_interval_share_of_total": 0.25,
        "intervals_for_half_of_total": 3,  # 2 + 1 + 1 = 4 mm = half of 8
        "share_of_usable_intervals_for_half_of_total": 0.03,
    }


def test_wet_only_data() -> None:
    s = station(series([0.5, 1.0, 1.5] * 10))
    assert s["occurrence"]["zero_proportion"] == 0.0
    assert s["occurrence"]["wet_proportion"] == 1.0
    assert s["wet_only"]["count"] == s["all_intervals"]["count"] == 30


def test_missing_and_excluded_input_never_counts_as_zero() -> None:
    rows = series([0.0, None, 1.0, None, 0.0])
    s = station(rows)
    assert s["coverage"]["usable_intervals"] == 3
    assert s["coverage"]["not_usable_intervals"] == 2
    assert s["coverage"]["not_usable_flags"] == {"TIMEZONE_ASSUMED": 2, "VALUE_MISSING_SENTINEL": 2}
    assert s["occurrence"]["zero_count"] == 2
    assert s["all_intervals"]["count"] == 3


def test_one_very_large_value() -> None:
    s = station(series([0.0] * 99 + [150.0]))
    a = s["all_intervals"]
    assert (a["max_mm"], a["total_mm"], a["mean_mm"]) == (150.0, 150.0, 1.5)
    assert a["skewness"] == {"status": "OK", "value": 10.0}  # G1 of one spike in n=100
    assert s["concentration"] == {"status": INSUFFICIENT_SAMPLE, "n": 1, "required_n": 10}
    assert q(a, "p99")["status"] == INSUFFICIENT_SAMPLE


def test_wet_threshold_is_configurable() -> None:
    s = station(series([0.0, 0.2, 0.5, 1.0]), RainfallAnalysisConfig(wet_threshold_mm=0.5))
    assert s["occurrence"]["wet_count"] == 1  # strictly greater than the threshold
    assert s["occurrence"]["nonzero_below_wet_threshold_count"] == 2


def test_insufficient_wet_samples_are_explicit() -> None:
    doc = analyze(series([0.0] * 50 + [1.0, 2.0, 3.0]), dataset_version="v")
    w = doc["stations"][0]["wet_only"]
    assert w["count"] == 3
    assert w["median_mm"] == {"status": INSUFFICIENT_SAMPLE, "n": 3, "required_n": 10}
    assert q(w, "p50") == {"status": INSUFFICIENT_SAMPLE, "n": 3, "required_n": 10}
    assert w["skewness"] == {"status": INSUFFICIENT_SAMPLE, "n": 3, "required_n": 30}
    assert doc["sufficiency"]["wet_only_statistics"]["status"] == INSUFFICIENT
    assert doc["sufficiency"]["wet_only_quantiles"]["observed"]["estimable_quantiles"] == []


def test_single_value_has_no_standard_deviation() -> None:
    a = station(series([1.0]))["all_intervals"]
    assert a["std_mm"] == {"status": INSUFFICIENT_SAMPLE, "n": 1, "required_n": 2}


def test_quantile_sample_rule() -> None:
    assert [CFG.required_n(x) for x in CFG.quantiles] == [10, 20, 50, 100, 500]


@pytest.mark.parametrize(
    "kw",
    [
        {"quantiles": (0.9, 0.5)},
        {"quantiles": (0.0, 0.5)},
        {"quantiles": ()},
        {"wet_threshold_mm": -0.1},
        {"min_day_coverage": 0.0},
        {"min_tail_count": 0},
        {"min_samples_skewness": 2},
    ],
)
def test_invalid_config_rejected(kw: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="must be"):
        RainfallAnalysisConfig(**kw)


# --- stations, determinism, provenance ------------------------------------------------------


def test_multiple_stations_keep_identity() -> None:
    rows = series([0.0] * 40, sensor="B") + series([1.0] * 40, sensor="A")
    doc = analyze(rows, dataset_version="v")
    assert [s["fg_sensor_id"] for s in doc["stations"]] == ["A", "B"]
    assert [s["all_intervals"]["total_mm"] for s in doc["stations"]] == [40.0, 0.0]
    assert doc["network"]["stations_analysed"] == 2
    assert doc["sufficiency"]["station_comparison"]["status"] == INSUFFICIENT  # < 30 days shared


def test_station_comparison_needs_shared_covered_days() -> None:
    day = 288
    rows = series([0.0] * day * 30, sensor="A") + series([0.5] * day * 30, sensor="B")
    doc = analyze(rows, dataset_version="v")
    comp = doc["sufficiency"]["station_comparison"]
    assert comp["status"] == SUFFICIENT
    assert comp["observed"]["max_shared_covered_days"] == 30
    shifted = series([0.5] * day * 30, sensor="B", start=START + timedelta(days=1))
    doc = analyze(series([0.0] * day * 30, sensor="A") + shifted, dataset_version="v")
    assert doc["sufficiency"]["station_comparison"]["status"] == INSUFFICIENT


def test_output_is_deterministic_and_order_independent() -> None:
    rows = series(MIXED, sensor="A") + series(list(reversed(MIXED)), sensor="B")
    first = to_json_bytes(analyze(rows, dataset_version="v"))
    shuffled = rows[:]
    random.Random(7).shuffle(shuffled)
    assert to_json_bytes(analyze(shuffled, dataset_version="v")) == first
    assert to_json_bytes(analyze(rows, dataset_version="v")) == first


def test_dataset_version_propagates(tmp_path: Path) -> None:
    doc = analyze(series(MIXED), dataset_version="abc123", observations_sha256="f" * 64)
    assert doc["dataset_version"] == "abc123"
    assert doc["analysis_schema_version"] == SCHEMA_VERSION
    assert doc["input"]["observations_sha256"] == "f" * 64
    path, written = write_summary(doc, tmp_path)
    assert written
    assert path == tmp_path / "abc123" / "rainfall_distribution.json"
    assert json.loads(path.read_text(encoding="utf-8"))["dataset_version"] == "abc123"
    assert write_summary(doc, tmp_path) == (path, False)  # identical rerun: no-op
    with pytest.raises(OSError, match="different content"):
        write_summary({**doc, "scope": "changed"}, tmp_path)
    with pytest.raises(RainfallContractError):
        analyze(series(MIXED), dataset_version="")


def test_quality_summary_cadence_and_station_metadata_are_carried() -> None:
    summary = {
        "series": {
            "S1/RAINFALL_INTERVAL": {
                "history_cadence": {
                    "expected_slots": 10,
                    "absent_slots": 2,
                    "history_rows_not_in_canonical": 0,
                }
            }
        }
    }
    meta = {"S1": {"sensor_type": "RAINFALL", "district": "D", "main_basin": "B"}}
    doc = analyze(
        series([0.0] * 8), dataset_version="v", quality_summary=summary, station_metadata=meta
    )
    s = doc["stations"][0]
    assert s["coverage"]["history_absent_slots"] == 2
    assert s["coverage"]["history_expected_slots"] == 10
    assert s["station"]["district"] == "D"
    assert doc["network"]["rainfall_sensors_in_station_master"] == 1


# --- input contract and regression guards ---------------------------------------------------


def test_water_level_and_other_rainfall_fields_never_enter() -> None:
    rainfall = series(MIXED)
    others = series(
        [5.0] * 100, measurement_type="WATER_LEVEL", unit="m", sensor_type="WATER_LEVEL"
    ) + series([99.0] * 100, measurement_type="RAINFALL_1H_TOTAL")
    alone = analyze(rainfall, dataset_version="v")
    mixed = analyze(rainfall + others, dataset_version="v")
    assert mixed["stations"] == alone["stations"]
    assert mixed["input"]["excluded_rows_by_measurement_type"] == {
        "RAINFALL_1H_TOTAL": 100,
        "WATER_LEVEL": 100,
    }
    assert mixed["input"]["rainfall_interval_rows"] == 100


@pytest.mark.parametrize(
    ("edit", "match"),
    [
        ({"unit": "m"}, "unit"),
        ({"unit": None}, "unit"),
        ({"sensor_type": "WATER_LEVEL"}, "sensor type"),
        ({"measurement_type": "RAINFALL_CLEAN"}, "unknown measurement type"),
        ({"measurement_type": "cyearly"}, "unknown measurement type"),
        ({"observation_schema_version": "observations/v0"}, "observations/v1"),
        ({"value": -1.0}, "invalid"),
        ({"value": None}, "invalid"),
        ({"value": float("nan")}, "invalid"),
        ({"value": True}, "invalid"),
        ({"usable": "yes"}, "boolean"),
        ({"fg_sensor_id": None}, "identity"),
        ({"observation_time_utc": "2030-01-01T00:00:00"}, "tz-aware"),
    ],
)
def test_malformed_rows_rejected(edit: dict[str, Any], match: str) -> None:
    rows = series([0.0, 1.0])
    rows[1].update(edit)
    with pytest.raises(RainfallContractError, match=match):
        analyze(rows, dataset_version="v")


def test_repeated_canonical_key_rejected() -> None:
    rows = series([0.0, 1.0])
    with pytest.raises(RainfallContractError, match="repeated"):
        analyze([*rows, dict(rows[1])], dataset_version="v")


# --- sufficiency ----------------------------------------------------------------------------


def test_one_day_window_supports_descriptive_only() -> None:
    doc = analyze(series([0.0] * 280 + [0.5] * 9), dataset_version="v")
    status = {k: v["status"] for k, v in doc["sufficiency"].items()}
    assert status == {
        "basic_descriptive": SUFFICIENT,
        "wet_only_statistics": INSUFFICIENT,
        "wet_only_quantiles": INSUFFICIENT,
        "station_comparison": INSUFFICIENT,
        "seasonal_analysis": INSUFFICIENT,
        "monsoon_comparison": INSUFFICIENT,
        "extreme_event_analysis": INSUFFICIENT,
    }
    assert STATION_WINDOW_DESCRIPTIVE in doc["evidence_levels_supported"]
    assert NETWORK_HISTORICAL not in doc["evidence_levels_supported"]


def _summary(sid: str, months: dict[str, int], years: int) -> dict[str, Any]:
    return {
        "fg_sensor_id": sid,
        "coverage": {"usable_intervals": 10**6},
        "occurrence": {"wet_count": 10**5},
        "calendar": {
            "covered_days": 60,
            "complete_months_by_calendar_month": months,
            "complete_years": years,
        },
    }


def test_long_history_rules() -> None:
    full = {f"{m:02d}": 2 for m in range(1, 13)}
    days = {f"S{i}": {date(2030, 1, 1) + timedelta(days=d) for d in range(60)} for i in (1, 2)}
    stations = [_summary("S1", full, 20), _summary("S2", {**full, "07": 1}, 1)]
    got = assess_sufficiency(stations, days, CFG)
    assert all(
        got[k]["status"] == SUFFICIENT
        for k in ("seasonal_analysis", "station_comparison", "extreme_event_analysis")
    )
    assert got["wet_only_quantiles"]["status"] == SUFFICIENT
    assert got["monsoon_comparison"]["status"] == INSUFFICIENT  # no verified season boundaries
    cfg = RainfallAnalysisConfig(monsoon_definition_source="METMalaysia (verified)")
    assert assess_sufficiency(stations, days, cfg)["monsoon_comparison"]["status"] == SUFFICIENT
    short = [_summary("S1", {**full, "07": 1}, 19)]
    got = assess_sufficiency(short, days, CFG)
    assert got["seasonal_analysis"]["status"] == INSUFFICIENT
    assert got["extreme_event_analysis"]["status"] == INSUFFICIENT


def test_covered_day_uses_interval_start_and_coverage_share() -> None:
    # 00:05..24:00 is one full local day; the 00:00 value belongs to the previous day.
    day = series([0.0] * 289, start=START - timedelta(minutes=5))
    assert covered_days(day, CFG) == {date(2030, 1, 1)}
    assert covered_days(day[:231], CFG) == set()  # 230 intervals of 2030-01-01 < 80% of 288
    assert covered_days(day[:232], CFG) == {date(2030, 1, 1)}  # 231 >= ceil(230.4)


# --- processed-dataset contract and the one-shot script -------------------------------------


def _dataset(
    root: Path, rows: list[Row], version: str = "synthv1", *, origin: str | None = None
) -> Path:
    d = root / version
    d.mkdir(parents=True)
    data = "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode("utf-8")
    (d / "observations.jsonl").write_bytes(data)
    (d / "quality_summary.json").write_text(
        json.dumps({"summary_schema_version": "quality_summary/v1", "series": {}}),
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


def test_load_processed_dataset_contract(tmp_path: Path) -> None:
    d = _dataset(tmp_path, series(MIXED))
    ds = load_processed_dataset(d / "dataset_manifest.json")
    assert (ds.dataset_version, len(ds.rows)) == ("synthv1", 100)
    (d / "observations.jsonl").write_bytes(b"{}\n")
    with pytest.raises(RainfallContractError, match="hash"):
        load_processed_dataset(d)
    renamed = _dataset(tmp_path / "x", series(MIXED)).rename(tmp_path / "x" / "other")
    with pytest.raises(RainfallContractError, match="directory"):
        load_processed_dataset(renamed)
    bad = _dataset(tmp_path / "y", series(MIXED))
    manifest = json.loads((bad / "dataset_manifest.json").read_text(encoding="utf-8"))
    manifest["checks"][0]["passed"] = False
    (bad / "dataset_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RainfallContractError, match="checks"):
        load_processed_dataset(bad)


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "analyze_rainfall", ROOT / "scripts" / "analyze_rainfall.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_script_runs_offline_and_is_byte_identical(tmp_path: Path) -> None:
    d = _dataset(tmp_path / "processed", series(MIXED) + series([0.0] * 50, sensor="S2"))
    main = _script().main

    def run(name: str) -> int:
        out = str(tmp_path / name)
        no_master = str(tmp_path / "no_master")
        result: int = main(
            ["--dataset", str(d), "--output-root", out, "--station-master-dir", no_master]
        )
        return result

    output = tmp_path / "run1" / "synthv1" / "rainfall_distribution.json"
    assert run("run1") == 0
    assert run("run2") == 0
    assert (
        output.read_bytes()
        == (tmp_path / "run2" / output.relative_to(tmp_path / "run1")).read_bytes()
    )
    assert run("run1") == 0  # identical rerun: no-op
    output.write_bytes(b"{}")
    assert run("run1") == 2  # existing output differs: refused
    assert main(["--dataset", str(tmp_path / "missing")]) == 2


def test_local_time_must_be_kuala_lumpur_offset() -> None:
    rows = series([0.0, 1.0])
    utc = datetime.fromisoformat(rows[1]["observation_time_utc"])
    rows[1]["observation_time_local"] = utc.astimezone(timezone(timedelta(hours=7))).isoformat()
    with pytest.raises(RainfallContractError, match="policy zone"):
        analyze(rows, dataset_version="v")


def test_station_master_hash_recorded(tmp_path: Path) -> None:
    master = tmp_path / "master"
    master.mkdir()
    (master / "sensors.csv").write_text(
        "fg_sensor_id,fg_site_id,sensor_type,jps_internal_id\nS1,site-S1,RAINFALL,1\n",
        encoding="utf-8",
    )
    (master / "sites.csv").write_text(
        "fg_site_id,district,main_basin\nsite-S1,D,B\n", encoding="utf-8"
    )
    digest = hashlib.sha256((master / "sensors.csv").read_bytes()).hexdigest()
    d = _dataset(tmp_path / "processed", series(MIXED), origin=f"sensors.csv@sha256:{digest[:16]}")
    out = tmp_path / "out"
    args = ["--dataset", str(d), "--output-root", str(out), "--station-master-dir", str(master)]
    assert _script().main(args) == 0
    doc = json.loads((out / "synthv1" / "rainfall_distribution.json").read_text(encoding="utf-8"))
    assert len(doc["input"]["station_master_sha256"]) == 64
    assert doc["stations"][0]["station"]["district"] == "D"
    (master / "sites.csv").write_text("fg_site_id,district,main_basin\nsite-S1,X,B\n", "utf-8")
    assert _script().main(args) == 2  # changed master, same dataset version: refused


def test_script_refuses_other_station_master(tmp_path: Path) -> None:
    # Regression: the rainfall script loaded any local station master without checking it was
    # the one the dataset was built with (now enforced by the shared loader for every analysis).
    master = tmp_path / "master"
    master.mkdir()
    (master / "sensors.csv").write_text(
        "fg_sensor_id,fg_site_id,sensor_type,jps_internal_id\nS1,site-S1,RAINFALL,1\n", "utf-8"
    )
    (master / "sites.csv").write_text("fg_site_id,district,main_basin\nsite-S1,D,B\n", "utf-8")
    d = _dataset(tmp_path / "p", series(MIXED), origin="sensors.csv@sha256:0000000000000000")
    args = ["--dataset", str(d), "--output-root", str(tmp_path / "o")]
    assert _script().main([*args, "--station-master-dir", str(master)]) == 2
    assert not (tmp_path / "o").exists()
    assert _script().main([*args, "--station-master-dir", str(tmp_path / "none")]) == 0
