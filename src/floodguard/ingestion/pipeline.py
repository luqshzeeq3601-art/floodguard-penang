"""Run one raw-ingestion batch: bytes -> hash -> idempotency -> parse -> map -> write -> manifest.

Failure semantics (docs/RAW_INGESTION_DESIGN.md):

- same source + dataset + partition + payload SHA-256 already SUCCEEDED -> DUPLICATE entry,
  nothing written;
- any error before or during artifact writing -> FAILED entry, no artifact left behind;
- manifest append fails after artifacts were placed -> those artifacts are removed, FAILED.
"""

from __future__ import annotations

import contextlib
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from floodguard.ingestion import manifest, storage
from floodguard.ingestion.contracts import (
    RECORD_SCHEMA_VERSION,
    STRUCTURAL_REASONS,
    TIMEZONE_INTERPRETATION,
    Adapter,
    BatchStatus,
    IngestionReport,
    MappingStatus,
    ParsedRow,
    QuarantineReason,
    RawRecord,
)
from floodguard.ingestion.hashing import jsonl_bytes, sha256_hex
from floodguard.ingestion.station_mapping import SensorMapper, StationMappingError
from floodguard.station_master import FG_NAMESPACE

MAPPING_REASONS = frozenset({QuarantineReason.UNMAPPED_SENSOR, QuarantineReason.INVALID_SOURCE_ID})


def batch_id(adapter: Adapter, payload_sha256: str, retrieved_at_utc: str) -> str:
    """Deterministic: re-running identical inputs yields byte-identical records artifacts."""
    name = (
        f"raw_batch/v1|{adapter.source}|{adapter.dataset}|{adapter.partition or ''}"
        f"|{payload_sha256}|{retrieved_at_utc}"
        f"|{adapter.parser_name}|{adapter.parser_version}"
    )
    return str(uuid.uuid5(FG_NAMESPACE, name))


def _record(
    row: ParsedRow,
    adapter: Adapter,
    mapper: SensorMapper | None,
    common: dict[str, Any],
) -> RawRecord:
    fg: str | None = None
    reason: QuarantineReason | None = row.structural_error
    detail = row.structural_detail
    status = (
        MappingStatus.UNMAPPED if adapter.requires_station_mapping else MappingStatus.NOT_APPLICABLE
    )
    if reason is None and adapter.requires_station_mapping:
        if mapper is None or row.sensor_type is None:
            raise StationMappingError("station mapping required but no mapper/sensor type")
        res = mapper.resolve(adapter.source, row.source_station_id, row.sensor_type)
        fg, reason, detail = res.fg_sensor_id, res.reason, res.detail
        if fg is not None:
            status = MappingStatus.MAPPED
    return RawRecord(
        **common,
        fg_sensor_id=fg,
        mapping_status=status,
        quarantine_reason=reason,
        quarantine_detail=detail,
        row=row,
    )


def _source_duplicates(rows: tuple[ParsedRow, ...], source: str) -> int:
    """Rows sharing source + station + measurement + observation time (counted, never dropped)."""
    keys = [
        (
            source,
            r.source_station_id.strip(),
            r.measurement_type,
            r.observation_time_naive or r.source_time_raw,
        )
        for r in rows
        if r.source_station_id and (r.observation_time_naive or r.source_time_raw)
    ]
    return len(keys) - len(set(keys))


