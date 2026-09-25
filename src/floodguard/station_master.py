"""Station master: FloodGuard site / sensor / threshold identity for JPS stations.

Pure, offline logic (no I/O, no network). Design and rules: docs/STATION_MASTER_DESIGN.md.

- A *site* is a monitoring location; a *sensor* is one measurement type at a site (1..n per site).
- ``jps_internal_id`` / ``jps_display_station_id`` are source identifiers only, never keys.
- Every ``fg_*_id`` is a UUIDv5 under a pinned namespace, derived only from the source name, the
  normalised source key and the sensor/threshold type, never from names, readings or times
  (threshold IDs also include the capture time, which versions them).
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

SCHEMA_VERSION = "station_master/v1"
SOURCE_JPS = "JPS_PUBLIC_INFOBANJIR"
# Pinned forever: uuid5(NAMESPACE_URL, "urn:floodguard-penang:station-master").
FG_NAMESPACE = uuid.UUID("ea5bad5b-553a-52a4-b428-73d204244a21")
MISSING_DISPLAY_TEXT = frozenset({"", "no data"})
# LIVE_ACCESS.md: "(F2)" stations publish every 15 min; other stations have no verified cadence.
F2_MARKER = "(F2)"
F2_LISTING_INTERVAL_MINUTES = 15


class SensorType(StrEnum):
    RAINFALL = "RAINFALL"
    WATER_LEVEL = "WATER_LEVEL"


MEASUREMENT: dict[SensorType, tuple[str, str]] = {
    SensorType.RAINFALL: ("rainfall", "mm"),
    SensorType.WATER_LEVEL: ("water_level", "m"),
}


class ThresholdType(StrEnum):
    """JPS "Tahap Nilai Ambang" terms, kept in Malay as published."""

    NORMAL = "NORMAL"
    WASPADA = "WASPADA"
    AMARAN = "AMARAN"
    BAHAYA = "BAHAYA"


# NORMAL is 0.00 on 14/22 stations and behaves like a reference offset: never a label level.
LABEL_ELIGIBLE_THRESHOLDS = frozenset(
    {ThresholdType.WASPADA, ThresholdType.AMARAN, ThresholdType.BAHAYA}
)


class ThresholdSource(StrEnum):
    JPS_NATIONAL_LISTING = "JPS_NATIONAL_LISTING"
    JPS_PENANG_PORTAL = "JPS_PENANG_PORTAL"


class Flag(StrEnum):
    MISSING_DISPLAY_ID = "MISSING_DISPLAY_ID"
    DUPLICATE_DISPLAY_ID = "DUPLICATE_DISPLAY_ID"
    AMBIGUOUS_SITE_MAPPING = "AMBIGUOUS_SITE_MAPPING"
    CRS_INFERRED = "CRS_INFERRED"
    MISSING_COORDINATES = "MISSING_COORDINATES"
    SOURCE_ID_COLLISION = "SOURCE_ID_COLLISION"
    WHITESPACE_NORMALISED_SOURCE_ID = "WHITESPACE_NORMALISED_SOURCE_ID"
    MISSING_BASIN = "MISSING_BASIN"
    SENSOR_TYPES_SOURCE_MISMATCH = "SENSOR_TYPES_SOURCE_MISMATCH"
    COLOCATED_WITH_OTHER_SITE = "COLOCATED_WITH_OTHER_SITE"
    THRESHOLD_PROVENANCE_CONFLICT = "THRESHOLD_PROVENANCE_CONFLICT"


class StationMasterError(ValueError):
    """Identity cannot be derived safely; the build must stop."""


# ---------------------------------------------------------------- inputs (source evidence)


@dataclass(frozen=True)
class SensorEvidence:
    """One row of a JPS state listing (rainfall or water-level inventory), verbatim."""

    sensor_type: SensorType
    jps_internal_id: str
    jps_display_station_id: str
    station_name: str
    state: str
    district: str
    main_basin: str | None  # None: the listing has no basin column (rainfall)
    sub_basin: str | None
    source_url: str
    discovered_at: datetime


@dataclass(frozen=True)
class CoordinateEvidence:
    """One official map-feed record (``penang_station_coordinates_jps.csv``), verbatim."""

    jps_internal_id: str
    station_name: str
    state: str
    district: str
    main_basin: str
    sub_basin: str
    sensor_types: frozenset[SensorType]
    latitude: str
    longitude: str
    crs_declared: bool
    source_url: str
    retrieved_at: datetime


@dataclass(frozen=True)
class ThresholdEvidence:
    jps_internal_id: str
    threshold_type: ThresholdType
    value_raw: str
    source: ThresholdSource
    source_url: str
    captured_at: datetime
    provenance: str


# ---------------------------------------------------------------- outputs (station master)


@dataclass(frozen=True)
class SiteRecord:
    fg_site_id: str
    fg_source_site_key: str
    source: str
    jps_internal_id: str
    fg_site_name: str
    jps_map_feed_name: str
    state: str
    district: str
    latitude: str
    longitude: str
    coordinate_source: str
    fg_crs_assumption: str
    main_basin: str
    sub_basin: str
    fg_first_seen_at: datetime
    fg_last_verified_at: datetime
    fg_quality_flags: tuple[Flag, ...]
    fg_schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class SensorRecord:
    fg_sensor_id: str
    fg_site_id: str
    sensor_type: SensorType
    source: str
    jps_internal_id: str
    jps_display_station_id: str
    jps_sensor_name: str
    measurement_type: str
    unit: str
    fg_expected_listing_interval_minutes: int | None
    source_url: str
    fg_first_seen_at: datetime
    fg_last_verified_at: datetime
    fg_quality_flags: tuple[Flag, ...]
    fg_schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class ThresholdRecord:
    fg_threshold_id: str
    fg_sensor_id: str
    threshold_type: ThresholdType
    value: Decimal
    value_raw: str
    unit: str
    threshold_source: ThresholdSource
    source_url: str
    captured_at: datetime
    valid_from: datetime | None  # JPS publishes no validity period
    source_verified_at: datetime
    provenance: str
    fg_label_eligible: bool
    fg_quality_flags: tuple[Flag, ...]
    fg_schema_version: str = SCHEMA_VERSION


@dataclass(frozen=True)
class StationMaster:
    sites: tuple[SiteRecord, ...]
    sensors: tuple[SensorRecord, ...]


# ---------------------------------------------------------------- identity


def normalise_source_id(raw: str) -> str:
    """Key-derivation form of a JPS source ID: outer whitespace stripped, nothing else.

    Case is kept (JPS IDs such as ``LIMBUNGAN`` may be case-sensitive); the raw value is always
    stored separately and a changed value is flagged ``WHITESPACE_NORMALISED_SOURCE_ID``.
    """
    key = raw.strip()
    if not key or any(ch.isspace() for ch in key):
        raise StationMasterError(f"unusable source ID {raw!r}")
    return key


def _uuid(name: str) -> str:
    return str(uuid.uuid5(FG_NAMESPACE, name))


def site_id(source: str, source_site_key: str) -> str:
    return _uuid(f"site/v1|{source}|{source_site_key}")


def review_site_id(source: str, source_site_key: str, sensor_type: SensorType) -> str:
    """Separate site for a sensor whose site evidence disagrees (manual review pending)."""
    return _uuid(f"site/v1|{source}|{source_site_key}|review|{sensor_type}")


def sensor_id(source: str, source_site_key: str, sensor_type: SensorType) -> str:
    """Independent of site assignment, so resolving a review keeps the sensor's identity."""
    return _uuid(f"sensor/v1|{source}|{source_site_key}|{sensor_type}")


