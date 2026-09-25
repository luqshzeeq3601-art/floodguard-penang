"""Offline tests for floodguard.station_master and scripts/build_station_master.py.

All fixtures under tests/fixtures/station_master/ are SYNTHETIC (see its README). One test reads
the tracked JPS inventories and asserts aggregate invariants only. Nothing here reads the
git-ignored local build output (data/local/).
"""

from __future__ import annotations

import importlib.util
import sys
import uuid
from collections import Counter
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest

from floodguard import station_master as sm
from floodguard.station_master import (
    Flag,
    SensorEvidence,
    SensorType,
    StationMaster,
    StationMasterError,
    ThresholdEvidence,
    ThresholdSource,
    ThresholdType,
)

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "station_master"


def _load_script() -> ModuleType:
    path = ROOT / "scripts" / "build_station_master.py"
    spec = importlib.util.spec_from_file_location("build_station_master", path)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


bsm = _load_script()


def _sensors() -> list[SensorEvidence]:
    rf: list[SensorEvidence] = bsm.load_sensor_evidence(
        FIX / "synthetic_rainfall.csv", SensorType.RAINFALL
    )
    wl: list[SensorEvidence] = bsm.load_sensor_evidence(
        FIX / "synthetic_water_level.csv", SensorType.WATER_LEVEL
    )
    return rf + wl


def _coords() -> list[sm.CoordinateEvidence]:
    coords: list[sm.CoordinateEvidence] = bsm.load_coordinates(FIX / "synthetic_coordinates.csv")
    return coords


def _master(
    sensors: list[SensorEvidence] | None = None,
    coords: list[sm.CoordinateEvidence] | None = None,
) -> StationMaster:
    return sm.build_station_master(
        _sensors() if sensors is None else sensors, _coords() if coords is None else coords
    )


def _sites_for(master: StationMaster, key: str) -> list[sm.SiteRecord]:
    return [s for s in master.sites if s.fg_source_site_key == key]


def _sensors_for(master: StationMaster, key: str) -> list[sm.SensorRecord]:
    return [s for s in master.sensors if s.jps_internal_id.strip() == key]


# ---------------------------------------------------------------- deterministic identity


def test_namespace_and_id_algorithm_are_pinned() -> None:
    assert uuid.uuid5(uuid.NAMESPACE_URL, "urn:floodguard-penang:station-master") == (
        sm.FG_NAMESPACE
    )
    # Literal values: any change to the key recipe must fail here, not silently re-key data.
    assert sm.site_id(sm.SOURCE_JPS, "SYN001") == "e92e57cd-306b-5067-a757-b78cee051191"
    assert (
        sm.sensor_id(sm.SOURCE_JPS, "SYN001", SensorType.WATER_LEVEL)
        == "4c2f443b-168a-54a1-88f8-83b2930ebff3"
    )


def test_ids_stable_across_runs() -> None:
    a, b = _master(), _master()
    assert [s.fg_site_id for s in a.sites] == [s.fg_site_id for s in b.sites]
    assert [s.fg_sensor_id for s in a.sensors] == [s.fg_sensor_id for s in b.sensors]


def test_ids_independent_of_names_and_timestamps() -> None:
    later = timedelta(days=400)
    renamed = [
        replace(e, station_name=f"Renamed {i}", discovered_at=e.discovered_at + later)
        for i, e in enumerate(_sensors())
    ]
    coords = [
        replace(c, station_name="Renamed", retrieved_at=c.retrieved_at + later) for c in _coords()
    ]
    a, b = _master(), _master(renamed, coords)
    assert {s.fg_site_id for s in a.sites} == {s.fg_site_id for s in b.sites}
    assert {s.fg_sensor_id for s in a.sensors} == {s.fg_sensor_id for s in b.sensors}


def test_adding_a_sensor_type_later_keeps_existing_ids() -> None:
    rf_only = [e for e in _sensors() if e.sensor_type is SensorType.RAINFALL]
    before, after = _master(rf_only), _master()
    old = _sites_for(before, "SYN001")[0]
    new = _sites_for(after, "SYN001")[0]
    assert old.fg_site_id == new.fg_site_id
    rf_before = _sensors_for(before, "SYN001")[0].fg_sensor_id
    assert rf_before in {s.fg_sensor_id for s in _sensors_for(after, "SYN001")}


