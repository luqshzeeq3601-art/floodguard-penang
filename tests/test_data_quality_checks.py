"""Offline data-quality tests: every pipeline invariant is detected when broken, and the summary
measures problems before exclusion (docs/HISTORICAL_PIPELINE.md sections 4-5).

Quality rows come from the trimmed REAL history fixtures through the real layers; every mutation
applied below is SYNTHETIC.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from floodguard.ingestion.adapters.jps import history_adapter
from floodguard.ingestion.contracts import BatchStatus
from floodguard.ingestion.pipeline import ingest_batch
from floodguard.ingestion.station_mapping import SensorMapper
from floodguard.ingestion.storage import fs_path
from floodguard.preprocessing import station_ids, timestamps, units
from floodguard.station_master import SensorType
from floodguard.validation.checks import run_checks
from floodguard.validation.observations import build_observations
from floodguard.validation.quality_flags import flag_batch
from floodguard.validation.summary import quality_summary

pytestmark = pytest.mark.usefixtures("no_network")

JPS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "jps"
AT = datetime(2026, 9, 24, 8, 0, tzinfo=timezone(timedelta(hours=8)))
Rows = list[dict[str, Any]]


@pytest.fixture
def layers(tmp_path: Path, make_sensors_csv: Callable[..., Path]) -> tuple[Rows, Rows]:
    """(quality rows, canonical rows) for real RF and WL history fixtures."""
    rf, wl = SensorType.RAINFALL, SensorType.WATER_LEVEL
    mapper = SensorMapper.from_csv(make_sensors_csv([("27608", rf), ("26460", wl)]))
    quality: Rows = []
    for sensor, sid, name in (
        (rf, "27608", "history_rainfall_27608_20260918_trimmed.json"),
        (wl, "26460", "history_water_level_26460_20260923_trimmed.json"),
    ):
        rep = ingest_batch(
            (JPS / name).read_bytes(),
            history_adapter(sensor, sid, "https://example.invalid/h"),
            source_reference="https://example.invalid/h",
            retrieved_at=AT,
            raw_root=tmp_path,
            mapper=mapper,
        )
        assert rep.status is BatchStatus.SUCCEEDED
        text = fs_path(tmp_path / rep.artifact_paths[1]).read_text(encoding="utf-8")
        recs = [json.loads(x) for x in text.splitlines()]
        quality += flag_batch(
            recs,
            quarantined=False,
            timestamp_rows=[timestamps.normalize_record(r) for r in recs],
            station_rows=[station_ids.normalize_record(r, mapper) for r in recs],
            unit_rows=[u for r in recs for u in units.validate_record(r)],
        )
    obs, _ = build_observations(quality)
    return quality, obs


def failing(obs: Rows, quality: Rows) -> set[str]:
    return {c.name for c in run_checks(obs, quality) if not c.passed}


def test_real_fixture_tables_pass_every_check(layers: tuple[Rows, Rows]) -> None:
    quality, obs = layers
    results = run_checks(obs, quality)
    assert len(results) == 15
    assert all(c.passed and c.failing == 0 for c in results)


def _first(obs: Rows, pred: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
    return next(o for o in obs if pred(o))


def _zero(o: dict[str, Any]) -> bool:
    return bool(o["value"] == 0.0)


def _marker(o: dict[str, Any]) -> bool:
    return bool(o["value_parse_status"] == "SOURCE_MARKER")


def _set(pred: Callable[[dict[str, Any]], bool], **over: Any) -> Callable[[Rows], None]:
    def mutate(obs: Rows) -> None:
        _first(obs, pred).update(over)

    return mutate


def _swap(obs: Rows) -> None:
    obs[0], obs[1] = obs[1], obs[0]


def _repeat(obs: Rows) -> None:
    obs.insert(1, copy.deepcopy(obs[0]))


def _drop_flag(flag: str) -> Callable[[Rows], None]:
    def mutate(obs: Rows) -> None:
        o = _first(obs, lambda x: flag in x["quality_flags"])
        o["quality_flags"] = [f for f in o["quality_flags"] if f != flag]

    return mutate


def _add_flag(pred: Callable[[dict[str, Any]], bool], flag: str) -> Callable[[Rows], None]:
    def mutate(obs: Rows) -> None:
        o = _first(obs, pred)
        o["quality_flags"] = sorted([*o["quality_flags"], flag])

    return mutate


def _same_count_wrong_row(obs: Rows) -> None:
    """Regression (review): one row lost and another referenced twice keeps the count equal."""
    obs[0]["provenance"][0] = copy.deepcopy(obs[1]["provenance"][0])


def _any(o: dict[str, Any]) -> bool:
    return True


@pytest.mark.parametrize(
    ("mutate", "check"),
    [
        (_repeat, "canonical_key_unique"),
        (_swap, "chronological_order"),
        (lambda obs: obs.pop(), "no_row_lost"),
        (_same_count_wrong_row, "no_row_lost"),
        (
            _set(_any, measurement_type="FORECAST_TEMPERATURE_MIN"),
            "verified_measurement_types_only",
        ),
        (_set(_zero, unit="m"), "unit_matches_measurement_type"),
        (_set(_any, fg_site_id=None), "identity_complete"),
        (_set(_marker, value=1.5), "value_matches_status_and_flags"),
        (_drop_flag("VALUE_MISSING_SENTINEL"), "value_matches_status_and_flags"),
        (_add_flag(_zero, "VALUE_EMPTY"), "zero_is_not_missing"),
        (_set(_marker, usable=True), "usable_matches_flags"),
        (_set(_any, first_retrieved_at="2000-01-01T00:00:00+00:00"), "no_future_observation"),
        (_drop_flag("TIMEZONE_ASSUMED"), "timezone_assumption_marked"),
        (_set(_any, duplicate_count=2), "provenance_complete"),
        (
            _set(_zero, duplicate_status="CONFLICT", conflicting_values=["a", "b"]),
            "conflicts_unresolved",
        ),
        (_set(_zero, value=-1.0), "usable_rainfall_non_negative"),
        (_add_flag(_any, "BAHAYA"), "quality_flags_known"),
    ],
)
def test_each_check_detects_its_violation(
    layers: tuple[Rows, Rows], mutate: Callable[[Rows], Any], check: str
) -> None:
    quality, obs = layers
    broken = copy.deepcopy(obs)
    mutate(broken)
    assert check in failing(broken, quality)


def test_zero_check_also_covers_the_validated_layer(layers: tuple[Rows, Rows]) -> None:
    quality, obs = layers
    broken = copy.deepcopy(quality)
    _add_flag(lambda q: q["parsed_value"] == 0.0, "VALUE_MISSING_SENTINEL")(broken)
    assert "zero_is_not_missing" in failing(obs, broken)


def test_summary_measures_problems_before_exclusion(layers: tuple[Rows, Rows]) -> None:
    quality, obs = layers
    s = quality_summary(quality, obs, {})
    assert s["validated"]["rows"] == len(quality) == 71  # 61 rainfall + 10 water level rows
    assert s["validated"]["quality_flags"]["VALUE_MISSING_SENTINEL"] == 5
    assert s["canonical"]["usable"] == 66
    assert s["canonical"]["missing_value_flags"] == {"VALUE_MISSING_SENTINEL": 5}
    wl = next(v for v in s["series"].values() if v["sensor_type"] == "WATER_LEVEL")
    assert wl["per_local_date"] == {
        "2026-09-23": {"rows": 10, "usable": 5, "missing_value_rows": 5}
    }
    assert wl["history_cadence"]["absent_slots"] == 0
    assert wl["history_cadence"]["expected_slots"] == 10


def test_checks_and_summary_are_deterministic(layers: tuple[Rows, Rows]) -> None:
    quality, obs = layers
    assert run_checks(obs, quality) == run_checks(copy.deepcopy(obs), copy.deepcopy(quality))
    assert quality_summary(quality, obs, {}) == quality_summary(
        copy.deepcopy(quality), copy.deepcopy(obs), {}
    )


def test_negative_zero_is_not_a_conflict(layers: tuple[Rows, Rows]) -> None:
    """Regression (review): "-0.0" and "0" are the same reading, not NUMERIC_VALUES_DIFFER."""
    quality, _ = layers
    zero = next(q for q in quality if q["parsed_value"] == 0.0)
    again = {**zero, "ingestion_batch_id": "z", "parsed_value": -0.0, "value_raw": "-0.0"}
    obs, _ = build_observations([*quality, again])
    [o] = [x for x in obs if x["duplicate_count"] == 2]
    assert o["duplicate_status"] == "IDENTICAL"
    assert {p["value_signature"] for p in o["provenance"]} == {"NUMERIC:0.0"}