def threshold_id(
    fg_sensor_id: str, source: ThresholdSource, threshold_type: ThresholdType, captured_at: datetime
) -> str:
    return _uuid(f"threshold/v1|{fg_sensor_id}|{source}|{threshold_type}|{captured_at.isoformat()}")


def is_missing_display_id(raw: str) -> bool:
    return raw.strip().casefold() in MISSING_DISPLAY_TEXT


# ---------------------------------------------------------------- build


def _site_evidence_matches(ev: SensorEvidence, coord: CoordinateEvidence) -> bool:
    """Merge evidence: exact state (case-insensitive), district and, where listed, basin."""
    if ev.state.strip().casefold() != coord.state.strip().casefold():
        return False
    if ev.district.strip() != coord.district.strip():
        return False
    if ev.main_basin is not None and ev.main_basin.strip() != coord.main_basin.strip():
        return False
    return ev.sub_basin is None or ev.sub_basin.strip() == coord.sub_basin.strip()


def _sensor_record(
    ev: SensorEvidence, key: str, fg_site: str, flags: Iterable[Flag]
) -> SensorRecord:
    measurement, unit = MEASUREMENT[ev.sensor_type]
    cadence = F2_LISTING_INTERVAL_MINUTES if F2_MARKER in ev.station_name else None
    return SensorRecord(
        fg_sensor_id=sensor_id(SOURCE_JPS, key, ev.sensor_type),
        fg_site_id=fg_site,
        sensor_type=ev.sensor_type,
        source=SOURCE_JPS,
        jps_internal_id=ev.jps_internal_id,
        jps_display_station_id=ev.jps_display_station_id,
        jps_sensor_name=ev.station_name,
        measurement_type=measurement,
        unit=unit,
        fg_expected_listing_interval_minutes=cadence,
        source_url=ev.source_url,
        fg_first_seen_at=ev.discovered_at,
        fg_last_verified_at=ev.discovered_at,
        fg_quality_flags=tuple(sorted(set(flags))),
    )


