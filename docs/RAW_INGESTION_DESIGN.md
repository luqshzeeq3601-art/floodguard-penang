# Raw Ingestion Design

Phase 2, "Implement raw ingestion". Code: `src/floodguard/ingestion/`, CLI `scripts/ingest_raw.py`,
tests `tests/test_ingestion_adapters.py`, `tests/test_ingestion_pipeline.py`.

The raw layer **preserves** payloads and emits **source-faithful** records with full provenance. It
does not clean, impute, convert units or timezones, normalise missing-value markers, deduplicate
observations, validate ranges, build features or labels, or write to PostgreSQL. Those belong to
the validation/normalisation tasks that follow in `TASKS.md`.

## 1. Layer responsibilities

| Module | Responsibility | Must not |
|---|---|---|
| `contracts.py` | `ParsedRow`, `RawRecord`, `ParseResult`, `IngestionReport`, `Adapter` protocol, status/reason enums, schema versions | contain logic |
| `hashing.py` | SHA-256 of payload bytes; canonical JSON Lines encoding | — |
| `adapters/jps_common.py` | Pure JPS parsing primitives (`ResultTableParser`, markers, history keys), shared with the discovery scripts | do I/O |
| `adapters/jps.py` | Rainfall/water-level **listing** (HTML) and **history** (JSON) parsers: bytes → `ParsedRow`s | resolve identity, fetch, judge values |
| `adapters/data_gov_my.py` | data.gov.my Weather API forecast parser, CC BY 4.0 licence and attribution fields | filter to Penang (validation layer does that) |
| `station_mapping.py` | Load a station-master `sensors.csv`; resolve (source, `jps_internal_id`, sensor type) → `fg_sensor_id` with `station_master` rules | invent IDs |
| `storage.py` | Immutable content-addressed store, all-or-nothing placement | overwrite |
| `manifest.py` | Append-only JSONL manifest, idempotency lookup | rewrite earlier lines |
| `fetch.py` | Permission-gated network boundary | fetch JPS without a permission record |
| `pipeline.py` | One batch: hash → idempotency → parse → map → write → manifest | loop or schedule |

Identity logic lives only in `floodguard.station_master`; adapters never map IDs.

## 2. Storage layout (immutability)

```text
<raw_root>/                                   default data/raw/ (git-ignored: data/raw/**)
  _manifest/raw_batches.jsonl                 one line per batch attempt
  <source_dir>/<dataset>[/<partition>]/<YYYY>/<MM>/<DD>/
      <payload_sha256>.<ext>                  payload, byte-for-byte as received
      <payload_sha256>.records.jsonl          accepted raw records
      <payload_sha256>.quarantine.jsonl       quarantined rows, same fields + reason
```

- `source_dir`: `jps` (JPS_PUBLIC_INFOBANJIR) or `data_gov_my` (DATA_GOV_MY_WEATHER_API); full
  source names are in every record and manifest line. On Windows all file operations use the
  extended-length path form (`storage.fs_path`), because artifact paths under a deep raw root
  exceed 260 characters (observed in the E2E run; regression test
  `test_deep_raw_root_beyond_windows_max_path`).
- `dataset`: `rainfall_listing`, `water_level_listing`, `rainfall_history`, `water_level_history`,
  `weather_forecast`.
- `partition`: only where the payload does not identify its own scope. JPS history bodies contain
  no station ID and "No result" is byte-identical for every station, so history batches are
  partitioned by the whitespace-stripped station key (validated `^[A-Za-z0-9_]{1,32}$`).
- Date: UTC date of `retrieved_at` (a capture at 01:39 +08:00 lands under the previous UTC day).
- Why content-addressed: the file name is the payload hash, so a file can be verified by rehashing
  and two captures of the same bytes cannot produce two payload files. Why a date directory:
  bounded directory sizes and simple time-range listing; the manifest remains the index.
- Writes: temp file in the same directory, `fsync`, then `os.replace`. An existing target with
  identical bytes is a no-op; with different bytes `ImmutableArtifactError` is raised and nothing is
  replaced. Files placed by a failing batch are removed again; temp files are always deleted.
- `<ext>` is the adapter's `payload_extension` (`html`, `json`); storage writes opaque bytes
  (binary mode, no decoding or newline translation), so a future CSV source only sets `csv`.
  Evidence: `tests/test_raw_payload_preservation.py` (exact bytes and SHA-256 for all five
  adapters, including CRLF/trailing-whitespace variants and a BOM on the HTML listings, and a
  synthetic CSV via storage).
- Only artifacts named by a `SUCCEEDED` manifest entry form a valid batch; a file without one
  (orphan of a hard crash, see §10) must not be consumed.
- Single-writer assumption: one ingestion process per raw root at a time (no cross-process lock).
- JSON Lines are canonical (sorted keys, compact separators, UTF-8), so identical inputs give
  identical bytes: `ingestion_batch_id` is a UUIDv5 of source, dataset, partition, payload hash,
  `retrieved_at`, parser name and version (namespace `station_master.FG_NAMESPACE`).

