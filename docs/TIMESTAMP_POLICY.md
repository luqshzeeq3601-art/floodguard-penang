# Timestamp Policy

Status: implemented 2026-09-24 (Phase 2 "Normalize timestamps"). Code:
`src/floodguard/preprocessing/timestamps.py`, batch script `scripts/normalize_timestamps.py`,
tests `tests/test_timestamp_normalization.py`. Schema version `timestamp_normalization/v1`.

Timestamp normalisation is a **derived layer**. It reads raw records and writes a separate file;
the raw payload, records, quarantine files and manifest are never modified. It does not
deduplicate, drop, reorder, impute, or touch units, values or station IDs.

## 1. Terms

| Term | Meaning |
|---|---|
| `observation_time_raw` | The source's time text, copied exactly from the raw record's `source_time_raw` (surrounding whitespace included). The source of truth. |
| source timezone | A zone or offset written in the time text itself (`Z`, `+05:30`). Neither current source publishes one. |
| assumed timezone | The zone that `SOURCE_TIMEZONE_POLICY` assigns to a source whose text carries no zone. An assumption, not a fact; it is recorded on every row. |
| `observation_time_local` | The parsed time with its offset attached (ISO 8601). |
| `observation_time_utc` | The same instant in UTC (ISO 8601, `+00:00`). Only produced when a zone is known (explicit or assumed). |
| `retrieved_at` | FloodGuard's capture time (from the raw record). Used only as the reference for the FUTURE check. **Never** used as, or in place of, an observation time. |

The raw layer's `observation_time_naive` is not used: normalisation re-parses the raw text.

## 2. Source timezone policy (single registry)

`SOURCE_TIMEZONE_POLICY` is the only place a zone is defined for normalisation (a test checks
that `src/floodguard` constructs exactly one `ZoneInfo` and contains no hard-coded `+08:00`).

| Source | Zone in text | Documented zone | Policy | Evidence (2026-09-24) |
|---|---|---|---|---|
| `JPS_PUBLIC_INFOBANJIR` | none | none | assume `Asia/Kuala_Lumpur` | `data/metadata/jps/HISTORICAL_AVAILABILITY.md` (Timezone), `LIVE_ACCESS.md`, `README.md`: latest reading never after the local retrieval clock; history matches listing. JPS does **not** state that it publishes Malaysia time. |
| `DATA_GOV_MY_WEATHER_API` | none | none | assume `Asia/Kuala_Lumpur` | `data/metadata/metmalaysia/ACCESS.md`: forecast `date` is a naive calendar date; first date equals the Malaysian date at retrieval [inferred]. |

`timezone_status`:

- `EXPLICIT_IN_SOURCE`: the text carries `Z` or an offset; that offset is used, the policy is not.
- `UNSPECIFIED_ASSUMED`: no zone in the text; the policy zone was applied. All current JPS and
  data.gov.my rows are in this state.
- `UNSPECIFIED_NO_POLICY`: no zone in the text and no policy for the source. No local/UTC
  instant is produced.

`Asia/Kuala_Lumpur` has had a fixed `+08:00` offset since 1982-01-01 (tested daily 1982-2100
against the installed IANA data). Earlier transitions (1945 repeated hour, 1981-12-31 skipped
23:30-23:59) are detected and flagged `AMBIGUOUS`.

## 3. Observed formats

Derived from the test fixtures and the local-only captures in `data/metadata/jps/raw/` (read-only).

| Source / dataset | Field | Example | Format | Precision | Zone |
|---|---|---|---|---|---|
| JPS `rainfall_listing` | `Kemaskini Terakhir` | `24/09/2026 01:15:00` | `%d/%m/%Y %H:%M:%S` | SECOND | unspecified, assumed |
| JPS `water_level_listing` | `Kemaskini Terakhir` | `24/09/2026 01:45` | `%d/%m/%Y %H:%M` | MINUTE | unspecified, assumed |
| JPS `rainfall_history` | `dt` | `18/09/2026 00:00` | `%d/%m/%Y %H:%M` | MINUTE | unspecified, assumed |
| JPS `water_level_history` | `dt` | `24/09/2024 13:45` | `%d/%m/%Y %H:%M` | MINUTE | unspecified, assumed |
| data.gov.my `weather_forecast` | `date` | `2026-09-24` | `%Y-%m-%d` | DATE | unspecified, assumed |
| data.gov.my warning (not ingested) | `issued`, `valid_from`, `valid_to` | `2026-09-24T09:00:00` | ISO 8601, naive | SECOND | unspecified |