def _site_record(
    fg_site: str,
    key: str,
    evs: Sequence[SensorEvidence],
    coord: CoordinateEvidence | None,
    flags: set[Flag],
) -> SiteRecord:
    first = min(evs, key=lambda e: e.sensor_type)  # RAINFALL before WATER_LEVEL: deterministic
    wl = next((e for e in evs if e.sensor_type is SensorType.WATER_LEVEL), None)
    times = [e.discovered_at for e in evs] + ([coord.retrieved_at] if coord else [])
    if coord is not None:
        main_basin, sub_basin = coord.main_basin.strip(), coord.sub_basin.strip()
    elif wl is not None:
        main_basin, sub_basin = (wl.main_basin or "").strip(), (wl.sub_basin or "").strip()
    else:
        main_basin = sub_basin = ""
    if not main_basin or not sub_basin:
        flags.add(Flag.MISSING_BASIN)
    if coord is None:
        flags.add(Flag.MISSING_COORDINATES)
    elif not coord.crs_declared:
        flags.add(Flag.CRS_INFERRED)
    raw_ids = {e.jps_internal_id for e in evs} | ({coord.jps_internal_id} if coord else set())
    if any(r != key for r in raw_ids):
        flags.add(Flag.WHITESPACE_NORMALISED_SOURCE_ID)
    name_source = coord.station_name if coord else (wl or first).station_name
    return SiteRecord(
        fg_site_id=fg_site,
        fg_source_site_key=key,
        source=SOURCE_JPS,
        jps_internal_id=coord.jps_internal_id if coord else first.jps_internal_id,
        fg_site_name=" ".join(name_source.split()),
        jps_map_feed_name=coord.station_name if coord else "",
        state=first.state,
        district=first.district,
        latitude=coord.latitude if coord else "",
        longitude=coord.longitude if coord else "",
        coordinate_source=coord.source_url if coord else "",
        fg_crs_assumption=(
            "" if coord is None else "declared" if coord.crs_declared else "EPSG:4326 (inferred)"
        ),
        main_basin=main_basin,
        sub_basin=sub_basin,
        fg_first_seen_at=min(times),
        fg_last_verified_at=max(times),
        fg_quality_flags=tuple(sorted(flags)),
    )


