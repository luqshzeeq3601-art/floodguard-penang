"""Offline tests for the raw-ingestion pipeline, immutable storage, manifest and CLI.

Payloads are the trimmed REAL JPS captures in tests/fixtures/jps (provenance in its README);
``test_synthetic_*`` tests mutate them. Station masters are SYNTHETIC files built per test by
``make_sensors_csv`` (IDs derived by the real ``station_master.sensor_id`` rule). Every raw root
is under ``tmp_path``; data/raw, data/local and git-ignored captures are never read. Network is
blocked for every test here (``no_network``).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any

import pytest

from floodguard.ingestion import manifest, storage
from floodguard.ingestion.adapters.jps import (
    RAINFALL_LISTING,
    WATER_LEVEL_LISTING,
    history_adapter,
)
from floodguard.ingestion.contracts import MANIFEST_SCHEMA_VERSION, Adapter, BatchStatus
from floodguard.ingestion.pipeline import ingest_batch
from floodguard.ingestion.station_mapping import SensorMapper
from floodguard.station_master import SOURCE_JPS, SensorType, sensor_id

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
JPS = ROOT / "tests" / "fixtures" / "jps"
RF_HTML = (JPS / "searchresultrainfall_PNG_trimmed.html").read_bytes()
WL_HTML = (JPS / "aras_air_data_PNG_trimmed.html").read_bytes()
WL_HIST = (JPS / "history_water_level_27608_20240924_trimmed.json").read_bytes()
RF_AT = datetime(2026, 9, 24, 1, 39, 20, tzinfo=timezone(timedelta(hours=8)))
REF = "https://example.invalid/listing"
WL_URL = "https://example.invalid/wl?station=27608"

RF_IDS = ["27603", "27608", "27616", "27643", "27666", "BUMBUNGLIMA", "26186", "5402002_"]
WL_IDS = ["27587", "27608", "27620", "BUMBUNGLIMA", "5302004_", "26189", "26460"]  # all 7
MASTER = [(i, SensorType.RAINFALL) for i in RF_IDS] + [(i, SensorType.WATER_LEVEL) for i in WL_IDS]

Make = Callable[[Iterable[tuple[str, SensorType]]], Path]


@pytest.fixture
def mapper(make_sensors_csv: Make) -> SensorMapper:
    return SensorMapper.from_csv(make_sensors_csv(MASTER))  # 26185 (RF) deliberately absent


def run(
    raw_root: Path,
    payload: bytes,
    mapper: SensorMapper,
    adapter: Adapter = RAINFALL_LISTING,
    at: datetime = RF_AT,
) -> Any:
    return ingest_batch(
        payload, adapter, source_reference=REF, retrieved_at=at, raw_root=raw_root, mapper=mapper
    )


def snapshot(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------- success paths


def test_rainfall_ingestion_writes_payload_records_quarantine(
    tmp_path: Path, mapper: SensorMapper
) -> None:
    raw = tmp_path / "r"
    rep = run(raw, RF_HTML, mapper)
    assert rep.status is BatchStatus.SUCCEEDED
    assert (rep.input_rows, rep.accepted_rows, rep.quarantined_rows) == (9, 8, 1)
    assert (rep.unmapped_rows, rep.invalid_structural_rows, rep.artifacts_written) == (1, 0, 3)
    sha = hashlib.sha256(RF_HTML).hexdigest()
    assert rep.payload_sha256 == sha
    d = raw / "jps" / "rainfall_listing" / "2026" / "09" / "23"  # UTC date of 01:39 +08:00
    assert (d / f"{sha}.html").read_bytes() == RF_HTML  # payload preserved byte-for-byte
    recs = jsonl(d / f"{sha}.records.jsonl")
    quar = jsonl(d / f"{sha}.quarantine.jsonl")
    assert len(recs) == 8
    assert [q["source_station_id"] for q in quar] == ["26185"]
    assert quar[0]["quarantine_reason"] == "UNMAPPED_SENSOR"
    assert quar[0]["fg_sensor_id"] is None
    r = next(x for x in recs if x["source_station_id"] == " 5402002_")
    assert r["fg_sensor_id"] == sensor_id(SOURCE_JPS, "5402002_", SensorType.RAINFALL)
    assert r["retrieved_at"] == "2026-09-23T17:39:20+00:00"
    assert r["timezone_interpretation"] == "UNVERIFIED_ASSUMED_MYT"
    assert r["source_time_raw"] == "24/09/2026 01:00:00"
    assert r["payload_sha256"] == sha
    assert r["record_schema_version"] == "raw_record/v1"
    assert r["parser_version"] == RAINFALL_LISTING.parser_version
    assert r["ingestion_batch_id"] == rep.batch_id
    assert r["value_raw"] == "0.0"  # zero rainfall accepted as data


def test_water_level_ingestion_and_shared_id_sensors(tmp_path: Path, mapper: SensorMapper) -> None:
    raw = tmp_path / "r"
    rf = run(raw, RF_HTML, mapper)
    wl = run(raw, WL_HTML, mapper, WATER_LEVEL_LISTING)
    assert wl.status is BatchStatus.SUCCEEDED
    assert (wl.input_rows, wl.accepted_rows, wl.quarantined_rows) == (7, 7, 0)
    rf_recs = jsonl(raw / rf.artifact_paths[1])
    wl_recs = jsonl(raw / wl.artifact_paths[1])
    rf_27608 = next(r for r in rf_recs if r["source_station_id"] == "27608")["fg_sensor_id"]
    wl_27608 = next(r for r in wl_recs if r["source_station_id"] == "27608")
    assert rf_27608 != wl_27608["fg_sensor_id"]  # same jps_internal_id, different sensors
    assert wl_27608["threshold_temporal_scope"] == "CURRENT_AT_RETRIEVAL"


def test_history_ingestion_preserves_markers(tmp_path: Path, mapper: SensorMapper) -> None:
    rep = run(
        tmp_path / "r", WL_HIST, mapper, history_adapter(SensorType.WATER_LEVEL, "27608", REF)
    )
    assert rep.status is BatchStatus.SUCCEEDED
    recs = jsonl(tmp_path / "r" / rep.artifact_paths[1])
    assert [r["value_raw"] for r in recs] == [
        "-9999",
        "-9999",
        "19.18",
        "19.18",
        "-9999",
        "-9999",
        "-9999",
        "19.17",
    ]
    assert recs[0]["source_fields_raw"]["severity"] == "ERROR"
    assert recs[0]["threshold_temporal_scope"] == "CURRENT_NOT_HISTORICAL"


def test_synthetic_source_duplicates_counted_not_dropped(
    tmp_path: Path, mapper: SensorMapper
) -> None:
    doc = json.loads(WL_HIST)
    doc["values"].append(dict(doc["values"][0]))
    doc["values"].append({**doc["values"][2], "final": "19.99"})  # same time, different value
    payload = json.dumps(doc).encode()
    rep = run(
        tmp_path / "r", payload, mapper, history_adapter(SensorType.WATER_LEVEL, "27608", REF)
    )
    assert (rep.input_rows, rep.accepted_rows, rep.source_duplicates_observed) == (10, 10, 2)


def test_synthetic_missing_timestamp_quarantined_batch_succeeds(
    tmp_path: Path, mapper: SensorMapper
) -> None:
    doc = json.loads(WL_HIST)
    doc["values"][3]["dt"] = ""
    payload = json.dumps(doc).encode()
    rep = run(
        tmp_path / "r", payload, mapper, history_adapter(SensorType.WATER_LEVEL, "27608", REF)
    )
    assert rep.status is BatchStatus.SUCCEEDED
    assert (rep.accepted_rows, rep.invalid_structural_rows, rep.unmapped_rows) == (7, 1, 0)
    q = jsonl(tmp_path / "r" / rep.artifact_paths[2])
    assert q[0]["quarantine_reason"] == "MISSING_TIMESTAMP"
    assert q[0]["source_row_index"] == 3


def test_records_are_deterministic(tmp_path: Path, mapper: SensorMapper) -> None:
    a, b = run(tmp_path / "a", RF_HTML, mapper), run(tmp_path / "b", RF_HTML, mapper)
    assert a.run_id != b.run_id
    assert a.batch_id == b.batch_id
    sa, sb = snapshot(tmp_path / "a"), snapshot(tmp_path / "b")
    sa.pop("_manifest/raw_batches.jsonl")
    sb.pop("_manifest/raw_batches.jsonl")
    assert sa == sb  # payload, records and quarantine bytes identical


def test_deep_raw_root_beyond_windows_max_path(tmp_path: Path, mapper: SensorMapper) -> None:
    """Regression: a raw root whose artifact paths exceed 260 characters must still work."""
    raw = tmp_path / ("d" * 90) / ("e" * 90)
    adapter = history_adapter(SensorType.WATER_LEVEL, "27608", REF)
    rep = run(raw, WL_HIST, mapper, adapter)
    assert rep.status is BatchStatus.SUCCEEDED, rep.error_reason
    longest = max(len(str(raw / p)) for p in rep.artifact_paths)
    assert longest > 260
    assert run(raw, WL_HIST, mapper, adapter).status is BatchStatus.DUPLICATE


# ---------------------------------------------------------------- idempotency and immutability


def test_repeated_payload_is_duplicate_and_writes_nothing(
    tmp_path: Path, mapper: SensorMapper
) -> None:
    raw = tmp_path / "r"
    first = run(raw, RF_HTML, mapper)
    before = snapshot(raw)
    again = run(raw, RF_HTML, mapper, at=RF_AT + timedelta(minutes=5))
    after = snapshot(raw)
    assert again.status is BatchStatus.DUPLICATE
    assert (again.artifacts_written, again.duplicate_of_run_id) == (0, first.run_id)
    assert again.batch_id == first.batch_id
    changed = {k for k in after if before.get(k) != after[k]}
    assert changed == {"_manifest/raw_batches.jsonl"}
    entries = manifest.read_entries(raw)
    assert [e["status"] for e in entries] == ["SUCCEEDED", "DUPLICATE"]
    assert entries[0]["payload_sha256"] == entries[1]["payload_sha256"]
    assert entries[1]["records_path"] == entries[0]["records_path"]


def test_changed_payload_creates_new_batch(tmp_path: Path, mapper: SensorMapper) -> None:
    raw = tmp_path / "r"
    first = run(raw, RF_HTML, mapper)
    changed = RF_HTML.replace(b"<td>50.5</td>", b"<td>51.0</td>", 1)
    second = run(raw, changed, mapper, at=RF_AT + timedelta(minutes=5))
    assert second.status is BatchStatus.SUCCEEDED
    assert second.payload_sha256 != first.payload_sha256
    assert set(second.artifact_paths).isdisjoint(first.artifact_paths)
    assert (raw / first.artifact_paths[0]).read_bytes() == RF_HTML


def test_identical_history_body_for_other_station_is_not_duplicate(
    tmp_path: Path, mapper: SensorMapper
) -> None:
    """History bodies carry no station ID and "No result" is identical for every station."""
    raw = tmp_path / "r"
    no_result = (JPS / "history_no_result.txt").read_bytes()
    a = run(raw, no_result, mapper, history_adapter(SensorType.RAINFALL, "27608", REF))
    b = run(raw, no_result, mapper, history_adapter(SensorType.RAINFALL, "26185", REF))
    c = run(raw, no_result, mapper, history_adapter(SensorType.RAINFALL, " 27608", REF))
    assert (a.status, b.status, c.status) == ("SUCCEEDED", "SUCCEEDED", "DUPLICATE")
    assert a.source_no_result
    assert (a.input_rows, a.artifacts_written) == (0, 3)
    assert a.artifact_paths[0].startswith("jps/rainfall_history/27608/")
    assert b.artifact_paths[0].startswith("jps/rainfall_history/26185/")


def test_storage_never_overwrites(tmp_path: Path) -> None:
    rel = PurePosixPath("jps", "x", "a.json")
    assert storage.write_artifacts(tmp_path, [storage.Artifact(rel, b"one")]) == [rel]
    assert storage.write_artifacts(tmp_path, [storage.Artifact(rel, b"one")]) == []  # identical
    with pytest.raises(storage.ImmutableArtifactError, match="refusing to overwrite"):
        storage.write_artifacts(tmp_path, [storage.Artifact(rel, b"two")])
    assert (tmp_path / "jps" / "x" / "a.json").read_bytes() == b"one"
    assert [p.name for p in (tmp_path / "jps" / "x").iterdir()] == ["a.json"]  # no temp left


def test_synthetic_orphan_conflict_fails_without_overwrite(
    tmp_path: Path, mapper: SensorMapper
) -> None:
    """An artifact left by an interrupted run with different content is never replaced."""
    raw = tmp_path / "r"
    sha = hashlib.sha256(RF_HTML).hexdigest()
    orphan = raw / "jps" / "rainfall_listing" / "2026" / "09" / "23" / f"{sha}.records.jsonl"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"orphan\n")
    rep = run(raw, RF_HTML, mapper)
    assert rep.status is BatchStatus.FAILED
    assert "refusing to overwrite" in (rep.error_reason or "")
    assert orphan.read_bytes() == b"orphan\n"
    assert snapshot(raw).keys() == {
        orphan.relative_to(raw).as_posix(),
        "_manifest/raw_batches.jsonl",
    }


# ---------------------------------------------------------------- failures


def test_schema_change_fails_with_reason_and_no_artifacts(
    tmp_path: Path, mapper: SensorMapper
) -> None:
    raw = tmp_path / "r"
    bad = RF_HTML.replace(b"Jumlah 1 Jam", b"Hujan 1 Jam")
    rep = run(raw, bad, mapper)
    assert rep.status is BatchStatus.FAILED
    assert "SchemaError" in (rep.error_reason or "")
    assert "Jumlah 1 Jam" in (rep.error_reason or "")
    assert list(snapshot(raw)) == ["_manifest/raw_batches.jsonl"]
    (entry,) = manifest.read_entries(raw)
    assert entry["status"] == "FAILED"
    assert entry["records_path"] is None
    # a FAILED attempt does not block a later successful ingest of a fixed payload
    assert run(raw, RF_HTML, mapper).status is BatchStatus.SUCCEEDED


def test_malformed_payload_fails(tmp_path: Path, mapper: SensorMapper) -> None:
    adapter = history_adapter(SensorType.WATER_LEVEL, "27608", WL_URL)
    rep = run(tmp_path / "r", b'{"info": {"name": "x"}, "values": [', mapper, adapter)
    assert rep.status is BatchStatus.FAILED
    assert "not JSON" in (rep.error_reason or "")


def test_write_failure_fails_cleanly(
    tmp_path: Path, mapper: SensorMapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulated disk error on the 2nd of 3 placements: batch FAILED, nothing left behind."""
    raw = tmp_path / "r"
    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src: Any, dst: Any) -> None:
        if str(dst).endswith(".jsonl") and "_manifest" not in str(dst):
            calls["n"] += 1
            if calls["n"] == 1:
                real_replace(src, dst)
                return
            raise OSError(28, "No space left on device (simulated)")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky_replace)
    rep = run(raw, RF_HTML, mapper)
    assert rep.status is BatchStatus.FAILED
    assert "simulated" in (rep.error_reason or "")
    assert rep.artifacts_written == 0
    assert list(snapshot(raw)) == ["_manifest/raw_batches.jsonl"]  # no payload/records/temp
    assert not any(p.name.endswith(".tmp") for p in raw.rglob("*"))
    assert manifest.read_entries(raw)[0]["status"] == "FAILED"
    monkeypatch.undo()
    assert run(raw, RF_HTML, mapper).status is BatchStatus.SUCCEEDED  # retry after the fault