def ingest_batch(
    payload: bytes,
    adapter: Adapter,
    *,
    source_reference: str,
    retrieved_at: datetime,
    raw_root: Path,
    mapper: SensorMapper | None = None,
    now: datetime | None = None,
) -> IngestionReport:
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")
    retrieved_utc = retrieved_at.astimezone(UTC)
    retrieved_iso = retrieved_utc.isoformat()
    sha = sha256_hex(payload)
    report = IngestionReport(
        run_id=str(uuid.uuid4()),
        status=BatchStatus.FAILED,
        source=adapter.source,
        dataset=adapter.dataset,
        source_reference=source_reference,
        retrieved_at=retrieved_iso,
        payload_sha256=sha,
        payload_bytes=len(payload),
        parser_name=adapter.parser_name,
        parser_version=adapter.parser_version,
        partition=adapter.partition,
    )
    entry: dict[str, Any] = {
        "run_id": report.run_id,
        "source": adapter.source,
        "dataset": adapter.dataset,
        "partition": adapter.partition,
        "source_reference": source_reference,
        "retrieved_at": retrieved_iso,
        "ingested_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
        "payload_sha256": sha,
        "payload_bytes": len(payload),
        "parser_name": adapter.parser_name,
        "parser_version": adapter.parser_version,
        "record_schema_version": RECORD_SCHEMA_VERSION,
    }

    def fail(reason: str) -> IngestionReport:
        report.status = BatchStatus.FAILED
        report.error_reason = reason
        report.artifacts_written = 0
        report.artifact_paths = []
        try:
            manifest.append_entry(
                raw_root, {**entry, "status": BatchStatus.FAILED, "error_reason": reason}
            )
        except Exception as e:  # report both; the caller exits non-zero
            report.error_reason = f"{reason}; FAILED entry not recorded: {type(e).__name__}: {e}"
        return report

    try:
        prior = manifest.find_succeeded(
            raw_root, adapter.source, adapter.dataset, adapter.partition, sha
        )
    except Exception as e:
        return fail(f"manifest unreadable: {type(e).__name__}: {e}")
    if prior is not None:
        report.status = BatchStatus.DUPLICATE
        report.batch_id = prior.get("batch_id")
        report.duplicate_of_run_id = prior.get("run_id")
        try:
            manifest.append_entry(
                raw_root,
                {
                    **entry,
                    "batch_id": report.batch_id,
                    "status": BatchStatus.DUPLICATE,
                    "duplicate_of_run_id": report.duplicate_of_run_id,
                    "payload_path": prior.get("payload_path"),
                    "records_path": prior.get("records_path"),
                    "quarantine_path": prior.get("quarantine_path"),
                },
            )
        except Exception as e:
            return fail(f"DUPLICATE entry not recorded: {type(e).__name__}: {e}")
        return report

    try:
        result = adapter.parse(payload)
        report.batch_id = batch_id(adapter, sha, retrieved_iso)
        common: dict[str, Any] = {
            "record_schema_version": RECORD_SCHEMA_VERSION,
            "source": adapter.source,
            "dataset": adapter.dataset,
            "source_reference": source_reference,
            "source_licence": adapter.licence,
            "source_attribution": adapter.attribution,
            "retrieved_at": retrieved_iso,
            "payload_sha256": sha,
            "ingestion_batch_id": report.batch_id,
            "parser_name": adapter.parser_name,
            "parser_version": adapter.parser_version,
            "timezone_interpretation": TIMEZONE_INTERPRETATION,
        }
        records = [_record(r, adapter, mapper, common) for r in result.rows]
        accepted = [r.to_json_dict() for r in records if r.quarantine_reason is None]
        quarantined = [r.to_json_dict() for r in records if r.quarantine_reason is not None]
        reasons = Counter(r.quarantine_reason for r in records if r.quarantine_reason)
        report.input_rows = len(records)
        report.accepted_rows = len(accepted)
        report.quarantined_rows = len(quarantined)
        report.unmapped_rows = sum(n for k, n in reasons.items() if k in MAPPING_REASONS)
        report.invalid_structural_rows = sum(
            n for k, n in reasons.items() if k in STRUCTURAL_REASONS
        )
        report.source_duplicates_observed = _source_duplicates(result.rows, adapter.source)
        report.source_no_result = result.source_no_result

        d = storage.batch_dir(adapter.source, adapter.dataset, adapter.partition, retrieved_utc)
        records_bytes, quarantine_bytes = jsonl_bytes(accepted), jsonl_bytes(quarantined)
        paths = {
            "payload_path": d / f"{sha}.{adapter.payload_extension}",
            "records_path": d / f"{sha}.records.jsonl",
            "quarantine_path": d / f"{sha}.quarantine.jsonl",
        }
        written = storage.write_artifacts(
            raw_root,
            [
                storage.Artifact(paths["payload_path"], payload),
                storage.Artifact(paths["records_path"], records_bytes),
                storage.Artifact(paths["quarantine_path"], quarantine_bytes),
            ],
        )
    except Exception as e:
        return fail(f"{type(e).__name__}: {e}")

    try:
        manifest.append_entry(
            raw_root,
            {
                **entry,
                **{k: str(v) for k, v in paths.items()},
                "batch_id": report.batch_id,
                "status": BatchStatus.SUCCEEDED,
                "records_sha256": sha256_hex(records_bytes),
                "quarantine_sha256": sha256_hex(quarantine_bytes),
                "input_rows": report.input_rows,
                "accepted_rows": report.accepted_rows,
                "quarantined_rows": report.quarantined_rows,
                "source_duplicates_observed": report.source_duplicates_observed,
            },
        )
    except Exception as e:
        _remove(raw_root, written)
        return fail(f"manifest append failed, artifacts removed: {type(e).__name__}: {e}")
    report.status = BatchStatus.SUCCEEDED
    report.artifacts_written = len(written)
    report.artifact_paths = [str(p) for p in paths.values()]
    return report


def _remove(raw_root: Path, relpaths: list[PurePosixPath]) -> None:
    for rel in relpaths:
        with contextlib.suppress(OSError):
            storage.fs_path(raw_root.joinpath(*rel.parts)).unlink()