def build_station_master(
    sensors: Sequence[SensorEvidence], coordinates: Sequence[CoordinateEvidence]
) -> StationMaster:
    """Group listing rows into sites by normalised ``jps_internal_id`` with evidence checks.

    Raises ``StationMasterError`` for a duplicate source key within one listing (identity is
    undefined) and for any generated-ID collision.
    """
    by_key: dict[str, list[SensorEvidence]] = defaultdict(list)
    for ev in sensors:
        key = normalise_source_id(ev.jps_internal_id)
        if any(o.sensor_type is ev.sensor_type for o in by_key[key]):
            raise StationMasterError(
                f"duplicate {ev.sensor_type} source ID {ev.jps_internal_id!r} (key {key!r})"
            )
        by_key[key].append(ev)

    coord_groups: dict[str, list[CoordinateEvidence]] = defaultdict(list)
    for c in coordinates:
        coord_groups[normalise_source_id(c.jps_internal_id)].append(c)

    display_counts = Counter(
        (ev.sensor_type, ev.jps_display_station_id.strip())
        for ev in sensors
        if not is_missing_display_id(ev.jps_display_station_id)
    )

    def sensor_flags(ev: SensorEvidence) -> set[Flag]:
        disp = ev.jps_display_station_id
        if is_missing_display_id(disp):
            return {Flag.MISSING_DISPLAY_ID}
        if display_counts[(ev.sensor_type, disp.strip())] > 1:
            return {Flag.DUPLICATE_DISPLAY_ID}
        return set()

    sites: list[SiteRecord] = []
    out_sensors: list[SensorRecord] = []
    for key in sorted(by_key):
        evs = sorted(by_key[key], key=lambda e: e.sensor_type)
        candidates = coord_groups.get(key, [])
        collided = len(candidates) > 1
        coord = candidates[0] if len(candidates) == 1 else None
        if coord is not None:
            attached = [e for e in evs if _site_evidence_matches(e, coord)]
        else:  # no single official anchor: only an unshared ID is unambiguous
            attached = evs if len(evs) == 1 else []
        review = [e for e in evs if e not in attached]

        base_flags: set[Flag] = set()
        if collided:
            base_flags.add(Flag.SOURCE_ID_COLLISION)
        if review:
            base_flags.add(Flag.AMBIGUOUS_SITE_MAPPING)
        if attached:
            fg_site = site_id(SOURCE_JPS, key)
            flags = set(base_flags)
            if coord is not None and coord.sensor_types != {e.sensor_type for e in evs}:
                flags.add(Flag.SENSOR_TYPES_SOURCE_MISMATCH)
            sites.append(_site_record(fg_site, key, attached, coord, flags))
            out_sensors.extend(_sensor_record(e, key, fg_site, sensor_flags(e)) for e in attached)
        for e in review:
            fg_site = review_site_id(SOURCE_JPS, key, e.sensor_type)
            sites.append(_site_record(fg_site, key, [e], None, set(base_flags)))
            out_sensors.append(_sensor_record(e, key, fg_site, sensor_flags(e)))

    _flag_colocated(sites)
    master = StationMaster(tuple(sites), tuple(out_sensors))
    validate_station_master(master)
    return master


def _flag_colocated(sites: list[SiteRecord]) -> None:
    """Distinct source keys at identical official coordinates: never merged, only flagged."""
    points: dict[tuple[str, str], set[str]] = defaultdict(set)
    for s in sites:
        if s.latitude and s.longitude:
            points[(s.latitude.strip(), s.longitude.strip())].add(s.fg_source_site_key)
    for i, s in enumerate(sites):
        if len(points.get((s.latitude.strip(), s.longitude.strip()), ())) > 1:
            flags = tuple(sorted({*s.fg_quality_flags, Flag.COLOCATED_WITH_OTHER_SITE}))
            sites[i] = replace(s, fg_quality_flags=flags)