def test_golden_output_matches_synthetic_expected(tmp_path: Path) -> None:
    master, thresholds = bsm.build(
        FIX / "synthetic_rainfall.csv",
        FIX / "synthetic_water_level.csv",
        FIX / "synthetic_coordinates.csv",
        FIX / "synthetic_threshold_comparison.md",
    )
    bsm.write_outputs(tmp_path, master, thresholds)
    for name in ("sites.csv", "sensors.csv", "thresholds.csv"):
        assert (tmp_path / name).read_bytes() == (FIX / "expected" / name).read_bytes(), name


# ---------------------------------------------------------------- source identifiers


@pytest.mark.parametrize("raw", ["", "   ", "A B", "\t"])
def test_normalise_rejects_unusable_ids(raw: str) -> None:
    with pytest.raises(StationMasterError):
        sm.normalise_source_id(raw)


def test_whitespace_id_joins_feed_and_keeps_raw_value() -> None:
    assert sm.normalise_source_id(" SYN005_") == "SYN005_"
    master = _master()
    (site,) = _sites_for(master, "SYN005_")
    (sensor,) = _sensors_for(master, "SYN005_")
    assert Flag.WHITESPACE_NORMALISED_SOURCE_ID in site.fg_quality_flags
    assert sensor.jps_internal_id == " SYN005_"  # verbatim source value
    assert site.latitude  # joined to the feed record "SYN005_"
    assert site.fg_site_id == sm.site_id(sm.SOURCE_JPS, "SYN005_")


def test_case_is_not_folded() -> None:
    assert sm.site_id(sm.SOURCE_JPS, "ABC") != sm.site_id(sm.SOURCE_JPS, "abc")


def test_duplicate_source_id_within_one_listing_is_rejected() -> None:
    rf = next(e for e in _sensors() if e.jps_internal_id == "SYN001")
    with pytest.raises(StationMasterError, match="duplicate RAINFALL"):
        _master([*_sensors(), replace(rf, station_name="Other")])


def test_whitespace_variant_duplicate_within_one_listing_is_rejected() -> None:
    rf = next(e for e in _sensors() if e.jps_internal_id == "SYN001")
    with pytest.raises(StationMasterError, match="duplicate RAINFALL"):
        _master([*_sensors(), replace(rf, jps_internal_id=" SYN001")])


def test_feed_source_id_collision_withholds_coordinates() -> None:
    (site,) = _sites_for(_master(), "SYN002")
    assert Flag.SOURCE_ID_COLLISION in site.fg_quality_flags
    assert Flag.MISSING_COORDINATES in site.fg_quality_flags
    assert site.latitude == site.longitude == ""


def test_generated_id_collision_is_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sm, "site_id", lambda source, key: "00000000-0000-5000-8000-000000000000")
    with pytest.raises(StationMasterError, match="duplicate fg_site_id"):
        _master()


def test_missing_and_duplicate_display_ids_flagged() -> None:
    m = _master()
    flags = {s.jps_internal_id: s.fg_quality_flags for s in m.sensors}
    assert flags["SYN004"] == (Flag.MISSING_DISPLAY_ID,)  # "No Data"
    assert flags[" SYN005_"] == (Flag.MISSING_DISPLAY_ID,)  # blank
    assert flags["SYN002"] == flags["SYN003"] == (Flag.DUPLICATE_DISPLAY_ID,)
    display = {s.jps_internal_id: s.jps_display_station_id for s in m.sensors}
    assert display["SYN004"] == "No Data"  # raw preserved


# ---------------------------------------------------------------- merge and ambiguity


def test_shared_id_with_matching_evidence_becomes_one_site() -> None:
    m = _master()
    (site,) = _sites_for(m, "SYN001")
    sensors = _sensors_for(m, "SYN001")
    assert {s.sensor_type for s in sensors} == set(SensorType)
    assert {s.fg_site_id for s in sensors} == {site.fg_site_id}
    assert Flag.AMBIGUOUS_SITE_MAPPING not in site.fg_quality_flags


def test_district_mismatch_keeps_sites_separate_and_flags() -> None:
    m = _master()
    sites = _sites_for(m, "SYN007")
    assert len(sites) == 2
    assert all(Flag.AMBIGUOUS_SITE_MAPPING in s.fg_quality_flags for s in sites)
    by_type = {s.sensor_type: s.fg_site_id for s in _sensors_for(m, "SYN007")}
    assert by_type[SensorType.RAINFALL] == sm.site_id(sm.SOURCE_JPS, "SYN007")
    assert by_type[SensorType.WATER_LEVEL] == sm.review_site_id(
        sm.SOURCE_JPS, "SYN007", SensorType.WATER_LEVEL
    )


