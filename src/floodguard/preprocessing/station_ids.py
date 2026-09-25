"""Station-ID normalisation: a derived layer over raw records.

Policy: docs/STATION_MASTER_DESIGN.md section 12.

Re-resolves every record from its preserved source IDs with the one shared resolver
(``floodguard.ingestion.station_mapping.SensorMapper.lookup``), so the raw layer's ingest-time
``fg_sensor_id`` is treated as provisional and only compared, never copied. Keys are
(source, outer-whitespace-stripped ``jps_internal_id``, sensor type); names, coordinates and
display IDs are never used. Pure and deterministic for a given station-master file; never writes
to the raw store, never drops, merges or deduplicates records, and never invents an ID.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from floodguard.ingestion.station_mapping import IdMappingStatus, SensorMapper

SCHEMA_VERSION = "station_id_normalization/v1"


@dataclass(frozen=True)
class StationIdResult:
    jps_internal_id_raw: str | None  # exactly as in the raw record (whitespace kept)
    jps_display_station_id_raw: str | None  # exactly as in the raw record; never a key
    lookup_key: str | None  # normalise_source_id(jps_internal_id_raw); None when unusable
    sensor_type: str | None  # as supplied by the adapter
    fg_site_id: str | None
    fg_sensor_id: str | None
    station_id_mapping_status: IdMappingStatus
    mapping_reason: str | None  # None only when MAPPED


def resolve_station_ids(
    source: str,
    jps_internal_id_raw: str | None,
    jps_display_station_id_raw: str | None,
    sensor_type: str | None,
    mapper: SensorMapper,
) -> StationIdResult:
    """Map one record's source IDs. The display ID is carried through, never looked up."""
    res = mapper.lookup(source, jps_internal_id_raw, sensor_type)
    return StationIdResult(
        jps_internal_id_raw=jps_internal_id_raw,
        jps_display_station_id_raw=jps_display_station_id_raw,
        lookup_key=res.lookup_key,
        sensor_type=sensor_type,
        fg_site_id=res.fg_site_id,
        fg_sensor_id=res.fg_sensor_id,
        station_id_mapping_status=res.status,
        mapping_reason=res.reason,
    )


def normalize_record(record: Mapping[str, Any], mapper: SensorMapper) -> dict[str, Any]:
    """One derived row for one raw record (``raw_record/v1``); the record is not modified.

    ``raw_fg_sensor_id`` is the ingest-time value. Because sensor IDs are a pure function of
    (source, key, type), it can only differ from ``fg_sensor_id`` by being null on one side (the
    station master gained or lost that sensor); two different non-null IDs are a conflict.
    """
    result = resolve_station_ids(
        record["source"],
        record["source_station_id"],
        record["source_display_station_id"],
        record["sensor_type"],
        mapper,
    )
    return {
        "station_id_schema_version": SCHEMA_VERSION,
        "ingestion_batch_id": record["ingestion_batch_id"],
        "payload_sha256": record["payload_sha256"],
        "source": record["source"],
        "dataset": record["dataset"],
        "source_row_index": record["source_row_index"],
        "measurement_type": record["measurement_type"],
        "station_master_origin": mapper.origin,
        "raw_fg_sensor_id": record["fg_sensor_id"],
        "raw_mapping_status": record["mapping_status"],
        **asdict(result),
    }


def raw_mapping_conflict(row: Mapping[str, Any]) -> bool:
    """True when the raw and derived layers assign two different non-null sensor IDs."""
    raw, derived = row["raw_fg_sensor_id"], row["fg_sensor_id"]
    return raw is not None and derived is not None and raw != derived