def test_manifest_failure_removes_artifacts(
    tmp_path: Path, mapper: SensorMapper, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "r"
    real_append = manifest.append_entry

    def append(root: Path, entry: dict[str, Any]) -> None:
        if entry["status"] == BatchStatus.SUCCEEDED:
            raise OSError("manifest disk error (simulated)")
        real_append(root, entry)

    monkeypatch.setattr(manifest, "append_entry", append)
    rep = run(raw, RF_HTML, mapper)
    assert rep.status is BatchStatus.FAILED
    assert "artifacts removed" in (rep.error_reason or "")
    assert list(snapshot(raw)) == ["_manifest/raw_batches.jsonl"]


def test_naive_retrieved_at_rejected(tmp_path: Path, mapper: SensorMapper) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        run(tmp_path / "r", RF_HTML, mapper, at=datetime(2026, 9, 24, 1, 39))  # noqa: DTZ001


def test_manifest_fields(tmp_path: Path, mapper: SensorMapper) -> None:
    raw = tmp_path / "r"
    rep = run(raw, RF_HTML, mapper)
    (e,) = manifest.read_entries(raw)
    assert set(e) == set(manifest.MANIFEST_FIELDS)
    assert e["partition"] is None
    assert e["manifest_schema_version"] == MANIFEST_SCHEMA_VERSION
    assert (e["run_id"], e["batch_id"], e["status"]) == (rep.run_id, rep.batch_id, "SUCCEEDED")
    assert (e["source"], e["dataset"], e["source_reference"]) == (
        SOURCE_JPS,
        "rainfall_listing",
        REF,
    )
    assert e["retrieved_at"] == "2026-09-23T17:39:20+00:00"
    assert datetime.fromisoformat(e["ingested_at"]).utcoffset() == timedelta(0)
    assert e["payload_sha256"] == hashlib.sha256(RF_HTML).hexdigest()
    assert (e["input_rows"], e["accepted_rows"], e["quarantined_rows"]) == (9, 8, 1)
    assert (e["parser_name"], e["parser_version"]) == (
        RAINFALL_LISTING.parser_name,
        RAINFALL_LISTING.parser_version,
    )
    assert e["record_schema_version"] == "raw_record/v1"
    assert e["error_reason"] is None
    rec_bytes = (raw / e["records_path"]).read_bytes()
    assert e["records_sha256"] == hashlib.sha256(rec_bytes).hexdigest()
    assert datetime.now(UTC) >= datetime.fromisoformat(e["ingested_at"])


# ---------------------------------------------------------------- CLI


def _cli() -> ModuleType:
    path = ROOT / "scripts" / "ingest_raw.py"
    spec = importlib.util.spec_from_file_location("ingest_raw", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_cli_one_batch_then_duplicate(
    tmp_path: Path, make_sensors_csv: Make, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _cli()
    master = make_sensors_csv(MASTER)
    args = [
        "jps-water-level",
        "--input",
        str(JPS / "aras_air_data_PNG_trimmed.html"),
        "--retrieved-at",
        "2026-09-24T01:53:11+08:00",
        "--source-reference",
        REF,
        "--station-master",
        str(master),
        "--raw-root",
        str(tmp_path / "r"),
    ]
    assert cli.main(args) == 0
    first = json.loads(capsys.readouterr().out)
    assert (first["status"], first["accepted_rows"]) == ("SUCCEEDED", 7)
    assert cli.main(args) == 0
    second = json.loads(capsys.readouterr().out)
    assert (second["status"], second["duplicate_of_run_id"]) == ("DUPLICATE", first["run_id"])


def test_cli_rejects_before_batch(
    tmp_path: Path, make_sensors_csv: Make, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = _cli()
    base = ["jps-rainfall", "--input", str(JPS / "searchresultrainfall_PNG_trimmed.html")]
    base += ["--source-reference", REF, "--raw-root", str(tmp_path / "r")]
    with pytest.raises(SystemExit):  # naive --retrieved-at
        cli.main([*base, "--retrieved-at", "2026-09-24T01:39:20"])
    missing_master = ["--station-master", str(tmp_path / "none.csv")]
    assert cli.main([*base, "--retrieved-at", "2026-09-24T01:39:20+08:00", *missing_master]) == 2
    assert not (tmp_path / "r").exists()  # nothing written, no manifest entry
    capsys.readouterr()


def test_cli_has_no_jps_fetch_option() -> None:
    cli = _cli()
    for cmd in ("jps-rainfall", "jps-water-level", "jps-rainfall-history"):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args([cmd, "--fetch"])