def test_basin_mismatch_keeps_sites_separate() -> None:
    sensors = [
        replace(e, sub_basin="Sg. Lain")
        if e.jps_internal_id == "SYN001" and e.sensor_type is SensorType.WATER_LEVEL
        else e
        for e in _sensors()
    ]
    sites = _sites_for(_master(sensors), "SYN001")
    assert len(sites) == 2
    assert all(Flag.AMBIGUOUS_SITE_MAPPING in s.fg_quality_flags for s in sites)


def test_coordinate_mismatch_from_duplicate_feed_records_keeps_shared_id_separate() -> None:
    extra = replace(
        next(c for c in _coords() if c.jps_internal_id == "SYN001"), latitude="5.499999"
    )
    sites = _sites_for(_master(coords=[*_coords(), extra]), "SYN001")
    assert len(sites) == 2
    assert all(
        {Flag.AMBIGUOUS_SITE_MAPPING, Flag.SOURCE_ID_COLLISION} <= set(s.fg_quality_flags)
        for s in sites
    )


def test_shared_id_without_official_coordinates_is_not_merged() -> None:
    sites = _sites_for(_master(), "SYN011")
    assert len(sites) == 2
    assert all(Flag.AMBIGUOUS_SITE_MAPPING in s.fg_quality_flags for s in sites)


def test_same_name_different_id_is_never_merged() -> None:
    sensors = [
        replace(e, station_name="Same Name") if e.jps_internal_id in {"SYN009", "SYN010"} else e
        for e in _sensors()
    ]
    m = _master(sensors)
    assert len(_sites_for(m, "SYN009")) == len(_sites_for(m, "SYN010")) == 1
    assert all(
        Flag.COLOCATED_WITH_OTHER_SITE in s.fg_quality_flags
        for key in ("SYN009", "SYN010")
        for s in _sites_for(m, key)
    )


def test_feed_sensor_types_mismatch_flagged() -> None:
    (site,) = _sites_for(_master(), "SYN006")
    assert Flag.SENSOR_TYPES_SOURCE_MISMATCH in site.fg_quality_flags


# ---------------------------------------------------------------- cardinality and validation


def test_every_sensor_has_exactly_one_existing_site() -> None:
    m = _master()
    site_ids = [s.fg_site_id for s in m.sites]
    assert len(site_ids) == len(set(site_ids))
    assert all(s.fg_site_id in site_ids for s in m.sensors)
    assert set(site_ids) == {s.fg_site_id for s in m.sensors}  # no empty site
    assert max(Counter((s.fg_site_id, s.sensor_type) for s in m.sensors).values()) == 1


def test_validator_rejects_orphan_sensor_and_empty_site() -> None:
    m = _master()
    orphan = replace(m.sensors[0], fg_site_id="not-a-site")
    with pytest.raises(StationMasterError, match="unknown site"):
        sm.validate_station_master(replace(m, sensors=(orphan, *m.sensors[1:])))
    with pytest.raises(StationMasterError, match="no sensor"):
        sm.validate_station_master(
            replace(m, sensors=tuple(s for s in m.sensors if s.jps_internal_id != "SYN003"))
        )


def test_validator_rejects_naive_timestamp() -> None:
    m = _master()
    naive = replace(m.sites[0], fg_first_seen_at=datetime(2000, 1, 1))  # noqa: DTZ001
    with pytest.raises(StationMasterError, match="naive"):
        sm.validate_station_master(replace(m, sites=(naive, *m.sites[1:])))


# ---------------------------------------------------------------- thresholds


def _thresholds() -> tuple[StationMaster, tuple[sm.ThresholdRecord, ...]]:
    result: tuple[StationMaster, tuple[sm.ThresholdRecord, ...]] = bsm.build(
        FIX / "synthetic_rainfall.csv",
        FIX / "synthetic_water_level.csv",
        FIX / "synthetic_coordinates.csv",
        FIX / "synthetic_threshold_comparison.md",
    )
    return result


