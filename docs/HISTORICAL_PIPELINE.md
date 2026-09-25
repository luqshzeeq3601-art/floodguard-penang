# Historical Pipeline: raw → validated → processed

Status: implemented 2026-09-24 (Phase 2 "Build raw -> validated -> processed pipeline" and "Add
data-quality tests"). Code: `src/floodguard/validation/` (`build.py`, `quality_flags.py`,
`observations.py`, `checks.py`, `summary.py`); CLI `scripts/build_historical_dataset.py`.

## 1. Flow

```text
data/raw/ (immutable; payload, records, quarantine, manifest)
   │  every SUCCEEDED batch; payload/records/quarantine SHA-256 checked against the manifest
   ├─> interim/timestamps/v1    preprocessing.timestamps   (accepted records)
   ├─> interim/station_ids/v1   preprocessing.station_ids  (JPS records + quarantine)
   ├─> interim/units/v1         preprocessing.units        (records + quarantine)
   └─> interim/quality/v1       validation.quality_flags   = the VALIDATED layer
          │  one row per raw record and measurement field; nothing dropped
          ▼
processed/observations/v1/<dataset_version>/
   observations.jsonl       canonical long-form observations (validation.observations)
   quality_summary.json     factual diagnostics (validation.summary)
   dataset_manifest.json    inputs, versions, checks, licence, timezone assumption
```

One command, one run, then exit (no loop, scheduler or network):

```text
.venv\Scripts\python.exe scripts\build_historical_dataset.py
```

Options: `--raw-root`, `--interim-root`, `--processed-root`, `--station-master`. Exit codes: 0 built
or already present; 1 a data-quality check failed (no processed output); 2 rejected (raw file
does not match the manifest, component join defect, unusable station master, output root inside
the raw root, or an existing output with different content).

The component files are produced with the layers' own functions and have the same paths and
bytes their per-layer scripts write; a test re-runs those scripts over the pipeline's output and
gets write-once no-ops. All outputs are write-once, so a rerun is a no-op.

## 2. Dataset version

`dataset_version` = first 16 hex of SHA-256 over the pipeline version, every component schema and
policy version, the station-master origin (file name + hash prefix) and the sorted list of input
batches (`batch_id`, dataset, partition, `retrieved_at`, payload/records/quarantine hashes).
Batches are sorted by source, dataset, partition and payload hash, so the version does not depend
on ingestion order. Any new batch, rebuilt station master or schema change gives a new processed
directory; older versions are never overwritten. The interim component files are keyed by raw batch
only and are write-once, so a rebuilt station master (or a code change that alters a component's
output without a schema bump) is refused on an existing interim root (exit 2,
`ImmutableArtifactError`), exactly as the per-layer scripts refuse it. Build such a version into a
new `--interim-root`.

## 3. Canonical observations (`observations/v1`)

Identity is `(source, fg_sensor_id, observation_time)` with `observation_time` =
`observation_time_utc` (`docs/STATION_MASTER_DESIGN.md` section 12). A rain gauge publishes two
verified measurements for one instant (5-min interval from history, 1-hour total from the
listing), so each `measurement_type` is a separate value of the same observation and the table is
keyed by identity + `measurement_type`. No second identity scheme exists.

A quality row enters only when all hold; otherwise it is counted under
`excluded_quality_rows` by reason and dataset:

| Requirement | Exclusion reason |
|---|---|
| measurement type is `RAINFALL_INTERVAL`, `RAINFALL_1H_TOTAL` or `WATER_LEVEL` | `NOT_A_STATION_OBSERVATION` (forecasts, unpromoted fields) |
| unit `VALID` | `UNIT_NOT_VALID` |
| mapped `fg_sensor_id`, row not quarantined | `NO_CANONICAL_SENSOR` |
| timestamp `VALID` with a UTC instant | `NO_VALID_OBSERVATION_TIME` (includes `FUTURE`, e.g. JPS history padding after retrieval) |

Rows whose value is `-9999`, `ERROR`, `Tiada Data`, blank or non-numeric **do** enter, with
`value` null, `value_raw` kept and the matching flag, so missingness stays visible. Zero stays
`0.0` and usable.

### Duplicates

Detected on the canonical key across all batches (overlapping history windows, repeated listing
snapshots of a stale station, listing vs history for the same reading). The raw layer is never
changed.

| `duplicate_status` | Rule | Output |
|---|---|---|
| `UNIQUE` | one source row | its value |
| `IDENTICAL` | several rows, same value representation (numeric value compared as a float; markers by text) | one row, `DUPLICATE_IDENTICAL` (informational), every source row in `provenance`, `duplicate_count` |
| `CONFLICT` | several rows, different representations | `value`, `value_raw`, `value_parse_status` null; `DUPLICATE_CONFLICT` (blocking); `conflict_reason` `NUMERIC_VALUES_DIFFER` / `MARKER_VS_NUMERIC` / `MARKERS_DIFFER`; all candidates in `conflicting_values` |

