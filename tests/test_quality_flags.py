"""Offline tests for the quality-flag layer (docs/QUALITY_FLAGS.md).

Payloads are the trimmed REAL fixtures in tests/fixtures/jps and tests/fixtures/metmalaysia,
ingested with the real raw pipeline and passed through the real component layers. Mutated records
(``synthetic(...)``) and the station master built by ``make_sensors_csv`` are SYNTHETIC.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
from floodguard.ingestion.storage import fs_path
from floodguard.preprocessing import station_ids, timestamps, units
from floodguard.station_master import SensorType
from floodguard.validation.quality_flags import (
    INFORMATIONAL,
    PipelineJoinError,
    QualityFlag,
    flag_batch,
    is_usable,
)

pytestmark = pytest.mark.usefixtures("no_network")

ROOT = Path(__file__).resolve().parents[1]
JPS = ROOT / "tests" / "fixtures" / "jps"
FORECAST = ROOT / "tests/fixtures/metmalaysia/weather_forecast_trimmed_20260924T112926+0800.json"
AT = datetime(2026, 9, 24, 8, 0, tzinfo=timezone(timedelta(hours=8)))
RF, WL = SensorType.RAINFALL, SensorType.WATER_LEVEL
Rows = list[dict[str, Any]]


@pytest.fixture
def mapper(make_sensors_csv: Callable[..., Path]) -> SensorMapper:
    return SensorMapper.from_csv(make_sensors_csv([("27608", RF), ("27608", WL), ("26460", WL)]))


def ingest(tmp: Path, adapter: Adapter, payload: bytes, mapper: SensorMapper | None) -> Rows:
    rep = ingest_batch(
        payload,
        adapter,
        source_reference="https://example.invalid/x",
        retrieved_at=AT,
        raw_root=tmp,
        mapper=mapper,
    )
    assert rep.status is BatchStatus.SUCCEEDED
    rows: Rows = []
    for p in rep.artifact_paths[1:]:  # records, quarantine
        text = fs_path(tmp / p).read_text(encoding="utf-8")
        rows += [json.loads(x) for x in text.splitlines()]
    return rows


def run(records: Rows, mapper: SensorMapper | None, *, quarantined: bool = False) -> Rows:
    """Component layers exactly as the pipeline runs them, then the quality layer."""
    return flag_batch(
        records,
        quarantined=quarantined,
        timestamp_rows=[] if quarantined else [timestamps.normalize_record(r) for r in records],
        station_rows=([station_ids.normalize_record(r, mapper) for r in records] if mapper else []),
        unit_rows=[u for r in records for u in units.validate_record(r)],
    )


def history(tmp: Path, mapper: SensorMapper, sensor: SensorType, name: str, sid: str) -> Rows:
    adapter = history_adapter(sensor, sid, "https://example.invalid/h")
    return ingest(tmp, adapter, (JPS / name).read_bytes(), mapper)


def synthetic(rec: dict[str, Any], **over: Any) -> dict[str, Any]:
    out = copy.deepcopy(rec)
    out.update(over)
    if "value_raw" in over:
        out["source_fields_raw"][out["value_field"]] = over["value_raw"]
    return out


def flags(row: dict[str, Any]) -> set[str]:
    return set(row["quality_flags"])


# ---------------------------------------------------------------- real fixtures


def test_zero_rainfall_is_usable_and_never_flagged_missing(
    tmp_path: Path, mapper: SensorMapper
) -> None:
    recs = history(tmp_path, mapper, RF, "history_rainfall_27608_20260918_trimmed.json", "27608")
    rows = run(recs, mapper)
    zeros = [r for r in rows if r["parsed_value"] == 0.0]
    assert zeros
    for r in zeros:
        assert flags(r) == {QualityFlag.TIMEZONE_ASSUMED}
        assert r["usable"] is True
        assert r["measurement_type"] == "RAINFALL_INTERVAL"
        assert r["canonical_unit"] == "mm"


def test_water_level_history_markers_and_source_severity(
    tmp_path: Path, mapper: SensorMapper
) -> None:
    recs = history(tmp_path, mapper, WL, "history_water_level_27608_20240924_trimmed.json", "27608")
    rows = {r["source_row_index"]: r for r in run(recs, mapper)}
    by_raw = {r["source_row_index"]: r["source_fields_raw"].get("severity") for r in recs}
    for i, r in rows.items():
        if r["value_raw"] == "-9999":
            assert QualityFlag.VALUE_MISSING_SENTINEL in flags(r)
            assert r["usable"] is False
            assert r["parsed_value"] is None
        if by_raw[i] == "ERROR":
            assert QualityFlag.SOURCE_SEVERITY_ERROR in flags(r)
        # component statuses are preserved verbatim
        assert r["unit_validation_status"] == "VALID"
        assert r["station_id_mapping_status"] == "MAPPED"
        assert r["timestamp_quality_flag"] == "VALID"
    assert any(r["usable"] for r in rows.values())  # SL_NML rows carry real readings


def test_no_flood_severity_category_is_a_quality_flag() -> None:
    names = {f.value.upper() for f in QualityFlag}
    assert not names & {"NORMAL", "WASPADA", "AMARAN", "BAHAYA", "ALERT", "WARNING", "DANGER"}


def test_listing_unmapped_rows_are_quarantined_and_flagged(
    tmp_path: Path, mapper: SensorMapper
) -> None:
    recs = ingest(
        tmp_path, WATER_LEVEL_LISTING, (JPS / "aras_air_data_PNG_trimmed.html").read_bytes(), mapper
    )
    accepted = [r for r in recs if r["quarantine_reason"] is None]
    quarantined = [r for r in recs if r["quarantine_reason"] is not None]
    assert accepted
    assert quarantined
    q = run(quarantined, mapper, quarantined=True)
    for r in q:
        assert {QualityFlag.RAW_QUARANTINED, QualityFlag.SENSOR_UNMAPPED} <= flags(r)
        assert r["timestamp_quality_flag"] is None  # quarantine is not timestamp-normalised
        assert r["raw_quarantine_reason"] == "UNMAPPED_SENSOR"
        assert r["usable"] is False
    assert all(r["usable"] for r in run(accepted, mapper) if r["parsed_value"] is not None)


def test_rainfall_listing_rows_have_no_threshold_quality_rows(
    tmp_path: Path, mapper: SensorMapper
) -> None:
    recs = ingest(
        tmp_path,
        RAINFALL_LISTING,
        (JPS / "searchresultrainfall_PNG_trimmed.html").read_bytes(),
        mapper,
    )
    rows = run([r for r in recs if r["quarantine_reason"] is None], mapper)
    assert {r["field_role"] for r in rows} == {"PRIMARY_VALUE"}
    assert {r["measurement_type"] for r in rows} == {"RAINFALL_1H_TOTAL"}


def test_forecast_rows_are_flagged_not_station_observations(tmp_path: Path) -> None:
    recs = ingest(tmp_path, WeatherForecastAdapter(), FORECAST.read_bytes(), None)
    rows = run(recs, None)
    roles = {(r["field_role"], r["measurement_type"]) for r in rows}
    assert roles == {
        ("PRIMARY_VALUE", None),
        ("SOURCE_FIELD", "FORECAST_TEMPERATURE_MIN"),
        ("SOURCE_FIELD", "FORECAST_TEMPERATURE_MAX"),
    }
    for r in rows:
        assert {QualityFlag.NO_STATION_SENSOR, QualityFlag.TIMESTAMP_DATE_ONLY} <= flags(r)
        assert r["usable"] is False
    primary = [r for r in rows if r["field_role"] == "PRIMARY_VALUE"]
    for r in primary:  # regression: categorical text is not a measurement, so no VALUE_* flag
        assert QualityFlag.MEASUREMENT_SEMANTICS_UNKNOWN in flags(r)
        assert not {f for f in flags(r) if f.startswith("VALUE_")}


# ---------------------------------------------------------------- synthetic conditions


@pytest.fixture
def rain(tmp_path: Path, mapper: SensorMapper) -> dict[str, Any]:
    recs = history(tmp_path, mapper, RF, "history_rainfall_27608_20260918_trimmed.json", "27608")
    return recs[0]


@pytest.mark.parametrize(
    ("over", "expected"),
    [
        ({"value_raw": "ERROR"}, QualityFlag.VALUE_SOURCE_ERROR),
        ({"value_raw": "Tiada Data"}, QualityFlag.VALUE_NO_DATA_MARKER),
        ({"value_raw": "-9999.0"}, QualityFlag.VALUE_MISSING_SENTINEL),
        ({"value_raw": "  "}, QualityFlag.VALUE_EMPTY),
        ({"value_raw": None}, QualityFlag.VALUE_EMPTY),
        ({"value_raw": "1,2"}, QualityFlag.VALUE_NON_NUMERIC),
        ({"value_raw": "-0.5"}, QualityFlag.RAINFALL_NEGATIVE),
        ({"source_time_raw": "19/09/2099 00:00"}, QualityFlag.TIMESTAMP_FUTURE),
        ({"source_time_raw": "31/02/2026 00:00"}, QualityFlag.TIMESTAMP_INVALID_FORMAT),
        ({"source_time_raw": ""}, QualityFlag.TIMESTAMP_MISSING),
        ({"unit": "m"}, QualityFlag.UNIT_MISMATCH),
        ({"unit": "inch"}, QualityFlag.UNIT_UNKNOWN),
        ({"source_station_id": "26460", "fg_sensor_id": None}, QualityFlag.SENSOR_TYPE_MISMATCH),
        ({"sensor_type": "WIND"}, QualityFlag.SENSOR_TYPE_INVALID),
        ({"value_field": "clean"}, QualityFlag.MEASUREMENT_SEMANTICS_UNKNOWN),
    ],
)
def test_each_condition_gets_its_own_blocking_flag(
    rain: dict[str, Any], mapper: SensorMapper, over: dict[str, Any], expected: QualityFlag
) -> None:
    [row] = [
        r for r in run([synthetic(rain, **over)], mapper) if r["field_role"] == "PRIMARY_VALUE"
    ]
    assert expected in flags(row)
    assert expected not in INFORMATIONAL
    assert row["usable"] is False


def test_sensor_type_mismatch_also_fails_units(rain: dict[str, Any], mapper: SensorMapper) -> None:
    # SYNTHETIC: a rainfall-history field on a record typed WATER_LEVEL (27608 has both sensors)
    [row] = run([synthetic(rain, sensor_type="WATER_LEVEL", fg_sensor_id=None)], mapper)
    assert QualityFlag.UNIT_SENSOR_TYPE_MISMATCH in flags(row)
    assert row["usable"] is False


def test_invalid_and_unmapped_source_ids(rain: dict[str, Any], mapper: SensorMapper) -> None:
    [bad] = run([synthetic(rain, source_station_id="27 608", fg_sensor_id=None)], mapper)
    [unk] = run([synthetic(rain, source_station_id="99999", fg_sensor_id=None)], mapper)
    assert QualityFlag.SOURCE_ID_INVALID in flags(bad)
    assert QualityFlag.SENSOR_UNMAPPED in flags(unk)


def test_multiple_flags_on_one_row_are_sorted_and_unique(
    rain: dict[str, Any], mapper: SensorMapper
) -> None:
    [row] = run([synthetic(rain, value_raw="ERROR", source_time_raw="19/09/2099 00:00")], mapper)
    assert row["quality_flags"] == sorted(row["quality_flags"])
    assert {QualityFlag.VALUE_SOURCE_ERROR, QualityFlag.TIMESTAMP_FUTURE} <= flags(row)


def test_station_master_change_is_informational(rain: dict[str, Any], mapper: SensorMapper) -> None:
    [row] = run([synthetic(rain, fg_sensor_id=None, mapping_status="UNMAPPED")], mapper)
    assert QualityFlag.STATION_MASTER_CHANGED_SINCE_INGEST in flags(row)
    assert row["usable"] is True


def test_is_usable_only_with_informational_flags() -> None:
    assert is_usable([])
    assert is_usable([f.value for f in INFORMATIONAL])
    assert not is_usable(["TIMEZONE_ASSUMED", "VALUE_EMPTY"])


def test_deterministic(tmp_path: Path, mapper: SensorMapper) -> None:
    recs = history(tmp_path, mapper, WL, "history_water_level_27608_20240924_trimmed.json", "27608")
    assert run(recs, mapper) == run(copy.deepcopy(recs), mapper)


def test_raw_records_are_not_modified(rain: dict[str, Any], mapper: SensorMapper) -> None:
    before = copy.deepcopy(rain)
    run([rain], mapper)
    assert rain == before


# ---------------------------------------------------------------- join defects fail loudly


def _layers(recs: Rows, mapper: SensorMapper) -> tuple[Rows, Rows, Rows]:
    return (
        [timestamps.normalize_record(r) for r in recs],
        [station_ids.normalize_record(r, mapper) for r in recs],
        [u for r in recs for u in units.validate_record(r)],
    )


def test_join_defects_raise(tmp_path: Path, mapper: SensorMapper) -> None:
    recs = history(tmp_path, mapper, RF, "history_rainfall_27608_20260918_trimmed.json", "27608")
    ts, sid, un = _layers(recs, mapper)

    def fails(**kw: Any) -> None:
        args: dict[str, Any] = {
            "quarantined": False,
            "timestamp_rows": ts,
            "station_rows": sid,
            "unit_rows": un,
        }
        with pytest.raises(PipelineJoinError):
            flag_batch(recs, **{**args, **kw})

    fails(timestamp_rows=ts[1:])  # missing component row
    fails(timestamp_rows=[*ts, ts[0]])  # duplicated component row
    fails(station_rows=[])  # JPS rows need station IDs
    fails(unit_rows=[u for u in un if u["source_row_index"] != 0])  # no PRIMARY_VALUE
    fails(unit_rows=[*un, {**un[0], "source_row_index": 10_000}])  # orphan
    fails(unit_rows=[*un, un[0]])  # duplicated field
    fails(timestamp_rows=[{**ts[0], "payload_sha256": "f" * 64}, *ts[1:]])  # provenance differs
    fails(station_rows=[{**sid[0], "fg_sensor_id": "other"}, *sid[1:]])  # ID conflict
    fails(quarantined=True)  # quarantine files have no timestamp rows
    # regression (review): off-by-one pairing inside one payload must not pass silently
    fails(
        timestamp_rows=[{**ts[0], "observation_time_raw": ts[1]["observation_time_raw"]}, *ts[1:]]
    )
    shifted = [
        {**u, "value_raw": "7.5"}
        if (u["source_row_index"], u["field_role"]) == (0, "PRIMARY_VALUE")
        else u
        for u in un
    ]
    fails(unit_rows=shifted)
    with pytest.raises(PipelineJoinError):
        flag_batch(
            [*recs, recs[0]], quarantined=False, timestamp_rows=ts, station_rows=sid, unit_rows=un
        )


def test_quarantined_record_in_a_records_file_raises(
    rain: dict[str, Any], mapper: SensorMapper
) -> None:
    """Regression (review): a quarantine record must not lose RAW_QUARANTINED silently."""
    bad = synthetic(rain, quarantine_reason="INVALID_ROW_STRUCTURE")
    with pytest.raises(PipelineJoinError):
        run([bad], mapper)
