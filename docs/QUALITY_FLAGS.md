# Data-Quality Flags

Status: implemented 2026-09-24 (Phase 2 "Add quality flags"). Code:
`src/floodguard/validation/quality_flags.py`. Written by `scripts/build_historical_dataset.py`
(see `docs/HISTORICAL_PIPELINE.md`) into `data/interim/quality/v1/` (git-ignored).

## 1. What the layer does

It joins, per raw record, the rows the three component layers already produced and turns their
statuses into machine-readable flags. It does not re-parse times, re-resolve station IDs or
re-validate units:

| Component | Status reused | Produced by |
|---|---|---|
| raw record | `quarantine_reason`, raw file (records / quarantine) | `floodguard.ingestion` |
| timestamps | `timestamp_quality_flag`, `timezone_status`, `precision` | `preprocessing.timestamps` |
| station IDs | `station_id_mapping_status`, raw vs derived `fg_sensor_id` | `preprocessing.station_ids` |
| units | `unit_validation_status`, `value_parse_status`, `measurement_type` | `preprocessing.units` |

One quality row per raw record for the primary value, plus one per other field the unit layer
promoted to a measurement type (only the data.gov.my forecast `min_temp`/`max_temp`). Thresholds
are source metadata (`CURRENT_NOT_HISTORICAL` in history) and stay in the unit layer. Join key:
`ingestion_batch_id` + `source_row_index` + `source_field`.

`quality_flags` is a sorted list, so several flags can apply to one row. The component statuses
are copied next to it unchanged. `usable` is true only when every flag is informational and a
number was parsed (`parsed_value` not null).

These flags describe **data quality only**. The JPS flood severity categories (Normal, Waspada,
Amaran, Bahaya) are never used as quality levels; a test enforces it.

## 2. Flags

Blocking flags make a row unusable as a canonical station observation. Informational flags do not.

| Flag | Kind | Source of the condition |
|---|---|---|
| `RAW_QUARANTINED` | blocking | row is in the raw quarantine file |
| `ROW_STRUCTURE_INVALID` | blocking | raw `quarantine_reason = INVALID_ROW_STRUCTURE` |
| `TIMESTAMP_MISSING` | blocking | timestamp `MISSING`, or raw `MISSING_TIMESTAMP` (quarantine) |
| `TIMESTAMP_INVALID_FORMAT` | blocking | timestamp `INVALID_FORMAT`, or raw `UNPARSEABLE_TIMESTAMP` |
| `TIMESTAMP_AMBIGUOUS` | blocking | timestamp `AMBIGUOUS` |
| `TIMESTAMP_FUTURE` | blocking | timestamp `FUTURE` (> `retrieved_at` + 10 min) |
| `TIMESTAMP_UNSPECIFIED_TIMEZONE` | blocking | timestamp `UNSPECIFIED_TIMEZONE` |
| `TIMESTAMP_DATE_ONLY` | blocking | `DATE` precision (forecast dates; no instant) |
| `TIMEZONE_ASSUMED` | informational | `timezone_status = UNSPECIFIED_ASSUMED` (every JPS and data.gov.my row today) |
| `NO_STATION_SENSOR` | blocking | source has no station master (data.gov.my forecasts) |
| `SENSOR_UNMAPPED` | blocking | station `UNMAPPED` |
| `SOURCE_ID_INVALID` | blocking | station `INVALID_SOURCE_ID` |
| `SENSOR_TYPE_MISMATCH` | blocking | station `SENSOR_TYPE_MISMATCH` |
| `SENSOR_TYPE_INVALID` | blocking | station `INVALID_SENSOR_TYPE` |
| `STATION_MASTER_CHANGED_SINCE_INGEST` | informational | ingest-time `fg_sensor_id` null on one side only |
| `UNIT_MISSING` / `UNIT_UNKNOWN` / `UNIT_MISMATCH` | blocking | unit `MISSING_UNIT` / `UNKNOWN_UNIT` / `UNIT_MISMATCH` |
| `UNIT_SENSOR_TYPE_MISMATCH` | blocking | unit `SENSOR_TYPE_MISMATCH` |
| `MEASUREMENT_SEMANTICS_UNKNOWN` | blocking | unit `UNKNOWN_MEASUREMENT_SEMANTICS` |
| `VALUE_MISSING_SENTINEL` | blocking | value `SOURCE_MARKER` `-9999` (also `-9999.0`) |
| `VALUE_SOURCE_ERROR` | blocking | value `SOURCE_MARKER` `ERROR` |
| `VALUE_NO_DATA_MARKER` | blocking | value `SOURCE_MARKER` `Tiada Data` |
| `VALUE_EMPTY` | blocking | value `EMPTY` (null, blank) |
| `VALUE_NON_NUMERIC` | blocking | value `NON_NUMERIC` |
| `RAINFALL_NEGATIVE` | blocking | rainfall measurement with a parsed value < 0 (definitional, not an outlier rule) |
| `SOURCE_SEVERITY_ERROR` | informational | JPS water-level history `severity = ERROR` (a source QC marker; the value itself is `-9999` in every captured case and is flagged separately) |
| `DUPLICATE_IDENTICAL` | informational | added in the canonical table (`docs/HISTORICAL_PIPELINE.md`) |
| `DUPLICATE_CONFLICT` | blocking | added in the canonical table |

Value flags are set only for fields with a known measurement type: the forecast's categorical
`summary_forecast` text gets `MEASUREMENT_SEMANTICS_UNKNOWN`, not `VALUE_NON_NUMERIC`.

Zero is a valid number. A `0` rainfall reading gets no value flag and stays usable. The four
missing representations (`-9999`, `ERROR`, blank, `Tiada Data`) keep separate flags. Absent rows
(no row at all for a 5-min slot) are not records, so they are measured in the quality summary, not
flagged here.

## 3. Deliberately not flagged

- **Physical ranges / outliers.** No evidence-backed bounds exist yet. Negative water levels occur
  in real data (`-0.31` m) and stay valid.
- **Freshness / staleness.** The JPS live freshness classes in `data/metadata/jps/LIVE_ACCESS.md`
  are provisional and apply to live polling, not history. No permanent rule is set here.
- **Thresholds.** Unit-validated in the unit layer. History thresholds are present-day values
  (`CURRENT_NOT_HISTORICAL`), so they are not historical truth.

## 4. Pipeline defects fail loudly

`flag_batch` raises `PipelineJoinError` (nothing written) when components do not join one-to-one:
a missing, duplicated or orphan component row, a record without exactly one `PRIMARY_VALUE` unit
row, timestamp rows for a quarantine file, missing station rows for JPS records, a component row
whose `payload_sha256`/`source`/`dataset` differs from its record, or conflicting non-null
`fg_sensor_id`s, a timestamp or primary-unit row whose time or value text differs from its record
(off-by-one pairing), or a record whose `quarantine_reason` does not match the file it came from.
These are code or storage defects, never ordinary data-quality warnings.

## 5. Output fields

`docs/04_DATA_DICTIONARY.md` section 1f.