The rainfall listing's six daily-column headers (`18/09/2026` ...) are column labels, not
observation times. The JPS patterns are taken from the adapters (`RAINFALL_LISTING.time_format`,
`WATER_LEVEL_LISTING.time_format`, `HISTORY_TIME_FORMAT`), so the formats are defined once.
Parsing is strict: the text (outer whitespace stripped) must round-trip through the format, so
unpadded or otherwise changed forms are `INVALID_FORMAT` (format drift is surfaced, not guessed).
An `ISO_8601` format (`YYYY-MM-DDTHH:MM[:SS][Z|±HH:MM]`, no fractions) is supported for sources
that publish offsets; no ingested dataset uses it yet.

## 4. Quality flag

One `timestamp_quality_flag` per row. Timezone provenance is a separate field
(`timezone_status`), so a JPS row can be `VALID` and still be marked as an assumption.

| Flag | When | Values produced |
|---|---|---|
| `VALID` | parsed, zone known, not in the future | local, UTC (or date label) |
| `MISSING` | `None`, empty or whitespace-only | none; `retrieved_at` is not substituted |
| `INVALID_FORMAT` | no permitted format matches, or an impossible date/time (31/02, 29/02 in a non-leap year, 24:00) | none |
| `AMBIGUOUS` | the wall time is repeated or skipped in the assumed zone (zoneinfo `fold` check) | none (cannot choose an instant) |
| `FUTURE` | UTC instant later than `retrieved_at + 10 min` | local and UTC kept; row not dropped |
| `UNSPECIFIED_TIMEZONE` | parsed, but no zone in text and no source policy | none (UTC not derivable) |

**Future skew.** `FUTURE_SKEW = 10 min`. A time exactly at `retrieved_at + 10 min` is `VALID`; one
second later is `FUTURE`. Why `retrieved_at` and not the wall clock: an observation cannot be
later than its capture, and using the record's own capture time keeps the output reproducible
(the same records always give the same flags). Known real case: JPS history responses are padded
with `-9999` slots up to the requested end time, which can lie after retrieval.

**Date-only values.** `DATE` precision (forecast `date`) is kept as a calendar label in
`observation_date_local`; `observation_time_local` and `observation_time_utc` stay null. No
midnight instant is invented, because the period semantics of a forecast date are not documented.
Forecast dates lie ahead of retrieval by design, so date labels are never flagged `FUTURE`.

## 5. Sequence checks

`check_monotonic` takes `(source_row_index, observation_time_utc)` in source order and reports,
without reordering or dropping anything:

- `non_monotonic_positions`: rows whose instant is earlier than the preceding placed row;
- `duplicate_groups`: UTC instants shared by several rows (compared as instants, not text);
- `unplaced_positions`: rows with no UTC instant (not compared).

The batch script runs it for history datasets (one station per batch). Listings are multi-station
snapshots and are not checked.

## 6. Derived output

`scripts/normalize_timestamps.py --records <raw_root>/.../<sha256>.records.jsonl` checks the file
against its `SUCCEEDED` manifest entry (`records_sha256`), then writes
`data/interim/timestamps/v1/<same relative path>/<sha256>.timestamps.jsonl` (git-ignored). One line
per accepted raw record, joined back by `ingestion_batch_id` + `source_row_index`. Written
write-once, temp-then-rename (`floodguard.ingestion.storage`): a rerun is a no-op, and different
content at an existing path is refused. The output root must lie outside the raw root.
Quarantined raw rows are not normalised (they have no mapped station or no usable structure).

Fields: `docs/04_DATA_DICTIONARY.md` section 1c.

## 7. Limitations

- The JPS and data.gov.my zones are assumptions supported by consistency evidence only; neither
  publisher documents a timezone. Revisit if either source publishes one.
- Forecast date period semantics (Malaysian calendar day?) are not verified, so no UTC interval
  is produced for them.
- data.gov.my warnings are not ingested; their ISO format is supported but not yet used.