## 3. Manifest (`raw_manifest/v1`)

`<raw_root>/_manifest/raw_batches.jsonl`, one canonical JSON object per attempt. Append = read
existing bytes, write existing + new line to a temp file, check the file did not change, then
`os.replace`. Earlier lines are never rewritten; an unterminated last line stops ingestion.

| Field | Meaning |
|---|---|
| `manifest_schema_version` | `raw_manifest/v1` |
| `run_id` | UUIDv4 of this invocation |
| `batch_id` | deterministic `ingestion_batch_id` (DUPLICATE: the original batch's) |
| `status` | `SUCCEEDED`, `FAILED`, `DUPLICATE` |
| `source`, `dataset`, `partition` | batch scope (`partition` null except JPS history) |
| `source_reference` | request URL or file reference, as supplied |
| `retrieved_at` | capture time, tz-aware UTC ISO 8601 |
| `ingested_at` | wall-clock time of this run, UTC |
| `payload_sha256`, `payload_bytes` | hash and size of the payload bytes |
| `payload_path`, `records_path`, `quarantine_path` | relative to the raw root (DUPLICATE: the original's) |
| `records_sha256`, `quarantine_sha256` | hashes of the JSONL artifacts |
| `input_rows`, `accepted_rows`, `quarantined_rows`, `source_duplicates_observed` | counts |
| `parser_name`, `parser_version`, `record_schema_version` | parser and record contract |
| `duplicate_of_run_id` | DUPLICATE only: `run_id` of the SUCCEEDED batch |
| `error_reason` | FAILED only: exception type and message |

## 4. Idempotency

Key: `source + dataset + partition + payload_sha256`. If a SUCCEEDED entry with that key exists, the
run appends a `DUPLICATE` entry and writes no artifact. FAILED entries do not block a retry.
Re-parsing a stored payload with a newer parser version is not done by this CLI (future replay
task); the preserved payload makes it possible.

Observation-level duplicates are a different thing: rows sharing
`source + jps_internal_id (stripped) + measurement_type + observation time` within one batch are
**counted** (`source_duplicates_observed`) and all kept. Overlap *between* batches (successive
listing polls republish the same observation) is expected and left to the validation layer.

## 5. Raw record contract (`raw_record/v1`)

Field list: `docs/04_DATA_DICTIONARY.md`, section 1b. Principles:

- Published IDs exactly as received: `source_station_id` keeps whitespace (`" 5402002_"`),
  `source_display_station_id` keeps `No Data` and blanks.
- `source_time_raw` exactly as received; `observation_time_naive` is the same instant parsed with the
  verified format, **no offset, no UTC conversion**; `timezone_interpretation` is
  `UNVERIFIED_ASSUMED_MYT` (JPS and data.gov.my declare no timezone). `retrieved_at` is tz-aware UTC.
- `value_raw` and every cell/key in `source_fields_raw` are text as published: `-9999`, `ERROR`,
  blank, `Tiada Data`, `0`/`0.0` (zero rainfall is valid data) are preserved and never judged here.
  JSON `null` becomes `null`, distinct from `""`. JSON number tokens keep their text. HTML cells are
  taken with outer whitespace stripped; the payload file keeps the exact bytes.
- Primary value: listing rainfall `Jumlah 1 Jam`, listing water level `Aras Air (m)`, history
  rainfall `raw` (5-min increment; `clean` depends on `datafreq`), history water level `final`
  (plotted by the official page). All other fields stay in `source_fields_raw`.
- Units: `unit` + `unit_basis` (`SOURCE_HEADER` when the payload labels it, `SOURCE_DOCUMENTATION`
  when it comes from official graph-page labels, `NONE`).
- Thresholds are source metadata only (`threshold_values_raw`), with
  `threshold_temporal_scope` = `CURRENT_AT_RETRIEVAL` (listings) or `CURRENT_NOT_HISTORICAL`
  (history responses return today's thresholds for any window). Nothing is labelled from them here.
- Provenance on every record: source, dataset, `source_reference`, licence, attribution,
  `retrieved_at`, `payload_sha256`, `ingestion_batch_id`, parser name/version, schema version,
  `source_row_index` and (HTML) `source_line`.
- Identity: `fg_sensor_id` + `mapping_status` (`MAPPED`, `UNMAPPED`, `NOT_APPLICABLE` for sources
  without a station master, e.g. forecasts). Unmapped rows are quarantined, never given an ID.

## 6. Failure semantics

| Situation | Outcome |
|---|---|
| Same payload again (same key) | `DUPLICATE`, nothing written |
| Not UTF-8, not JSON (except the "No result" body) | `FAILED` (`PayloadError`) |
| Schema change: required header missing, header count changed, JSON shape changed, an expected key missing from every row | `FAILED` (`SchemaError`) with the missing names |
| Listing body `Tiada Data` (no station rows) | `FAILED` |
| History `No result` body | `SUCCEEDED`, 0 rows, `source_no_result: true`, payload kept |
| Row with wrong cell count, no graph link, missing keys | row quarantined `INVALID_ROW_STRUCTURE` |
| Row with blank/absent time / time not in the verified format | quarantined `MISSING_TIMESTAMP` / `UNPARSEABLE_TIMESTAMP` |
| ID not in the station master (e.g. non-Penang) / unusable ID | quarantined `UNMAPPED_SENSOR` / `INVALID_SOURCE_ID` |
| Non-numeric or sentinel value with intact structure | accepted as raw text |
| History `source_station_id` ≠ `station` parameter of the reference URL | `FAILED` |
| Artifact exists with different bytes (e.g. orphan of an interrupted run) | `FAILED`, existing file untouched |
| Write error (disk full, permissions) | `FAILED`, placed files removed, temps deleted |
| Manifest append fails after placement | artifacts removed, `FAILED` |
| Bad CLI arguments, naive `--retrieved-at`, unreadable input, missing/inconsistent station master | rejected before a batch starts: exit 2, nothing written, no manifest line |

`IngestionReport` (printed as JSON by the CLI): `input_rows`, `accepted_rows`, `quarantined_rows`,
`unmapped_rows`, `invalid_structural_rows`, `source_duplicates_observed`, `source_no_result`,
`artifacts_written`, `artifact_paths`, `status`, `error_reason`, plus scope and hashes. CLI exit
code: 0 SUCCEEDED/DUPLICATE, 1 FAILED, 2 rejected.

## 7. Station mapping

`SensorMapper.from_csv` reads a station-master `sensors.csv` (default
`data/local/station_master/sensors.csv`, local-only because JPS data is PERMISSION REQUIRED). Every
row's `fg_sensor_id` is re-derived with `station_master.sensor_id(source, normalise_source_id(id),
sensor_type)` and its `fg_site_id` must be that key's canonical or review site ID; a mismatch,
duplicate, unknown schema version or missing column rejects the file. `SensorMapper.lookup` is the
single resolver, shared with the derived station-ID layer (`docs/STATION_MASTER_DESIGN.md` section
12); `resolve` turns its result into the raw layer's ID-or-quarantine-reason form.
Lookups strip outer whitespace only (the documented key rule) and keep sensor type, so a shared
`jps_internal_id` resolves to different rainfall and water-level sensors. Records store
`quarantine_detail` with the file name and a hash prefix, never the local path.

## 8. Permission boundary

- JPS Public Infobanjir: **network fetching is disabled.** The CLI has no JPS fetch option; JPS
  payloads are ingested only from files the user supplies with `--input`.
  `fetch.PermissionedFetcher` raises `PermissionNotGrantedError` before any socket use unless it
  holds an `AccessPermission` for that exact source with scope `network_fetch`. For JPS such a
  record can only come from an explicit local JSON file (`load_permission`; fields `source`,
  `scope`, `granted_by`, `reference`, `granted_on`), none exists, and nothing in the CLI loads one.
  Enabling JPS fetch requires JPS's written consent (`docs/DATA_LICENSING_AND_ACCESS.md` §8) and a
  code change.
- data.gov.my Weather API: open (CC BY 4.0, 4 requests/min). `data-gov-my-weather --fetch` makes
  exactly one GET per invocation; no retry, loop or scheduler. Records carry licence and the
  attribution text from `docs/DATA_LICENSING_AND_ACCESS.md` §7.
- Tests block `socket.connect`, `create_connection` and `getaddrinfo` (`no_network` fixture) and
  assert the guard fires.

## 9. Timestamp policy

| Field | Rule |
|---|---|
| `source_time_raw` | verbatim text |
| `observation_time_naive` | parsed with the verified format (`DD/MM/YYYY HH:MM[:SS]`), ISO without offset; `null` if blank, unparseable, or a date-only value (forecast `date`) |
| `timezone_interpretation` | `UNVERIFIED_ASSUMED_MYT`; conversion to aware `Asia/Kuala_Lumpur` is done by the derived layer in `docs/TIMESTAMP_POLICY.md` (raw records unchanged) |
| `retrieved_at` | supplied capture time (must carry an offset), stored as UTC |
| `ingested_at` | manifest only, run wall clock, UTC |

## 10. Limitations

- JSON value type (string vs number token) is not kept per field; the payload file has it.
- Listing rainfall daily totals stay inside `source_fields_raw` keyed by their date headers; they
  are not separate observations yet.
- No cross-process locking; the manifest is re-read per batch (O(n) in manifest lines).
- A stored payload is not re-parsed when the parser version changes (future replay task).
- A UTF-8 BOM before a JSON payload (not observed upstream) fails the batch (`PayloadError`,
  nothing stored); HTML listings tolerate it.
- Orphan artifacts from a crash between placement and manifest append: a retry with the same
  inputs reproduces identical bytes and adopts them; different bytes are a conflict (FAILED). They
  are not cleaned automatically.
- No PostgreSQL, validated/interim/processed layers, marker normalisation or quality flags yet.
