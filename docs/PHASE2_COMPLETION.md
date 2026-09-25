# Phase 2 Completion Record — Historical Data Pipeline

Date: 2026-09-24. Scope: the Phase 2 section of `TASKS.md`. This records what exists and what
was measured. It makes no production-readiness or model-performance claim.

## 1. Tasks

| Task | Status | Evidence |
|---|---|---|
| Implement raw ingestion | DONE | `src/floodguard/ingestion/`, `scripts/ingest_raw.py`, `docs/RAW_INGESTION_DESIGN.md` |
| Preserve source payload/CSV | DONE | `tests/test_raw_payload_preservation.py`, design §2 |
| Normalize timestamps | DONE | `preprocessing/timestamps.py`, `docs/TIMESTAMP_POLICY.md` |
| Normalize station IDs | DONE | `preprocessing/station_ids.py`, `docs/STATION_MASTER_DESIGN.md` §12 |
| Validate units | DONE | `preprocessing/units.py`, `docs/UNIT_POLICY.md` |
| Add quality flags | DONE | `validation/quality_flags.py`, `docs/QUALITY_FLAGS.md`, `tests/test_quality_flags.py` |
| Build raw -> validated -> processed pipeline | DONE | `validation/{build,observations,summary}.py`, `scripts/build_historical_dataset.py`, `docs/HISTORICAL_PIPELINE.md`, `tests/test_historical_pipeline.py` |
| Add data-quality tests | DONE | `validation/checks.py`, `tests/test_data_quality_checks.py` |

No Phase 2 task is BLOCKED. Bulk acquisition of JPS history is not a Phase 2 task item; it stays
disabled pending JPS permission (section 5), and the pipeline has only been run on local captures.

## 2. Final pipeline

```text
captured payload ─ scripts/ingest_raw.py ─> data/raw/ (immutable, content-addressed, manifest)
data/raw/ ─ scripts/build_historical_dataset.py (one offline run):
   ├─ interim/timestamps/v1   tz-aware local + UTC, precision, timestamp_quality_flag
   ├─ interim/station_ids/v1  fg_site_id, fg_sensor_id, mapping status
   ├─ interim/units/v1        measurement type, canonical unit, unit and value status
   ├─ interim/quality/v1      validated layer: multi-valued quality flags, component statuses kept
   └─ processed/observations/v1/<dataset_version>/
        observations.jsonl, quality_summary.json, dataset_manifest.json (checks, inputs, versions)
```

The per-layer scripts (`normalize_timestamps.py`, `normalize_station_ids.py`, `validate_units.py`)
remain usable on one batch file and produce the same bytes as the pipeline (tested).

## 3. Verification (2026-09-24)

| Check | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 56 files already formatted |
| `mypy` (strict; src, tests, scripts) | no issues in 56 source files |
| `pytest` | 400 passed (64 new in Phase 2 steps 6–8), all offline |
| `pip check` | No broken requirements |
| `scripts/verify_environment.py` | OK: Python 3.11.9 |

## 4. Local evidence metrics

Input: the 9 local Phase 1 captures (2 rainfall listings, 2 water-level listings, 4 JPS history
windows of which 1 is "No result", 1 data.gov.my forecast), ingested into a scratch raw store
outside the repository with `retrieved_at` taken from the capture file names. Dataset version
`9995ddafeb644d7d`; station master `data/local/station_master/sensors.csv`. Outputs stayed in the
scratch directory. These captures are not a representative sample of the network.

Validated layer (every row, nothing dropped): 1,611 rows, 599 usable.

| Dataset | Rows | Usable | Main non-usable cause |
|---|---:|---:|---|
| rainfall_history | 289 | 289 | — |
| rainfall_listing | 112 | 112 | — |
| water_level_history | 578 | 154 | 424 `VALUE_MISSING_SENTINEL` (`-9999`) |
| water_level_listing | 44 | 44 | — |
| weather_forecast | 588 | 0 | not station observations (`NO_STATION_SENSOR`, `TIMESTAMP_DATE_ONLY`) |

Flags: `TIMEZONE_ASSUMED` 1,611; `VALUE_MISSING_SENTINEL` 424; `SOURCE_SEVERITY_ERROR` 167;
`NO_STATION_SENSOR` 588; `TIMESTAMP_DATE_ONLY` 588; `MEASUREMENT_SEMANTICS_UNKNOWN` 196 (forecast
text). Timestamps 100% `VALID`; JPS station IDs 1,023/1,023 `MAPPED`; JPS units 100% `VALID`;
0 quarantined rows.