def build_thresholds(
    master: StationMaster, evidence: Sequence[ThresholdEvidence]
) -> tuple[ThresholdRecord, ...]:
    """Versioned threshold records, linked to WATER_LEVEL sensors only.

    Values that differ between sources for the same sensor and type are all flagged
    ``THRESHOLD_PROVENANCE_CONFLICT``; none is dropped or preferred here.
    """
    wl_sensor = {
        normalise_source_id(s.jps_internal_id): s.fg_sensor_id
        for s in master.sensors
        if s.sensor_type is SensorType.WATER_LEVEL
    }
    parsed: list[tuple[ThresholdEvidence, str, Decimal]] = []
    for ev in evidence:
        key = normalise_source_id(ev.jps_internal_id)
        if key not in wl_sensor:
            raise StationMasterError(f"threshold for {key!r} has no WATER_LEVEL sensor")
        try:
            value = Decimal(ev.value_raw.strip())
        except InvalidOperation as exc:
            raise StationMasterError(f"non-numeric threshold {ev.value_raw!r} ({key})") from exc
        if not value.is_finite():
            raise StationMasterError(f"non-finite threshold {ev.value_raw!r} ({key})")
        parsed.append((ev, wl_sensor[key], value))

    values: dict[tuple[str, ThresholdType], set[Decimal]] = defaultdict(set)
    for ev, sid, value in parsed:
        values[(sid, ev.threshold_type)].add(value)

    records = tuple(
        ThresholdRecord(
            fg_threshold_id=threshold_id(sid, ev.source, ev.threshold_type, ev.captured_at),
            fg_sensor_id=sid,
            threshold_type=ev.threshold_type,
            value=value,
            value_raw=ev.value_raw,
            unit=MEASUREMENT[SensorType.WATER_LEVEL][1],
            threshold_source=ev.source,
            source_url=ev.source_url,
            captured_at=ev.captured_at,
            valid_from=None,
            source_verified_at=ev.captured_at,
            provenance=ev.provenance,
            fg_label_eligible=ev.threshold_type in LABEL_ELIGIBLE_THRESHOLDS,
            fg_quality_flags=(
                (Flag.THRESHOLD_PROVENANCE_CONFLICT,)
                if len(values[(sid, ev.threshold_type)]) > 1
                else ()
            ),
        )
        for ev, sid, value in parsed
    )
    validate_thresholds(master, records)
    return records


# ---------------------------------------------------------------- validation


def validate_station_master(master: StationMaster) -> None:
    """Structural invariants; raises ``StationMasterError`` listing every violation.

    Grouping makes each source key (and key + sensor type) unique before hashing, so a duplicate
    generated ID can only be a UUIDv5 collision: this check is the collision detector.
    """
    errors: list[str] = []
    site_ids = Counter(s.fg_site_id for s in master.sites)
    sensor_ids = Counter(s.fg_sensor_id for s in master.sensors)
    errors += [f"duplicate fg_site_id {i}" for i, n in site_ids.items() if n > 1]
    errors += [f"duplicate fg_sensor_id {i}" for i, n in sensor_ids.items() if n > 1]
    per_site = Counter(s.fg_site_id for s in master.sensors)
    per_site_type = Counter((s.fg_site_id, s.sensor_type) for s in master.sensors)
    errors += [
        f"sensor {s.fg_sensor_id} has unknown site"
        for s in master.sensors
        if s.fg_site_id not in site_ids
    ]
    errors += [f"site {i} has no sensor" for i in site_ids if per_site[i] == 0]
    errors += [f"site {i} has >1 {t} sensor" for (i, t), n in per_site_type.items() if n > 1]
    records: tuple[SiteRecord | SensorRecord, ...] = (*master.sites, *master.sensors)
    for rec in records:
        if rec.fg_first_seen_at.tzinfo is None or rec.fg_last_verified_at.tzinfo is None:
            errors.append(f"naive timestamp on {rec}")
        elif rec.fg_first_seen_at > rec.fg_last_verified_at:
            errors.append(f"first_seen after last_verified on {rec}")
    for s in master.sites:
        if bool(s.latitude) != bool(s.longitude):
            errors.append(f"site {s.fg_site_id} has half a coordinate")
        if s.latitude and not (
            -90 <= float(s.latitude) <= 90 and -180 <= float(s.longitude) <= 180
        ):
            errors.append(f"site {s.fg_site_id} coordinate out of range")
    if errors:
        raise StationMasterError("; ".join(errors))


def validate_thresholds(master: StationMaster, thresholds: Sequence[ThresholdRecord]) -> None:
    types = {s.fg_sensor_id: s.sensor_type for s in master.sensors}
    errors = [
        f"threshold {t.fg_threshold_id} -> {types.get(t.fg_sensor_id)} sensor"
        for t in thresholds
        if types.get(t.fg_sensor_id) is not SensorType.WATER_LEVEL
    ]
    errors += [
        f"duplicate fg_threshold_id {i}"
        for i, n in Counter(t.fg_threshold_id for t in thresholds).items()
        if n > 1
    ]
    errors += [
        f"NORMAL marked label-eligible ({t.fg_threshold_id})"
        for t in thresholds
        if t.threshold_type is ThresholdType.NORMAL and t.fg_label_eligible
    ]
    if errors:
        raise StationMasterError("; ".join(errors))
