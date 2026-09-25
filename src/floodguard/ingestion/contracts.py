"""Source-neutral raw-ingestion contracts (stdlib dataclasses, JSON-serialisable).

Field semantics: docs/RAW_INGESTION_DESIGN.md and docs/04_DATA_DICTIONARY.md (section 1b).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Protocol

RECORD_SCHEMA_VERSION = "raw_record/v1"
MANIFEST_SCHEMA_VERSION = "raw_manifest/v1"
REPORT_SCHEMA_VERSION = "ingestion_report/v1"
# Neither JPS nor data.gov.my declares a timezone; Asia/Kuala_Lumpur is assumed, never applied.
TIMEZONE_INTERPRETATION = "UNVERIFIED_ASSUMED_MYT"


class PayloadError(ValueError):
    """The captured payload cannot be ingested (malformed bytes or structure)."""


class SchemaError(PayloadError):
    """Upstream markup or content no longer matches the verified schema."""


class BatchStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"


class MappingStatus(StrEnum):
    MAPPED = "MAPPED"
    UNMAPPED = "UNMAPPED"
    NOT_APPLICABLE = "NOT_APPLICABLE"  # source has no FloodGuard station master (e.g. forecasts)


class QuarantineReason(StrEnum):
    UNMAPPED_SENSOR = "UNMAPPED_SENSOR"
    INVALID_SOURCE_ID = "INVALID_SOURCE_ID"
    MISSING_TIMESTAMP = "MISSING_TIMESTAMP"
    UNPARSEABLE_TIMESTAMP = "UNPARSEABLE_TIMESTAMP"
    INVALID_ROW_STRUCTURE = "INVALID_ROW_STRUCTURE"


# Structural reasons: the row cannot form a source identity. UNMAPPED/INVALID_SOURCE_ID are mapping.
STRUCTURAL_REASONS = frozenset(
    {
        QuarantineReason.MISSING_TIMESTAMP,
        QuarantineReason.UNPARSEABLE_TIMESTAMP,
        QuarantineReason.INVALID_ROW_STRUCTURE,
    }
)


@dataclass(frozen=True)
class ParsedRow:
    """One source row exactly as published, before identity mapping (adapter output)."""

    source_row_index: int  # 0-based position among data rows in the payload
    source_line: int | None  # 1-based payload line where the row starts (text formats)
    source_station_id: str | None  # JPS: jps_internal_id, whitespace kept
    source_display_station_id: str | None  # JPS listing "ID Stesen"; None when not in payload
    source_station_name: str | None
    sensor_type: str | None  # station_master.SensorType value, or None when not a JPS sensor
    measurement_type: str
    source_time_raw: str | None
    source_time_field: str
    observation_time_naive: str | None  # ISO, no offset; None when absent/unparseable/date-only
    value_field: str
    value_raw: str | None  # verbatim text; None only for JSON null / absent
    unit: str | None
    unit_basis: str  # SOURCE_HEADER | SOURCE_DOCUMENTATION | NONE
    source_fields_raw: dict[str, str | None]
    threshold_values_raw: dict[str, str | None] | None = None
    threshold_temporal_scope: str | None = None
    source_metadata_raw: dict[str, str | None] = field(default_factory=dict)
    structural_error: QuarantineReason | None = None
    structural_detail: str | None = None


@dataclass(frozen=True)
class RawRecord:
    """A ``ParsedRow`` plus batch provenance and identity mapping (one JSONL line)."""

    record_schema_version: str
    source: str
    dataset: str
    source_reference: str
    source_licence: str
    source_attribution: str | None
    retrieved_at: str  # tz-aware UTC ISO 8601
    payload_sha256: str
    ingestion_batch_id: str
    parser_name: str
    parser_version: str
    timezone_interpretation: str
    fg_sensor_id: str | None
    mapping_status: MappingStatus
    quarantine_reason: QuarantineReason | None
    quarantine_detail: str | None
    row: ParsedRow

    def to_json_dict(self) -> dict[str, Any]:
        d = asdict(self)
        row = d.pop("row")
        row.pop("structural_error")
        row.pop("structural_detail")
        return {**d, **row}


@dataclass(frozen=True)
class ParseResult:
    rows: tuple[ParsedRow, ...]
    source_no_result: bool = False  # JPS history "No result" body: valid, zero rows


class Adapter(Protocol):
    """Read-only adapter surface used by the pipeline (frozen dataclasses satisfy it)."""

    @property
    def source(self) -> str: ...
    @property
    def dataset(self) -> str: ...
    @property
    def parser_name(self) -> str: ...
    @property
    def parser_version(self) -> str: ...
    @property
    def payload_extension(self) -> str: ...
    @property
    def requires_station_mapping(self) -> bool: ...
    @property
    def licence(self) -> str: ...
    @property
    def attribution(self) -> str | None: ...
    @property
    def partition(self) -> str | None:
        """Payload scope not visible in the bytes (JPS history: station key), else None."""

    def parse(self, payload: bytes) -> ParseResult: ...


@dataclass
class IngestionReport:
    run_id: str
    status: BatchStatus
    source: str
    dataset: str
    source_reference: str
    retrieved_at: str
    payload_sha256: str
    payload_bytes: int
    parser_name: str
    parser_version: str
    partition: str | None = None
    batch_id: str | None = None
    input_rows: int = 0
    accepted_rows: int = 0
    quarantined_rows: int = 0
    unmapped_rows: int = 0
    invalid_structural_rows: int = 0
    source_duplicates_observed: int = 0
    source_no_result: bool = False
    artifacts_written: int = 0
    artifact_paths: list[str] = field(default_factory=list)
    duplicate_of_run_id: str | None = None
    error_reason: str | None = None
    report_schema_version: str = REPORT_SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)
