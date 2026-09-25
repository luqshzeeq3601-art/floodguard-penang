"""Offline end-to-end tests: raw -> component layers -> validated -> processed (Phase 2 pipeline).

Payloads are the trimmed REAL fixtures in tests/fixtures/jps and tests/fixtures/metmalaysia.
Payloads edited here (``edited_history``: overlapping, conflicting or gapped history windows) and
the station master from ``make_sensors_csv`` are SYNTHETIC.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from floodguard.ingestion.adapters.data_gov_my import WeatherForecastAdapter
from floodguard.ingestion.adapters.jps import (
    RAINFALL_LISTING,
    WATER_LEVEL_LISTING,
    history_adapter,
)
from floodguard.ingestion.contracts import Adapter, BatchStatus
from floodguard.ingestion.pipeline import ingest_batch
from floodguard.ingestion.station_mapping import SensorMapper
from floodguard.station_master import SensorType

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
JPS = ROOT / "tests" / "fixtures" / "jps"
FORECAST = ROOT / "tests/fixtures/metmalaysia/weather_forecast_trimmed_20260924T112926+0800.json"
MYT = timezone(timedelta(hours=8))
AT = datetime(2026, 9, 24, 8, 0, tzinfo=MYT)
RF, WL = SensorType.RAINFALL, SensorType.WATER_LEVEL
WL_26460 = "history_water_level_26460_20260923_trimmed.json"
Batch = tuple[Adapter, bytes, datetime]


def _module(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def edited_history(
    name: str, edit: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
) -> bytes:
    """SYNTHETIC: a real history fixture with its ``values`` list edited."""
    doc = json.loads((JPS / name).read_text(encoding="utf-8"))
    doc["values"] = edit(doc["values"])
    doc["info"]["count"] = len(doc["values"])
    return json.dumps(doc).encode("utf-8")


def base_batches() -> list[Batch]:
    def hist(sensor: SensorType, sid: str, name: str) -> Batch:
        return (
            history_adapter(sensor, sid, f"https://example.invalid/{sid}"),
            (JPS / name).read_bytes(),
            AT,
        )

    return [
        (RAINFALL_LISTING, (JPS / "searchresultrainfall_PNG_trimmed.html").read_bytes(), AT),
        (WATER_LEVEL_LISTING, (JPS / "aras_air_data_PNG_trimmed.html").read_bytes(), AT),
        hist(RF, "27608", "history_rainfall_27608_20260918_trimmed.json"),
        hist(WL, "27608", "history_water_level_27608_20240924_trimmed.json"),
        hist(WL, "26460", WL_26460),
        hist(RF, "27608", "history_no_result.txt"),
        (WeatherForecastAdapter(), FORECAST.read_bytes(), AT),
    ]


@pytest.fixture
def master(make_sensors_csv: Callable[..., Path]) -> Path:
    return make_sensors_csv([("27608", RF), ("27608", WL), ("26460", WL)])


def ingest(raw: Path, master: Path, batches: list[Batch]) -> None:
    mapper = SensorMapper.from_csv(master)
    for adapter, payload, at in batches:
        rep = ingest_batch(
            payload,
            adapter,
            source_reference="https://example.invalid/x",
            retrieved_at=at,
            raw_root=raw,
            mapper=None if isinstance(adapter, WeatherForecastAdapter) else mapper,
        )
        assert rep.status is BatchStatus.SUCCEEDED


def build(tmp: Path, master: Path, raw: Path, tag: str = "") -> tuple[int, Path]:
    out = tmp / f"out{tag}"
    code: int = _module("build_historical_dataset").main(
        [
            "--raw-root",
            str(raw),
            "--interim-root",
            str(out / "interim"),
            "--processed-root",
            str(out / "processed"),
            "--station-master",
            str(master),
        ]
    )
    return code, out


def run_ok(
    tmp: Path, master: Path, raw: Path, capsys: pytest.CaptureFixture[str], tag: str = ""
) -> tuple[dict[str, Any], Path]:
    code, out = build(tmp, master, raw, tag)
    captured = capsys.readouterr()
    assert code == 0, captured.err
    report: dict[str, Any] = json.loads(captured.out)
    return report, out / "processed" / report["output_dir"]


def observations(out_dir: Path) -> list[dict[str, Any]]:
    text = (out_dir / "observations.jsonl").read_text(encoding="utf-8")
    return [json.loads(x) for x in text.splitlines()]


def hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


# ---------------------------------------------------------------- end to end


def test_end_to_end_layers_versioned_and_raw_untouched(
    tmp_path: Path, master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    ingest(raw, master, base_batches())
    before = hashes(raw)
    report, out_dir = run_ok(tmp_path, master, raw, capsys)
    assert hashes(raw) == before  # raw store only read

    interim = tmp_path / "out" / "interim"
    for layer in ("timestamps/v1", "station_ids/v1", "units/v1", "quality/v1"):
        assert list((interim / layer).rglob("*.jsonl")), layer
    assert sorted(p.name for p in out_dir.iterdir()) == [
        "dataset_manifest.json",
        "observations.jsonl",
        "quality_summary.json",
    ]
    manifest = json.loads((out_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_version"] == report["dataset_version"]
    assert "PERMISSION REQUIRED" in manifest["licence"]
    assert "ASSUMED" in manifest["timezone_interpretation"]
    assert all(c["passed"] for c in manifest["checks"])
    assert len(manifest["inputs"]) == 7
    obs_bytes = (out_dir / "observations.jsonl").read_bytes()
    assert manifest["observations_sha256"] == hashlib.sha256(obs_bytes).hexdigest()

    obs = observations(out_dir)
    assert {o["measurement_type"] for o in obs} == {
        "RAINFALL_INTERVAL",
        "RAINFALL_1H_TOTAL",
        "WATER_LEVEL",
    }
    assert report["excluded_quality_rows"]["NOT_A_STATION_OBSERVATION"] == {
        "weather_forecast": 63  # 21 forecast records x (summary text, min, max)
    }
    assert "NO_CANONICAL_SENSOR" in report["excluded_quality_rows"]  # quarantined listing rows
    # markers stay as rows with a null value; zero rainfall stays a usable 0.0
    sentinel = [o for o in obs if "VALUE_MISSING_SENTINEL" in o["quality_flags"]]
    assert sentinel
    assert all(o["value"] is None and o["value_raw"] == "-9999" for o in sentinel)
    zeros = [o for o in obs if o["measurement_type"] == "RAINFALL_INTERVAL" and o["value"] == 0.0]
    assert zeros
    assert all(o["usable"] for o in zeros)
    for o in obs:
        assert o["provenance"]
        assert o["fg_sensor_id"]
        assert o["timezone_status"] == "UNSPECIFIED_ASSUMED"


def test_rerun_is_noop_and_output_is_deterministic(
    tmp_path: Path, master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    ingest(raw, master, base_batches())
    first, out1 = run_ok(tmp_path, master, raw, capsys, "1")
    again, _ = run_ok(tmp_path, master, raw, capsys, "1")
    assert again["files_written"] == 0
    other, out2 = run_ok(tmp_path, master, raw, capsys, "2")
    assert other["dataset_version"] == first["dataset_version"]
    assert hashes(out1) == hashes(out2)


def test_dataset_version_ignores_ingestion_order(
    tmp_path: Path, master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = tmp_path / "rawA", tmp_path / "rawB"
    ingest(a, master, base_batches())
    ingest(b, master, list(reversed(base_batches())))
    ra, out_a = run_ok(tmp_path, master, a, capsys, "A")
    rb, out_b = run_ok(tmp_path, master, b, capsys, "B")
    assert ra["dataset_version"] == rb["dataset_version"]
    assert (out_a / "observations.jsonl").read_bytes() == (
        out_b / "observations.jsonl"
    ).read_bytes()


def test_component_outputs_equal_the_per_layer_scripts(
    tmp_path: Path, master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    ingest(raw, master, base_batches())
    run_ok(tmp_path, master, raw, capsys)
    interim = tmp_path / "out" / "interim"
    before = hashes(interim)
    for records in sorted(raw.rglob("*.records.jsonl")):
        for script, layer in (
            ("normalize_timestamps", "timestamps/v1"),
            ("validate_units", "units/v1"),
        ):
            argv = ["--records", str(records), "--raw-root", str(raw)]
            code = _module(script).main([*argv, "--out-root", str(interim / layer)])
            assert code == 0, capsys.readouterr().err  # identical bytes: write-once no-op
    assert hashes(interim) == before


# ---------------------------------------------------------------- duplicates


def _later(minutes: int) -> datetime:
    return AT + timedelta(minutes=minutes)


def test_overlapping_identical_history_collapses_with_full_provenance(
    tmp_path: Path, master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    overlap = edited_history(WL_26460, lambda v: v[3:8])  # SYNTHETIC sub-window, same values
    ingest(raw, master, [*base_batches(), (history_adapter(WL, "26460", "u"), overlap, _later(5))])
    _, out_dir = run_ok(tmp_path, master, raw, capsys)
    dup = [o for o in observations(out_dir) if o["duplicate_status"] == "IDENTICAL"]
    assert len(dup) >= 5
    for o in dup:
        assert o["duplicate_count"] == len(o["provenance"]) >= 2
        assert "DUPLICATE_IDENTICAL" in o["quality_flags"]
        assert o["first_retrieved_at"] == AT.astimezone(UTC).isoformat()
        assert o["conflict_reason"] is None


@pytest.mark.parametrize(
    ("new_value", "reason"),
    [("0.99", "NUMERIC_VALUES_DIFFER"), ("-9999", "MARKER_VS_NUMERIC")],
)
def test_conflicting_values_are_never_resolved(
    tmp_path: Path,
    master: Path,
    capsys: pytest.CaptureFixture[str],
    new_value: str,
    reason: str,
) -> None:
    def edit(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        row = next(v for v in values if v["dt"] == "23/09/2026 12:30")  # real value 0.21
        row["final"] = new_value  # SYNTHETIC
        return values

    raw = tmp_path / "raw"
    conflicting = edited_history(WL_26460, edit)
    ingest(
        raw, master, [*base_batches(), (history_adapter(WL, "26460", "u"), conflicting, _later(5))]
    )
    report, out_dir = run_ok(tmp_path, master, raw, capsys)
    [c] = [o for o in observations(out_dir) if o["duplicate_status"] == "CONFLICT"]
    assert c["observation_time_local"] == "2026-09-23T12:30:00+08:00"
    assert c["value"] is None
    assert c["value_raw"] is None
    assert c["usable"] is False
    assert c["conflict_reason"] == reason
    assert "DUPLICATE_CONFLICT" in c["quality_flags"]
    assert "NUMERIC:0.21" in c["conflicting_values"]
    assert len(c["conflicting_values"]) == 2
    assert report["duplicate_status"]["CONFLICT"] == 1
    # what each capture said stays recoverable for as-of use (regression, review)
    said = {p["retrieved_at"]: p["value_signature"] for p in c["provenance"]}
    assert said[AT.astimezone(UTC).isoformat()] == "NUMERIC:0.21"


# ---------------------------------------------------------------- temporal safety


def test_future_rows_are_kept_out_and_nothing_is_filled(
    tmp_path: Path, master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    early = datetime(2026, 9, 23, 12, 10, tzinfo=MYT)  # capture before most of the window
    ingest(raw, master, [(history_adapter(WL, "26460", "u"), (JPS / WL_26460).read_bytes(), early)])
    report, out_dir = run_ok(tmp_path, master, raw, capsys)
    obs = observations(out_dir)
    assert report["excluded_quality_rows"]["NO_VALID_OBSERVATION_TIME"] == {
        "water_level_history": 5  # 12:25..12:45 are later than 12:10 + 10 min
    }
    assert [o["observation_time_local"][11:16] for o in obs] == [
        "12:00",
        "12:05",
        "12:10",
        "12:15",
        "12:20",
    ]
    assert all(o["value"] is None for o in obs)  # -9999 slots: no later reading back-filled
    summary = json.loads((out_dir / "quality_summary.json").read_text(encoding="utf-8"))
    [series] = summary["series"].values()
    # regression (review): excluded rows exist, so they are not absent slots
    assert series["history_cadence"]["absent_slots"] == 0
    assert series["history_cadence"]["history_rows_not_in_canonical"] == 5


def test_absent_rows_are_measured_not_invented(
    tmp_path: Path, master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    gapped = edited_history(WL_26460, lambda v: v[:6] + v[8:])  # SYNTHETIC: drop 12:30, 12:35
    ingest(raw, master, [(history_adapter(WL, "26460", "u"), gapped, AT)])
    _, out_dir = run_ok(tmp_path, master, raw, capsys)
    obs = observations(out_dir)
    assert len(obs) == 8
    summary = json.loads((out_dir / "quality_summary.json").read_text(encoding="utf-8"))
    [series] = summary["series"].values()
    assert series["history_cadence"]["absent_slots"] == 2
    assert series["history_cadence"]["largest_gap_minutes"] == 15


# ---------------------------------------------------------------- rejections


def test_tampered_raw_file_is_rejected_before_any_output(
    tmp_path: Path, master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    ingest(raw, master, base_batches())
    records = next(p for p in raw.rglob("*.records.jsonl") if p.stat().st_size)
    records.write_bytes(records.read_bytes() + b"\n")
    code, out = build(tmp_path, master, raw)
    assert code == 2
    assert "RawIntegrityError" in capsys.readouterr().err
    assert not (out / "processed").exists()


def test_output_root_inside_raw_is_rejected(
    tmp_path: Path, master: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    raw = tmp_path / "raw"
    ingest(raw, master, base_batches())
    before = hashes(raw)
    code: int = _module("build_historical_dataset").main(
        ["--raw-root", str(raw), "--interim-root", str(raw / "x"), "--station-master", str(master)]
    )
    assert code == 2
    assert "outside the raw root" in capsys.readouterr().err
    assert hashes(raw) == before


def test_rebuilt_station_master_is_refused_on_the_same_interim_root(
    tmp_path: Path,
    master: Path,
    make_sensors_csv: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression (review): write-once component outputs never change under a new master; a new
    interim root is required, and it yields a new dataset version."""
    raw = tmp_path / "raw"
    ingest(raw, master, base_batches())
    first, _ = run_ok(tmp_path, master, raw, capsys)
    rebuilt = make_sensors_csv([("27608", RF), ("27608", WL), ("26460", WL), ("27587", WL)])
    code, _ = build(tmp_path, rebuilt, raw)
    assert code == 2
    assert "ImmutableArtifactError" in capsys.readouterr().err
    second, _ = run_ok(tmp_path, rebuilt, raw, capsys, "-new-master")
    assert second["dataset_version"] != first["dataset_version"]
