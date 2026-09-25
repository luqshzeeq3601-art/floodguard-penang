"""Resolve published source station IDs to FloodGuard IDs using a station-master build.

The single resolver for both the raw layer (``resolve``: ``fg_sensor_id`` or a quarantine reason
at ingest time) and the derived station-ID layer (``lookup``: full status, ``fg_site_id`` and
``fg_sensor_id``; ``floodguard.preprocessing.station_ids``). Identity rules live in
``floodguard.station_master`` only (docs/STATION_MASTER_DESIGN.md): the lookup key is (source,
whitespace-stripped ``jps_internal_id``, sensor type). Every loaded ``fg_sensor_id`` is re-derived
with ``station_master.sensor_id`` and every ``fg_site_id`` must be that key's canonical or review
site ID, so a stale, hand-edited or inconsistent file is rejected at load time instead of silently
mis-mapping. Unknown IDs are never invented, and names, coordinates and display IDs are never read.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from floodguard.ingestion.contracts import QuarantineReason
from floodguard.station_master import (
    SCHEMA_VERSION,
    SensorType,
    StationMasterError,
    normalise_source_id,
    review_site_id,
    sensor_id,
    site_id,
)

# Local-only real build (JPS data is PERMISSION REQUIRED; data/local/ is git-ignored).
DEFAULT_SENSORS_CSV = Path("data/local/station_master/sensors.csv")
REQUIRED_COLUMNS = (
    "fg_sensor_id",
    "fg_site_id",
    "sensor_type",
    "source",
    "jps_internal_id",
    "fg_schema_version",
)


class StationMappingError(ValueError):
    """The station-master file is missing, malformed or inconsistent with the ID rules."""


class IdMappingStatus(StrEnum):
    MAPPED = "MAPPED"
    UNMAPPED = "UNMAPPED"  # no sensor of any type for (source, key) in this master
    SENSOR_TYPE_MISMATCH = "SENSOR_TYPE_MISMATCH"  # key known, but not for this sensor type
    INVALID_SOURCE_ID = "INVALID_SOURCE_ID"  # absent, blank, or inner whitespace
    INVALID_SENSOR_TYPE = "INVALID_SENSOR_TYPE"  # absent or not a station_master.SensorType


@dataclass(frozen=True)
class Lookup:
    status: IdMappingStatus
    lookup_key: str | None  # normalise_source_id(raw); None when the raw ID is unusable
    fg_site_id: str | None
    fg_sensor_id: str | None
    reason: str | None  # None only when MAPPED


@dataclass(frozen=True)
class Resolution:
    fg_sensor_id: str | None
    reason: QuarantineReason | None
    detail: str | None


def _sensor_type(value: str | None) -> SensorType | None:
    return next((t for t in SensorType if t.value == value), None)


class SensorMapper:
    def __init__(
        self, sensors: dict[tuple[str, str, SensorType], tuple[str, str]], origin: str
    ) -> None:
        self._sensors = sensors  # (source, key, type) -> (fg_sensor_id, fg_site_id)
        self._keys = {(src, key) for src, key, _ in sensors}
        self.sources = frozenset(src for src, _ in self._keys)
        self.origin = origin

    @classmethod
    def from_csv(cls, path: Path) -> SensorMapper:
        """Load and verify a ``sensors.csv``. Any inconsistency is a hard error (fail closed)."""
        if not path.is_file():
            raise StationMappingError(f"station master sensors file not found: {path}")
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise StationMappingError(f"{path}: missing columns {missing}")
            rows = list(reader)
        sensors: dict[tuple[str, str, SensorType], tuple[str, str]] = {}
        for n, r in enumerate(rows, 2):
            if r["fg_schema_version"] != SCHEMA_VERSION:
                raise StationMappingError(f"{path}:{n}: schema {r['fg_schema_version']!r}")
            try:
                st = SensorType(r["sensor_type"])
                key = normalise_source_id(r["jps_internal_id"])
            except (ValueError, StationMasterError) as e:
                raise StationMappingError(f"{path}:{n}: {e}") from e
            src = r["source"]
            if sensor_id(src, key, st) != r["fg_sensor_id"]:
                raise StationMappingError(f"{path}:{n}: fg_sensor_id does not match ID rules")
            # Site IDs also derive from the key, so this check also rules out >1 sensor of a
            # type per site and a sensor attached to another key's site.
            if r["fg_site_id"] not in (site_id(src, key), review_site_id(src, key, st)):
                raise StationMappingError(f"{path}:{n}: fg_site_id does not match ID rules")
            if (src, key, st) in sensors:
                raise StationMappingError(f"{path}:{n}: duplicate sensor {key!r} {st}")
            sensors[(src, key, st)] = (r["fg_sensor_id"], r["fg_site_id"])
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        return cls(sensors, f"{path.name}@sha256:{digest}")  # no local path in records

    def lookup(self, source: str, source_station_id: str | None, sensor_type: str | None) -> Lookup:
        """Map one published ID by (source, key, sensor type) only. Never guesses."""
        if source_station_id is None:
            return Lookup(IdMappingStatus.INVALID_SOURCE_ID, None, None, None, "source ID absent")
        try:
            key = normalise_source_id(source_station_id)
        except StationMasterError as e:
            return Lookup(IdMappingStatus.INVALID_SOURCE_ID, None, None, None, str(e))
        st = _sensor_type(sensor_type)
        if st is None:
            why = "sensor type absent" if sensor_type is None else f"unknown {sensor_type!r}"
            return Lookup(IdMappingStatus.INVALID_SENSOR_TYPE, key, None, None, why)
        hit = self._sensors.get((source, key, st))
        if hit is not None:
            return Lookup(IdMappingStatus.MAPPED, key, hit[1], hit[0], None)
        where = f"{source} key {key!r} in {self.origin}"
        if (source, key) in self._keys:
            return Lookup(
                IdMappingStatus.SENSOR_TYPE_MISMATCH, key, None, None, f"no {st} sensor for {where}"
            )
        return Lookup(IdMappingStatus.UNMAPPED, key, None, None, f"no sensor for {where}")

    def resolve(self, source: str, source_station_id: str | None, sensor_type: str) -> Resolution:
        """Raw-layer view of ``lookup``: ``fg_sensor_id`` or a quarantine reason."""
        res = self.lookup(source, source_station_id, sensor_type)
        if res.status is IdMappingStatus.MAPPED:
            return Resolution(res.fg_sensor_id, None, None)
        if res.status is IdMappingStatus.INVALID_SOURCE_ID:
            return Resolution(None, QuarantineReason.INVALID_SOURCE_ID, res.reason)
        if res.status is IdMappingStatus.INVALID_SENSOR_TYPE:  # adapter contract violation
            raise StationMappingError(f"adapter produced invalid sensor type: {res.reason}")
        return Resolution(
            None,
            QuarantineReason.UNMAPPED_SENSOR,
            f"no {sensor_type} sensor for {source} key {res.lookup_key!r} in {self.origin}",
        )
