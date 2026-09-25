"""Offline tests for the derived timestamp-normalisation layer (docs/TIMESTAMP_POLICY.md).

Source-format cases use values copied from the trimmed REAL fixtures in tests/fixtures/jps and
tests/fixtures/metmalaysia. Cases marked ``synthetic`` are constructed here (impossible dates,
leap day, explicit offsets, zone-transition times, reordered sequences).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from floodguard.ingestion.adapters.jps import RAINFALL_LISTING, history_adapter
from floodguard.ingestion.contracts import BatchStatus
from floodguard.ingestion.pipeline import ingest_batch
from floodguard.ingestion.station_mapping import SensorMapper
from floodguard.preprocessing.timestamps import (
    DATASET_FORMATS,
    FUTURE_SKEW,
    ISO_8601,
    SOURCE_TIMEZONE_POLICY,
    Precision,
    TimeFormat,
    TimestampFlag,
    TimezoneStatus,
    check_monotonic,
    normalize,
    normalize_record,
)
from floodguard.station_master import SOURCE_JPS, SensorType

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
JPS_DIR = ROOT / "tests" / "fixtures" / "jps"
GOV = "DATA_GOV_MY_WEATHER_API"
REF = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)  # after every fixture time
RF_LIST = DATASET_FORMATS[(SOURCE_JPS, "rainfall_listing")]
WL_LIST = DATASET_FORMATS[(SOURCE_JPS, "water_level_listing")]
HIST = DATASET_FORMATS[(SOURCE_JPS, "water_level_history")]
FORECAST = DATASET_FORMATS[(GOV, "weather_forecast")]
ISO = (TimeFormat(ISO_8601, Precision.SECOND),)


def jps(raw: str | None, fmts: tuple[TimeFormat, ...] = HIST, **kw: Any) -> Any:
    return normalize(raw, SOURCE_JPS, fmts, reference_utc=kw.pop("ref", REF), **kw)


# ---------------------------------------------------------------- observed source formats


@pytest.mark.parametrize(
    ("raw", "fmts", "precision", "local", "utc"),
    [  # values from the real fixtures
        (
            "24/09/2026 01:15:00",
            RF_LIST,
            "SECOND",
            "2026-09-24T01:15:00+08:00",
            "2026-09-23T17:15:00+00:00",
        ),
        (
            "24/09/2026 01:45",
            WL_LIST,
            "MINUTE",
            "2026-09-24T01:45:00+08:00",
            "2026-09-23T17:45:00+00:00",
        ),
        (
            "18/09/2026 00:00",
            DATASET_FORMATS[(SOURCE_JPS, "rainfall_history")],
            "MINUTE",
            "2026-09-18T00:00:00+08:00",
            "2026-09-17T16:00:00+00:00",
        ),
        (
            "24/09/2024 13:45",
            HIST,
            "MINUTE",
            "2024-09-24T13:45:00+08:00",
            "2024-09-24T05:45:00+00:00",
        ),
    ],
)
def test_jps_formats_assumed_malaysia_time(
    raw: str, fmts: tuple[TimeFormat, ...], precision: str, local: str, utc: str
) -> None:
    n = jps(raw, fmts)
    assert (n.observation_time_raw, n.observation_time_local, n.observation_time_utc) == (
        raw,
        local,
        utc,
    )
    assert n.precision == precision
    assert n.timestamp_quality_flag is TimestampFlag.VALID
    # Converted, but still marked as an assumption (JPS publishes no timezone).
    assert n.timezone_status is TimezoneStatus.UNSPECIFIED_ASSUMED
    assert n.timezone_name == "Asia/Kuala_Lumpur"
    assert datetime.fromisoformat(n.observation_time_local).tzinfo is not None


def test_forecast_date_stays_a_date_label() -> None:
    n = normalize("2026-09-24", GOV, FORECAST, reference_utc=REF)
    assert n.observation_date_local == "2026-09-24"
    assert n.precision is Precision.DATE
    assert n.observation_time_local is None
    assert n.observation_time_utc is None  # no fabricated midnight instant
    assert n.timezone_status is TimezoneStatus.UNSPECIFIED_ASSUMED
    assert n.timestamp_quality_flag is TimestampFlag.VALID
    # Forecast valid dates lie ahead by design: no FUTURE flag for date labels.
    far = normalize("2026-09-30", GOV, FORECAST, reference_utc=REF)
    assert far.timestamp_quality_flag is TimestampFlag.VALID


def test_listing_formats_are_not_interchangeable() -> None:
    assert jps("24/09/2026 01:45", RF_LIST).timestamp_quality_flag is TimestampFlag.INVALID_FORMAT
    assert jps("24/09/2026 01:15:00", WL_LIST).timestamp_quality_flag is (
        TimestampFlag.INVALID_FORMAT
    )


def test_conversion_is_deterministic() -> None:
    assert jps("18/09/2026 00:05") == jps("18/09/2026 00:05")


# ---------------------------------------------------------------- explicit zones (synthetic)


def test_explicit_utc_z() -> None:
    n = jps("2026-09-23T17:15:00Z", ISO)
    assert n.timezone_status is TimezoneStatus.EXPLICIT_IN_SOURCE
    assert n.timezone_name == "UTC"
    assert n.observation_time_utc == "2026-09-23T17:15:00+00:00"
    assert n.timestamp_quality_flag is TimestampFlag.VALID


def test_same_instant_different_offsets_same_utc() -> None:
    texts = ["2026-09-23T17:15:00Z", "2026-09-23T22:45:00+05:30", "2026-09-23T14:15:00-03:00"]
    got = [jps(t, ISO) for t in texts]
    assert {g.observation_time_utc for g in got} == {"2026-09-23T17:15:00+00:00"}
    assert [g.observation_time_local for g in got] == [
        "2026-09-23T17:15:00+00:00",
        "2026-09-23T22:45:00+05:30",
        "2026-09-23T14:15:00-03:00",
    ]
    assert all(g.timezone_status is TimezoneStatus.EXPLICIT_IN_SOURCE for g in got)


def test_naive_iso_uses_source_policy() -> None:
    n = jps("2026-09-24T09:00", ISO)  # shape of data.gov.my warning `issued`, minus seconds
    assert n.precision is Precision.MINUTE
    assert n.observation_time_utc == "2026-09-24T01:00:00+00:00"
    assert n.timezone_status is TimezoneStatus.UNSPECIFIED_ASSUMED


def test_unknown_source_without_zone_gets_no_instant() -> None:
    n = normalize("18/09/2026 00:00", "UNKNOWN_SOURCE", HIST, reference_utc=REF)
    assert n.timestamp_quality_flag is TimestampFlag.UNSPECIFIED_TIMEZONE
    assert n.timezone_status is TimezoneStatus.UNSPECIFIED_NO_POLICY
    assert (n.observation_time_local, n.observation_time_utc, n.timezone_name) == (None,) * 3
    explicit = normalize("2026-09-23T17:15:00Z", "UNKNOWN_SOURCE", ISO, reference_utc=REF)
    assert explicit.timestamp_quality_flag is TimestampFlag.VALID


# ---------------------------------------------------------------- validation (synthetic)


@pytest.mark.parametrize("raw", [None, "", " ", "\t\n"])
def test_missing(raw: str | None) -> None:
    n = jps(raw)
    assert n.timestamp_quality_flag is TimestampFlag.MISSING
    assert n.observation_time_raw == raw
    assert (n.observation_time_local, n.observation_time_utc, n.timezone_status) == (None,) * 3


@pytest.mark.parametrize(
    "raw",
    [
        "garbage",
        "2026-09-18 00:00",  # ISO-like, not the JPS format
        "18-09-2026 00:00",
        "18/9/2026 00:00",  # unpadded month
        "18/09/2026 0:00",  # unpadded hour
        "18/09/26 00:00",
        "18/09/2026",  # date-only in a date-time field
        "31/02/2026 10:00",  # impossible date
        "29/02/2026 00:00",  # not a leap year
        "18/13/2026 00:00",
        "18/09/2026 24:00",
        "18/09/2026 00:60",
    ],
)
def test_invalid_format(raw: str) -> None:
    n = jps(raw)
    assert n.timestamp_quality_flag is TimestampFlag.INVALID_FORMAT
    assert n.observation_time_raw == raw
    assert n.observation_time_utc is None


@pytest.mark.parametrize("raw", ["2026-02-30", "2026-9-24", "24/09/2026", "2026-09-24T00:00"])
def test_invalid_forecast_date(raw: str) -> None:
    assert normalize(raw, GOV, FORECAST, reference_utc=REF).timestamp_quality_flag is (
        TimestampFlag.INVALID_FORMAT
    )


def test_leap_day_valid() -> None:
    n = jps("29/02/2024 00:00")
    assert n.timestamp_quality_flag is TimestampFlag.VALID
    assert n.observation_time_utc == "2024-02-28T16:00:00+00:00"


def test_with_and_without_seconds() -> None:
    assert jps("24/09/2026 01:15:30", RF_LIST).observation_time_utc == "2026-09-23T17:15:30+00:00"
    assert jps("24/09/2026 01:15", WL_LIST).observation_time_utc == "2026-09-23T17:15:00+00:00"
    assert jps("2026-09-23T17:15:30Z", ISO).precision is Precision.SECOND


def test_raw_text_preserved_exactly_including_whitespace() -> None:
    raw = "  18/09/2026 00:05\t"
    n = jps(raw)
    assert n.observation_time_raw == raw
    assert n.timestamp_quality_flag is TimestampFlag.VALID
    assert n.observation_time_utc == "2026-09-17T16:05:00+00:00"


def test_future_skew_boundary() -> None:
    ref = datetime(2026, 9, 23, 17, 0, tzinfo=UTC)  # 24/09/2026 01:00 in Malaysia
    assert timedelta(minutes=10) == FUTURE_SKEW
    at = jps("24/09/2026 01:10", ref=ref)
    beyond = jps("24/09/2026 01:10:01", RF_LIST, ref=ref)
    assert at.timestamp_quality_flag is TimestampFlag.VALID  # exactly ref + skew
    assert beyond.timestamp_quality_flag is TimestampFlag.FUTURE
    assert beyond.observation_time_utc == "2026-09-23T17:10:01+00:00"  # value kept
    assert jps("24/09/2026 01:11", ref=ref).timestamp_quality_flag is TimestampFlag.FUTURE
    # Reference given with another offset: same instant, same result.
    ref_myt = ref.astimezone(timezone(timedelta(hours=8)))
    assert jps("24/09/2026 01:10", ref=ref_myt) == at


def test_naive_reference_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        jps("18/09/2026 00:00", ref=datetime(2026, 9, 24))  # noqa: DTZ001


def test_ambiguous_and_nonexistent_local_times() -> None:
    # Real Asia/Kuala_Lumpur history: 1945-09-12 +09:00 -> +07:30 (repeated wall time) and
    # 1982-01-01 +07:30 -> +08:00 (skipped 23:30-23:59 on 1981-12-31).
    for raw in ("11/09/1945 23:00", "31/12/1981 23:45"):
        n = jps(raw)
        assert n.timestamp_quality_flag is TimestampFlag.AMBIGUOUS
        assert (n.observation_time_local, n.observation_time_utc) == (None, None)
        assert n.observation_time_raw == raw
    assert jps("01/01/1982 00:00").observation_time_utc == "1981-12-31T16:00:00+00:00"


def test_kuala_lumpur_has_no_transitions_since_1982() -> None:
    zone = SOURCE_TIMEZONE_POLICY[SOURCE_JPS].assumed_zone
    d = date(1982, 1, 2)
    while d < date(2100, 1, 1):
        wall = datetime(d.year, d.month, d.day, 12)  # noqa: DTZ001
        a, b = wall.replace(tzinfo=zone, fold=0), wall.replace(tzinfo=zone, fold=1)
        assert a.utcoffset() == b.utcoffset() == timedelta(hours=8), d
        d += timedelta(days=1)


# ---------------------------------------------------------------- records and provenance


def _record(**over: Any) -> dict[str, Any]:
    rec = {
        "source": SOURCE_JPS,
        "dataset": "water_level_history",
        "source_time_raw": "24/09/2024 13:45",
        "source_time_field": "dt",
        "retrieved_at": "2026-09-23T23:36:45+00:00",
        "ingestion_batch_id": "b",
        "payload_sha256": "0" * 64,
        "source_row_index": 3,
        "source_station_id": "27608",
        "fg_sensor_id": "fg",
        "observation_time_naive": "1999-01-01T00:00:00",  # ignored: raw text is the truth
    }
    return {**rec, **over}


def test_record_uses_raw_text_not_earlier_naive_parse() -> None:
    rec = _record()
    before = dict(rec)
    out = normalize_record(rec)
    assert rec == before  # input not modified
    assert out["observation_time_utc"] == "2024-09-24T05:45:00+00:00"
    assert out["source_row_index"] == 3
    assert out["retrieved_at"] == rec["retrieved_at"]


def test_retrieved_at_never_substituted() -> None:
    out = normalize_record(_record(source_time_raw=None))
    assert out["timestamp_quality_flag"] == "MISSING"
    assert out["observation_time_local"] is None
    assert out["observation_time_utc"] is None


def test_unsupported_dataset_rejected() -> None:
    with pytest.raises(ValueError, match="no verified timestamp format"):
        normalize_record(_record(dataset="unknown"))


def test_policy_registry_is_the_single_zone_source() -> None:
    src = ROOT / "src" / "floodguard"
    texts = {p: p.read_text(encoding="utf-8") for p in src.rglob("*.py")}
    zone_ctors = [p.name for p, t in texts.items() for _ in range(t.count("ZoneInfo("))]
    assert zone_ctors == ["timestamps.py"]
    assert not [p for p, t in texts.items() if "+08:00" in t or "hours=8" in t]
    assert {p.assumed_zone.key for p in SOURCE_TIMEZONE_POLICY.values()} == {"Asia/Kuala_Lumpur"}
    assert all(p.evidence_date == "2026-09-24" for p in SOURCE_TIMEZONE_POLICY.values())


# ---------------------------------------------------------------- monotonicity (synthetic)


def test_monotonicity_reports_without_reordering() -> None:
    a, b, c = "2026-09-18T00:00:00+00:00", "2026-09-18T00:05:00+00:00", "2026-09-18T00:10:00+00:00"
    rows = [(0, a), (1, b), (2, b), (3, a), (4, None), (5, c)]
    snapshot = list(rows)
    rep = check_monotonic(rows)
    assert rows == snapshot
    assert rep.non_monotonic_positions == (3,)
    assert rep.duplicate_groups == ((a, (0, 3)), (b, (1, 2)))
    assert rep.unplaced_positions == (4,)
    assert rep.checked == 5
    assert not rep.is_monotonic
    assert check_monotonic([(0, a), (1, b), (2, c)]).is_monotonic


def test_monotonic_compares_instants_not_text() -> None:
    rep = check_monotonic([(0, "2026-09-18T08:00:00+08:00"), (1, "2026-09-18T00:00:00+00:00")])
    assert rep.duplicate_groups == (("2026-09-18T00:00:00+00:00", (0, 1)),)
    assert rep.non_monotonic_positions == ()


# ---------------------------------------------------------------- batch script (real pipeline)


def _script() -> ModuleType:
    path = ROOT / "scripts" / "normalize_timestamps.py"
    spec = importlib.util.spec_from_file_location("normalize_timestamps", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _hashes(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _ingest(tmp_path: Path, make_sensors_csv: Any, payload: bytes, adapter: Any) -> Path:
    raw = tmp_path / "raw"
    mapper = SensorMapper.from_csv(
        make_sensors_csv(
            [(i, SensorType.RAINFALL) for i in ("27603", "27608", "27616", "27643", "27666")]
            + [("27608", SensorType.WATER_LEVEL)]
        )
    )
    rep = ingest_batch(
        payload,
        adapter,
        source_reference="https://example.invalid/wl?station=27608",
        retrieved_at=datetime(2026, 9, 24, 7, 36, 45, tzinfo=timezone(timedelta(hours=8))),
        raw_root=raw,
        mapper=mapper,
    )
    assert rep.status is BatchStatus.SUCCEEDED
    return raw / rep.artifact_paths[1]


def test_script_normalizes_history_batch_without_touching_raw(
    tmp_path: Path, make_sensors_csv: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = (JPS_DIR / "history_water_level_27608_20240924_trimmed.json").read_bytes()
    adapter = history_adapter(
        SensorType.WATER_LEVEL, "27608", "https://example.invalid/wl?station=27608"
    )
    records = _ingest(tmp_path, make_sensors_csv, payload, adapter)
    raw, out = tmp_path / "raw", tmp_path / "interim"
    before = _hashes(raw)
    args = ["--records", str(records), "--raw-root", str(raw), "--out-root", str(out)]
    assert _script().main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert _hashes(raw) == before  # raw payload, records, quarantine, manifest untouched
    first = _hashes(out)
    assert _script().main(args) == 0  # rerun: identical output, write-once no-op
    assert json.loads(capsys.readouterr().out)["written"] is False
    assert _hashes(out) == first
    assert _hashes(raw) == before

    recs = [json.loads(x) for x in records.read_text(encoding="utf-8").splitlines()]
    rows = [json.loads(x) for x in (out / report["output_path"]).read_text().splitlines()]
    assert report["rows"] == len(rows) == len(recs) == 8
    assert report["flags"] == {"VALID": 8}
    assert report["monotonicity"]["non_monotonic_positions"] == []
    assert report["monotonicity"]["duplicate_groups"] == []
    for rec, row in zip(recs, rows, strict=True):
        assert row["observation_time_raw"] == rec["source_time_raw"]
        assert row["source_row_index"] == rec["source_row_index"]
        assert row["timezone_status"] == "UNSPECIFIED_ASSUMED"
        assert datetime.fromisoformat(row["observation_time_utc"]).utcoffset() == timedelta(0)
        assert datetime.fromisoformat(row["observation_time_local"]).tzinfo is not None
    assert rows[0]["observation_time_utc"] == "2024-09-24T05:45:00+00:00"


def test_script_on_rainfall_listing(
    tmp_path: Path, make_sensors_csv: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = (JPS_DIR / "searchresultrainfall_PNG_trimmed.html").read_bytes()
    records = _ingest(tmp_path, make_sensors_csv, payload, RAINFALL_LISTING)
    args = ["--records", str(records), "--raw-root", str(tmp_path / "raw")]
    assert _script().main([*args, "--out-root", str(tmp_path / "interim")]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["rows"] > 0
    assert report["flags"] == {"VALID": report["rows"]}
    assert report["monotonicity"] is None  # multi-station snapshot: no sequence to check


def test_script_rejects_unverified_or_unsafe_inputs(
    tmp_path: Path, make_sensors_csv: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = (JPS_DIR / "history_water_level_27608_20240924_trimmed.json").read_bytes()
    adapter = history_adapter(
        SensorType.WATER_LEVEL, "27608", "https://example.invalid/wl?station=27608"
    )
    records = _ingest(tmp_path, make_sensors_csv, payload, adapter)
    raw = tmp_path / "raw"
    base = ["--records", str(records), "--raw-root", str(raw)]
    assert _script().main([*base, "--out-root", str(raw / "derived")]) == 2
    stray = tmp_path / "stray.records.jsonl"
    stray.write_bytes(records.read_bytes())
    assert _script().main(["--records", str(stray), "--raw-root", str(raw)]) == 2
    copy = raw / "jps" / "x.records.jsonl"  # synthetic: inside raw root, not in the manifest
    copy.write_bytes(records.read_bytes())
    out = str(tmp_path / "o")
    assert _script().main(["--records", str(copy), "--raw-root", str(raw), "--out-root", out]) == 2
    assert not (tmp_path / "o").exists()
    assert "REJECTED" in capsys.readouterr().err