def test_thresholds_link_only_to_water_level_sensors() -> None:
    m, ts = _thresholds()
    types = {s.fg_sensor_id: s.sensor_type for s in m.sensors}
    assert ts
    assert {types[t.fg_sensor_id] for t in ts} == {SensorType.WATER_LEVEL}
    rainfall_ids = {i for i, t in types.items() if t is SensorType.RAINFALL}
    assert not rainfall_ids & {t.fg_sensor_id for t in ts}


def test_rainfall_only_site_cannot_receive_threshold() -> None:
    m = _master()
    ev = ThresholdEvidence(
        jps_internal_id="SYN003",
        threshold_type=ThresholdType.WASPADA,
        value_raw="1.00",
        source=ThresholdSource.JPS_NATIONAL_LISTING,
        source_url="https://example.invalid",
        captured_at=datetime.fromisoformat("2000-01-01T00:00:00+08:00"),
        provenance="synthetic",
    )
    with pytest.raises(StationMasterError, match="no WATER_LEVEL sensor"):
        sm.build_thresholds(m, [ev])


def test_validator_rejects_threshold_on_rainfall_sensor() -> None:
    m, ts = _thresholds()
    rf = next(s for s in m.sensors if s.sensor_type is SensorType.RAINFALL)
    with pytest.raises(StationMasterError, match="RAINFALL"):
        sm.validate_thresholds(m, [replace(ts[0], fg_sensor_id=rf.fg_sensor_id)])


def test_normal_is_never_label_eligible() -> None:
    _, ts = _thresholds()
    assert all(t.fg_label_eligible is (t.threshold_type is not ThresholdType.NORMAL) for t in ts)


def test_threshold_conflict_flags_both_sources_only_for_differing_type() -> None:
    _, ts = _thresholds()
    wl = sm.sensor_id(sm.SOURCE_JPS, "SYN001", SensorType.WATER_LEVEL)
    flagged = {
        (t.threshold_source, t.threshold_type)
        for t in ts
        if t.fg_sensor_id == wl and Flag.THRESHOLD_PROVENANCE_CONFLICT in t.fg_quality_flags
    }
    assert flagged == {
        (ThresholdSource.JPS_NATIONAL_LISTING, ThresholdType.AMARAN),
        (ThresholdSource.JPS_PENANG_PORTAL, ThresholdType.AMARAN),
    }
    assert not any(
        Flag.THRESHOLD_PROVENANCE_CONFLICT in t.fg_quality_flags for t in ts if t.fg_sensor_id != wl
    )


def test_threshold_ids_version_by_capture_time() -> None:
    wl = sm.sensor_id(sm.SOURCE_JPS, "SYN001", SensorType.WATER_LEVEL)
    t0 = datetime.fromisoformat("2000-01-01T00:00:00+08:00")
    args = (wl, ThresholdSource.JPS_NATIONAL_LISTING, ThresholdType.WASPADA)
    assert sm.threshold_id(*args, t0) == sm.threshold_id(*args, t0)
    assert sm.threshold_id(*args, t0) != sm.threshold_id(*args, t0 + timedelta(days=1))


def test_stale_comparison_table_is_rejected() -> None:
    national = bsm.national_thresholds(FIX / "synthetic_water_level.csv")
    text = (FIX / "synthetic_threshold_comparison.md").read_text(encoding="utf-8")
    with pytest.raises(StationMasterError, match="disagrees"):
        bsm.penang_thresholds(
            text.replace("| 2.00 / 2.50 / 3.00 |", "| 2.10 / 2.50 / 3.00 |"), national, "x"
        )


# ---------------------------------------------------------------- tracked real inventories


def test_tracked_inventories_aggregate_invariants() -> None:
    """Aggregates only; reads tracked CSVs/docs, never data/local/."""
    master, thresholds = bsm.build(
        bsm.RAINFALL_CSV, bsm.WATER_LEVEL_CSV, bsm.COORDINATES_CSV, bsm.PENANG_THRESHOLD_DOC
    )
    s = bsm.summary(master, thresholds)
    assert (s["sites"], s["sensors_rainfall"], s["sensors_water_level"]) == (65, 56, 22)
    assert (s["sites_multi_sensor"], s["sites_rainfall_only"], s["sites_water_level_only"]) == (
        13,
        43,
        9,
    )
    assert s["ambiguous_source_keys"] == []
    assert s["thresholds_by_source_type"]["JPS_NATIONAL_LISTING:NORMAL"] == 22
    assert s["sensors_with_threshold_conflict"] == 3
    assert "MISSING_COORDINATES" not in s["flags"]
