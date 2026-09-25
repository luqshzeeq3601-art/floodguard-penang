"""Byte-for-byte payload preservation for every raw-ingestion adapter (offline).

Payloads are the trimmed REAL captures in tests/fixtures/jps and tests/fixtures/metmalaysia; the
``crlf`` / ``bom`` variants are SYNTHETIC edits of them (CRLF line endings, trailing whitespace,
UTF-8 BOM) that the parsers tolerate. The station master is SYNTHETIC (``make_sensors_csv``). Raw
roots live under ``tmp_path``; data/raw and data/local are never read. Network is blocked.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

import pytest

from floodguard.ingestion import manifest, storage
from floodguard.ingestion.adapters.data_gov_my import WeatherForecastAdapter
from floodguard.ingestion.adapters.jps import RAINFALL_LISTING, WATER_LEVEL_LISTING, history_adapter
from floodguard.ingestion.contracts import Adapter, BatchStatus
from floodguard.ingestion.pipeline import ingest_batch
from floodguard.ingestion.station_mapping import SensorMapper
from floodguard.station_master import SensorType

pytestmark = pytest.mark.usefixtures("no_network")

FIX = Path(__file__).resolve().parent / "fixtures"
REF = "https://example.invalid/capture"
AT = datetime(2026, 9, 24, 11, 29, 26, tzinfo=timezone(timedelta(hours=8)))

CASES: dict[str, tuple[Adapter, Path]] = {
    "rainfall_listing": (RAINFALL_LISTING, FIX / "jps/searchresultrainfall_PNG_trimmed.html"),
    "water_level_listing": (WATER_LEVEL_LISTING, FIX / "jps/aras_air_data_PNG_trimmed.html"),
    "rainfall_history": (
        history_adapter(SensorType.RAINFALL, "27608", REF),
        FIX / "jps/history_rainfall_27608_20260918_trimmed.json",
    ),
    "water_level_history": (
        history_adapter(SensorType.WATER_LEVEL, "27608", REF),
        FIX / "jps/history_water_level_27608_20240924_trimmed.json",
    ),
    "weather_forecast": (
        WeatherForecastAdapter(),
        FIX / "metmalaysia/weather_forecast_trimmed_20260924T112926+0800.json",
    ),
}


def crlf(b: bytes) -> bytes:
    """Every line ending -> trailing whitespace + CRLF, plus a leading blank CRLF line."""
    return b" \r\n" + b.replace(b"\r\n", b"\n").replace(b"\n", b" \t\r\n")


VARIANTS: dict[str, Callable[[bytes], bytes]] = {
    "as_captured": lambda b: b,
    "crlf": crlf,
    "bom": lambda b: b"\xef\xbb\xbf" + crlf(b),  # HTML only: the JSON parsers reject a BOM
}
PARAMS = [(c, v) for c in CASES for v in VARIANTS if v != "bom" or c.endswith("_listing")]


@pytest.fixture
def mapper(make_sensors_csv: Callable[[Iterable[tuple[str, SensorType]]], Path]) -> SensorMapper:
    # Other listing IDs are quarantined as UNMAPPED; the batch still succeeds.
    return SensorMapper.from_csv(
        make_sensors_csv([("27608", SensorType.RAINFALL), ("27608", SensorType.WATER_LEVEL)])
    )


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.mark.parametrize(("case", "variant"), PARAMS)
def test_payload_stored_byte_for_byte(
    tmp_path: Path, mapper: SensorMapper, case: str, variant: str
) -> None:
    adapter, fixture = CASES[case]
    original = fixture.read_bytes()
    payload = VARIANTS[variant](original)
    if variant != "as_captured":
        assert payload != original
        assert b"\r\n" in payload
    raw = tmp_path / "raw"
    m = None if isinstance(adapter, WeatherForecastAdapter) else mapper

    rep = ingest_batch(
        payload, adapter, source_reference=REF, retrieved_at=AT, raw_root=raw, mapper=m
    )
    assert rep.status is BatchStatus.SUCCEEDED, rep.error_reason
    assert rep.input_rows == len(adapter.parse(original).rows) > 0  # parser tolerates the variant

    (entry,) = manifest.read_entries(raw)
    stored_path = raw / entry["payload_path"]
    stored = stored_path.read_bytes()
    assert stored == payload  # exact bytes: no decode/re-encode, no newline translation
    assert sha(stored) == entry["payload_sha256"] == rep.payload_sha256 == sha(payload)
    assert entry["payload_bytes"] == len(payload)
    assert stored_path.name == f"{sha(payload)}.{adapter.payload_extension}"

    records_path, quarantine_path = raw / entry["records_path"], raw / entry["quarantine_path"]
    assert len({stored_path, records_path, quarantine_path}) == 3  # parsed rows kept separately
    assert sha(records_path.read_bytes()) == entry["records_sha256"]
    assert sha(quarantine_path.read_bytes()) == entry["quarantine_sha256"]

    mtime = stored_path.stat().st_mtime_ns
    again = ingest_batch(
        payload,
        adapter,
        source_reference=REF,
        retrieved_at=AT + timedelta(minutes=5),
        raw_root=raw,
        mapper=m,
    )
    assert again.status is BatchStatus.DUPLICATE
    assert stored_path.read_bytes() == payload
    assert stored_path.stat().st_mtime_ns == mtime


def test_synthetic_csv_bytes_preserved_by_generic_storage(tmp_path: Path) -> None:
    """Storage is format-agnostic: a future CSV payload keeps its extension and exact bytes."""
    data = b"\xef\xbb\xbfstation,time,value \r\nX1,01/01/2026 00:00,-9999\r\nX2,,\xe9\r\n\r\n"
    rel = PurePosixPath("synthetic_source", "csv_dataset", f"{sha(data)}.csv")
    assert storage.write_artifacts(tmp_path, [storage.Artifact(rel, data)]) == [rel]
    target = tmp_path.joinpath(*rel.parts)
    assert target.read_bytes() == data
    assert storage.write_artifacts(tmp_path, [storage.Artifact(rel, data)]) == []  # idempotent
    assert [p.name for p in target.parent.iterdir()] == [target.name]  # no temp files left