A conflict is never resolved by picking a value. Metadata of an identical group (local time, raw
text) comes from the earliest capture (`retrieved_at`, then batch ID, row index), which is also
`first_retrieved_at`: the first time FloodGuard held the observation. Flags are the union of all
members' flags. Each `provenance` entry keeps its own `value_signature` (`STATUS:value`), so what
every capture said, and when, stays recoverable for a later as-of join. Numeric values are
compared as floats with `-0.0` folded into `0.0`.

### Ordering and time

Rows are sorted by source, `fg_sensor_id`, `measurement_type`, UTC instant, and a check requires
strictly increasing keys. No slot is created for an absent row, nothing is interpolated or
filled, and no window or aggregate is computed in Phase 2. All JPS times carry the assumed
`Asia/Kuala_Lumpur` zone (`TIMEZONE_ASSUMED` flag, `timezone_status = UNSPECIFIED_ASSUMED`).

Thresholds are not part of the table: history thresholds are present-day values
(`CURRENT_NOT_HISTORICAL`) and stay in the unit layer with their capture time.

## 4. Quality summary (`quality_summary/v1`)

Measured before anything is excluded:

- `validated`: rows and usable rows by dataset; raw file (records/quarantine); every flag, overall
  and by dataset; each component status by dataset.
- `canonical`: rows and usable rows by measurement type; distinct sensors per type and sites;
  duplicate status, collapsed source rows, conflict reasons; missing-value flags; exclusions; UTC
  range.
- `series` (per `fg_sensor_id/measurement_type`): first/last time, rows, usable rows, missing-value
  flags, duplicates, datasets, per local date (rows, usable, marker rows) and, for series with
  history rows, a 5-min cadence report over the validated history rows (canonical or excluded)
  that have a UTC instant: expected slots between the first and last on-grid row, present slots,
  **absent slots** (no row at all; an excluded row is present, counted in
  `history_rows_not_in_canonical`), off-grid rows, largest gap.
  Listing snapshots are irregular and are not gap-checked.

## 5. Data-quality checks

`validation.checks.run_checks` runs before anything processed is written; any failure stops the
build (exit 1). The results are stored in `dataset_manifest.json`.

| Check | Invariant |
|---|---|
| `canonical_key_unique` | one row per source + sensor + measurement type + instant |
| `chronological_order` | strictly increasing within each series |
| `no_row_lost` | the eligible quality rows and the table's provenance entries are the same multiset of (batch, row, field) (no drop, no double use) |
| `verified_measurement_types_only` | only the three observation types |
| `unit_matches_measurement_type` | rainfall `mm`, water level `m` |
| `identity_complete` | `fg_sensor_id`, `fg_site_id`, UTC instant present |
| `value_matches_status_and_flags` | value set ⇔ `NUMERIC`; a null value always has a missing-value or conflict flag |
| `zero_is_not_missing` | a zero never carries a missing-value flag (validated and canonical rows) |
| `usable_matches_flags` | usable ⇔ value and only informational flags |
| `no_future_observation` | instant ≤ `first_retrieved_at` + 10 min |
| `timezone_assumption_marked` | timezone status set; an assumed zone is flagged |
| `provenance_complete` | `duplicate_count` = provenance entries, each with batch ID and row index |
| `conflicts_unresolved` | a conflict has a null value and ≥ 2 candidates |
| `usable_rainfall_non_negative` | no usable negative rainfall |
| `quality_flags_known` | flags are known, sorted and unique |

These are invariants of the pipeline, not judgements of data health. Data health is reported in
the summary. No physical range, jump or freshness rule is applied (no evidence yet).

## 6. Leakage controls

- Every derived value comes from its own raw row; nothing is filled, interpolated or carried
  forward or backward. No rolling or centred window exists in Phase 2.
- Rows later than their capture (+10 min) are excluded, and a check enforces it.
- `first_retrieved_at` records when FloodGuard first held each observation. Because of the 10-min
  FUTURE tolerance it can precede the observation time, so an as-of join must use
  `max(first_retrieved_at, observation_time_utc)` as the availability time.
- History thresholds are never attached as historical truth.
- No split, label, target or feature is produced in Phase 2.

## 7. Licensing

Outputs derived from JPS data are PERMISSION REQUIRED (`docs/DATA_LICENSING_AND_ACCESS.md`): they
stay under the git-ignored `data/interim/` and `data/processed/`. Tests use trimmed fixtures and
synthetic edits only. The builder never fetches data; JPS bulk history retrieval remains disabled
pending permission.

## 8. Limitations

- Memory: the build holds all quality rows of a run in memory; fine for local captures, to be
  revisited for multi-year bulk history.
- The timezone is an assumption for both sources; UTC instants inherit it.
- Local evidence covers only the captures in `data/metadata/jps/raw/` (four history windows, two
  snapshots per listing); coverage metrics are not representative of the network.