Canonical table: 1,017 rows (593 usable) from 1,023 eligible source rows; 5 `IDENTICAL` duplicate
groups (6 source rows collapsed: repeated listing snapshots of stale stations, and one listing
reading equal to its history row, `26460` 0.09 m at 23/09/2026 15:15); 0 conflicts; 588 forecast
rows excluded as `NOT_A_STATION_OBSERVATION`. 65 sites; 56 `RAINFALL_1H_TOTAL`, 1
`RAINFALL_INTERVAL` and 22 `WATER_LEVEL` sensors.

History series (5-min grid): 0 absent slots in all three non-empty windows (289/289 slots each).

| Series (history day) | Rows | Usable | `-9999` rows |
|---|---:|---:|---:|
| `27608` rainfall interval, 18/09/2026 | 289 | 289 | 0 |
| `26460` water level, 23/09/2026 | 289 | 35 | 254 |
| `27608` water level, 24/09/2024 (+2 listing rows) | 291 | 121 | 170 |

Determinism: a second build into new output roots gave byte-identical processed files and the same
version; a rerun wrote 0 files; SHA-256 of all raw files and of the source captures unchanged.

## 5. Licensing and external blockers

- JPS: PERMISSION REQUIRED (`docs/DATA_LICENSING_AND_ACCESS.md`). JPS network fetch, bulk
  historical retrieval and production polling remain disabled. All JPS-derived outputs are local
  (git-ignored `data/interim/`, `data/processed/`, `data/local/`); no new JPS content was added to
  tracked files. Tests use trimmed fixtures and synthetic edits.
- data.gov.my: CC BY 4.0, attribution kept in raw records and in the dataset manifest.
- Docker runtime: BLOCKED (Windows Virtual Machine Platform/WSL disabled; Phase 0). Phase 2 needs
  no database; no migrations were written.

## 6. Assumptions and limitations

- Timezone: JPS and data.gov.my publish none; `Asia/Kuala_Lumpur` is assumed and flagged on every
  row. UTC instants inherit the assumption.
- Thresholds: history returns present-day thresholds (`CURRENT_NOT_HISTORICAL`); they are kept in
  the unit layer with capture time and excluded from the canonical table. No threshold versioning
  exists yet.
- Source semantics: rainfall `clean`/`chourly`/`c15min`/`tdaily`/`cdaily`/`cyearly`, rainfall
  thresholds, WL `raw`/`ecm`/`clean` and listing daily totals stay unpromoted. The listing
  `RAINFALL_1H_TOTAL` window (trailing vs clock hour) is unverified.
- No physical range, jump or freshness rule is applied; `SOURCE_SEVERITY_ERROR` is recorded, not
  interpreted.
- Coverage: history depth is about two years (`data/metadata/jps/HISTORICAL_AVAILABILITY.md`) and
  no bulk history is held locally, so event counts and multi-station coverage are unmeasured.
- The build keeps one run's quality rows in memory; revisit for multi-year bulk history.
- The three per-layer scripts each repeat ~15 lines of manifest-hash verification that the builder
  also implements; left as is (working, tested code).

## 7. Leakage controls

No value is filled, interpolated or carried in either direction; no windows or aggregates; rows
later than capture + 10 min are excluded and checked; `first_retrieved_at` records availability;
thresholds are not attached as history; no split, label, target or feature exists. As-of use
must take `max(first_retrieved_at, observation_time_utc)` as availability time (10-min tolerance).

An independent review (ml-reviewer) found no high-severity defect; its 3 medium and 5 low findings
(interim write-once vs rebuilt master, absent-slot counting, per-capture value provenance, join
pairing checks, quarantine consistency, `-0.0` conflicts, multiset row accounting, as-of note) were
fixed or documented, each with a regression test.

## 8. Handoff to Phase 3

First Phase 3 task: **Analyze rainfall distributions** (`TASKS.md`). It can consume
`processed/observations/v1/<dataset_version>/observations.jsonl` rows with
`measurement_type = RAINFALL_INTERVAL` (5-min, mm) and `usable = true`, using `quality_summary.json`
for coverage and missingness, and `dataset_manifest.json` to cite the dataset version. It needs a
larger history set first, which requires JPS permission for bulk retrieval; with local captures
only one rainfall-history day exists. Label definition (+30/+60/+120) and threshold versioning
belong to Phase 3 and are not started.
