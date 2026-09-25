# Missingness and Observed-Data-Outage Analysis

Status: implemented 2026-09-25 (Phase 3 task "Analyze missingness and outages"). Code:
`src/floodguard/analysis/missingness.py` (shared input contract in
`src/floodguard/analysis/dataset.py`); CLI `scripts/analyze_missingness.py`; tests
`tests/test_missingness_analysis.py` (synthetic data only).

This is descriptive data-quality EDA. It quantifies where canonical observations are missing,
how missing observations are arranged in time and which source markers they carry. It does not
infer why an observation is missing, does not claim that any sensor, power supply or telemetry
link failed, and does not fill, interpolate, forward-fill or replace anything. It produces no
features, labels, imputation strategy or live freshness status.

## 1. Terminology

| Term | Meaning |
|---|---|
| Expected slot | A 5-min grid time inside a cadence window (section 3). Nowhere else. |
| Usable slot | A canonical row with `usable = true` at the slot. Zero rainfall and zero water level are usable. |
| Missing observation | An expected slot whose measurement is unusable: a source row with a missing marker or blocking flag, or no canonical row at all (`ABSENT_SLOT`). |
| Missing run | Maximal run of consecutive missing expected slots of one window. |
| Usable (observed) run | Maximal run of consecutive usable expected slots of one window. |
| Observed data outage | Used only as a synonym for missing run. JPS publishes no device or communications status, so no outage is ever a confirmed sensor, power, hardware, telemetry or communications failure (`cause_attributed: false`). |
| Point-in-time observation | A listing row: availability is counted, but no cadence, gap, run or outage is derived. |

## 2. Input contract

One Phase 2 processed dataset, `processed/observations/v1/<dataset_version>/`, loaded by the
shared verified loader (`analysis/dataset.py`, as for the rainfall and water-level analyses):
manifest hash, row count, stored checks and schema versions verified. Raw JPS files are never
read.

- All three canonical measurement types are selected with `select_measurement` (unit, sensor
  type, identity, time zone, usable value, one row per sensor and instant; a repeated canonical
  key is rejected). They are analysed separately and never combined.
- Each row must carry `quality_flags`/`datasets` lists and a non-empty `provenance` whose entries
  name a `*_history` or `*_listing` dataset and an `ingestion_batch_id`. A usable row with a
  blocking flag, or a not-usable row without one, is rejected (Phase 2 invariant
  `usable_matches_flags`).
- `quality_summary.json` is not hashed by the manifest. Its per-type canonical row counts must
  match the loaded rows, and, if it has series entries, every analysed series must have one whose
  row and usable counts match; only `history_rows_not_in_canonical` is then used.

**Station-master lineage (shared).** `load_station_context` supplies station metadata only from
the station master whose `sensors.csv` hash matches the manifest's `station_master_origin`; any
other master is refused (exit 2). It is used by the rainfall, water-level and missingness scripts.
Previously only the water-level script enforced this; the rainfall script now does too. The
manifest records only the `sensors.csv` hash, so `sites.csv` (district, basin) is hashed into
`station_master_sha256` but not verified; the output says so in `input.station_master_lineage`.
The
local rainfall and water-level outputs for `f4cf1c25f5cda102` are reproduced byte-identically
(rerun is a write-once no-op).

Every output records `dataset_version`, `observations_sha256`, `station_master_origin`,
`station_master_sha256` (sensors.csv + sites.csv), the observation and quality-summary schema
versions and the manifest's component versions.

## 3. Expected cadence and window boundaries

The 5-min cadence (`validation.summary.HISTORY_CADENCE`) is verified for JPS **history**
responses only (`data/metadata/jps/HISTORICAL_AVAILABILITY.md`; each captured history day has
289 rows, 00:00 to 24:00 local). Listing updates are heterogeneous (some stations ~15 min, others
delayed tens of minutes; `data/metadata/jps/LIVE_ACCESS.md`), so listing rows never get an
expected cadence and are summarised under `point_in_time` (rows, usable rows, missing rows by
type), with `outage_interpretation: NONE`.

**Cadence windows** (`cadence_windows`), per sensor and measurement type:

1. A history capture is the canonical rows of one ingestion batch of a `*_history` dataset
   (from `provenance`). Its span is its first to last row. Phase 2 does not preserve the requested
   query interval, so the captured rows are the only boundary evidence
   (`boundary_evidence: HISTORY_CAPTURE_ROWS`); no slot before the first or after the last
   captured row is ever generated.
2. Captures that overlap, or whose spans are at most one step (5 min) apart, are merged.
   Captures further apart are separate windows (`SEPARATE_CAPTURES`): the time between them is
   not classified at all, so a 2024 capture and a 2026 capture are never one outage.
3. Inside a window, consecutive rows more than `max_absent_gap_minutes` (60) apart split it
   (`GAP_EXCEEDS_MAX_ABSENT_GAP`); the gap is recorded in `window_boundaries` with
   `slots_between_classified: false`.
4. A window with any row off the 5-min grid is `UNVERIFIED_OFF_GRID_ROWS`: row counts by type
   only, no slots, coverage or runs.
5. Otherwise (`VERIFIED_5MIN_HISTORY_GRID`) every grid time from the first to the last row is an
   expected slot.

A row that merged a history and a listing capture of the same instant is a history row. A
listing-only row at an expected slot does not fill it: the slot is `LISTING_ONLY_SLOT` (a
missing history slot with a canonical listing row, not an absent slot), and the row is counted
in `listing_only_rows_in_window` and `point_in_time`.

The water-level analysis splits observation windows at gaps > 1 day over all rows, which is right
for not pooling levels but would turn a sub-day capture gap into missing slots here. The two
window definitions therefore stay separate; no shared helper was extracted.

## 4. Missing classification

A row's state comes from the Phase 2 quality flags (never from a null value alone), first match
wins; every blocking flag on missing rows is also counted in `missing_flags`.

| Type | Evidence |
|---|---|
| `DUPLICATE_CONFLICT` | `DUPLICATE_CONFLICT` (captures disagree; unresolved). Checked first, because a conflict row carries the union of its captures' flags (e.g. `-9999` from one capture) |
| `SENTINEL_-9999` | `VALUE_MISSING_SENTINEL` (value `-9999`) |
| `VALUE_ERROR` | `VALUE_SOURCE_ERROR` (value text `ERROR`; meaning undocumented) |
| `TIADA_DATA` | `VALUE_NO_DATA_MARKER` |
| `BLANK` | `VALUE_EMPTY` |
| `NON_NUMERIC` | `VALUE_NON_NUMERIC` |
| `OTHER_NOT_USABLE` | any other blocking flag |
| `LISTING_ONLY_SLOT` | no history row, but a listing-only canonical row at the slot |
| `ABSENT_SLOT` | no canonical row at the expected slot |

JPS **severity** `ERROR` (`SOURCE_SEVERITY_ERROR`, a history QC field beside the value) is a
separate source state: `source_severity_error` counts flagged rows by their usable/missing state.
It is not the same as the value `ERROR` and is never read as a failure.

`ABSENT_SLOT` vs marker row: a marker row is observed-by-source but measurement-missing; an absent
slot has no canonical row. Structurally unusable or future-dated source rows never reach the
canonical table, so they would appear as absent slots. `absent_slot_attribution` says
`NO_VALIDATED_HISTORY_ROW_WITH_VALID_TIME` when the quality summary shows no validated history row
of that series was excluded, else `UNRESOLVED`; dataset-wide exclusion counts are copied into
`input.excluded_quality_rows`.

## 5. Per-window metrics and runs

Per verified window: bounds (UTC and local), ingestion batches, datasets, expected / usable /
missing slots, coverage and missing percentages, absent slots, missing slots by type, first and
last missing slot, `starts_with_missing`, `ends_with_missing`, full local days, missing runs
(count, runs touching a window boundary, longest, length summary), usable runs (count, longest)
and the full ordered run list.

**Run algorithm** (`segment_runs`): scan the window's consecutive expected slots in time order;
a run ends when the usable/missing state changes or the window ends. Windows never share slots,
so a run can never cross a gap between captures. Each run records `start`/`end` (UTC and local),
`slots` = k, `first_to_last_slot_minutes` = (k - 1) × 5 and `slot_minutes` = k × 5 (no extra
interval is added: a single missing slot spans 0 min first-to-last and 5 min of slots),
`at_window_start`/`at_window_end` (the run may continue outside the capture: censored), and for
missing runs the slots by type. The longest run is the earliest of equal lengths.

**Run-length statistics** (`describe_lengths`): count, min and max are reported always; the mean
needs >= 5 runs; quantile q needs `ceil(5 / min(q, 1 - q))` runs (p50: 10, p25/p75: 20, p90:
50), else `INSUFFICIENT_SAMPLE` with `n` and `required_n`. Type-7 quantiles.

**Network summary** per measurement type: sums of expected, usable and missing slots over
verified windows and `slot_weighted_coverage_percent` = sum usable / sum expected. This is
slot-weighted (longer windows weigh more), is not an average of sensor percentages, is never
combined across measurement types and is not a reliability score. No sensor is labelled
reliable, unreliable, healthy or unhealthy.

## 6. Sufficiency

Per measurement type; every rule is a configurable project guard (`MissingnessConfig`), not a
statistical law.

| Analysis | Requirement |
|---|---|
| `window_level_missingness` | one verified cadence window |
| `run_length_analysis` | one verified window with >= 10 missing runs (median) |
| `sensor_comparison` | >= 2 sensors each with >= 30 full windowed local days, one pair of them sharing >= 30 |
| `network_wide_comparison` | the above for >= 50% of the station-master sensors of the type |
| `seasonal_missingness` | one sensor with all 12 calendar months complete (>= 20 full days) in >= 2 years |
| `monsoon_missingness` | seasonal, plus verified METMalaysia monsoon boundaries |
| `long_term_reliability` | one sensor with >= 10 complete years (coverage only, never a label) |
| `live_outage_detection` | always INSUFFICIENT: needs a separately validated live cadence/freshness policy |

Evidence levels: `IMPLEMENTATION_VERIFICATION`; `WINDOW_DESCRIPTIVE` when a window-level analysis
is supported; `NETWORK_HISTORICAL` only with network-wide and seasonal support.

## 7. CLI and output

```text
.venv\Scripts\python.exe scripts\analyze_missingness.py --dataset <processed dataset dir or manifest>
```

Options: `--output-root` (default `data/analysis/missingness`), `--station-master-dir` (default
`data/local/station_master`; optional; must be the dataset's station master). No network access.
Exit 0 written or already present; 2 rejected. Output
`<output-root>/<dataset_version>/missingness.json` (`missingness/v1`): keys sorted, floats
rounded to 6 decimals, no run timestamp, so identical inputs give identical bytes; write-once.
No plots (figures belong to "Produce baseline EDA figures").

## 8. Local validation (2026-09-25)

Input: processed dataset `f4cf1c25f5cda102`. This is the same local rebuild used for the
rainfall and water-level analyses, kept in a scratch directory outside the repository. **It holds
three one-day history-capture windows and two listing snapshots. It validates the
implementation and describes those windows only. It is not evidence of station or network
reliability.**

| Measure | Value |
|---|---|
| Rows by type | `RAINFALL_INTERVAL` 289, `WATER_LEVEL` 620, `RAINFALL_1H_TOTAL` 108 |
| Verified cadence windows | 3 (1 rainfall, 2 water level), each with 289 expected slots; no window boundaries |
| Rainfall history window (27608) | 289 of 289 usable; 0 missing runs; one usable run of 289 slots |
| Water level 26460 | 35 of 289 usable (12.1%); 254 `SENTINEL_-9999`; 2 missing runs (longest 149 slots), both touching a window edge (the window starts and ends with missing slots); 1 usable run of 35 |
| Water level 27608 (2024 history day) | 119 of 289 usable (41.2%); 170 `SENTINEL_-9999`, 167 of them with JPS severity `ERROR`; 2 missing runs (longest 167 slots; 1 at the window start); 2 usable runs (longest 117) |
| Value `ERROR`, `Tiada Data`, blank, non-numeric, conflict, listing-only and absent slots | 0 in every window; absent-slot attribution `NO_VALIDATED_HISTORY_ROW_WITH_VALID_TIME` |
| Point-in-time (listing) rows | `RAINFALL_1H_TOTAL` 108 rows on 56 sensors; `WATER_LEVEL` 42 rows. 27608's 2026 readings stay here and are never joined to its 2024 window. All usable; no cadence or outage derived |
| Water-level slot-weighted coverage | 154 of 578 slots (26.6%) over two windows only; not a network or reliability figure |
| Run-length median | `INSUFFICIENT_SAMPLE` in every window (at most 2 runs; 10 required) |
| Sufficiency | Window-level missingness SUFFICIENT for `RAINFALL_INTERVAL` and `WATER_LEVEL`. Run-length distribution, sensor comparison, network-wide, seasonal, monsoon, long-term reliability and live outage detection INSUFFICIENT. Nothing supported for `RAINFALL_1H_TOTAL` |
| Evidence levels | `IMPLEMENTATION_VERIFICATION`, `WINDOW_DESCRIPTIVE` |
| Determinism | 4 runs (two scratch roots, then the default root twice) gave byte-identical output, SHA-256 `8114f96b…a6d1b8`. The last rerun wrote nothing. The hashes of 39 raw, processed, capture and station-master files did not change. Rainfall and water-level reruns under the shared lineage check were write-once no-ops (outputs unchanged) |

Detailed run timestamps and sequences are derived JPS data (`docs/DATA_LICENSING_AND_ACCESS.md`).
They stay in the git-ignored local output; this document records counts and statuses only.

An independent review (ml-reviewer) found no high-severity defect. Each finding was fixed and
now has a regression test:

- Medium: a duplicate conflict was reported as its member's `-9999`.
- Medium: a slot holding a listing-only row was labelled absent.
- Low: `sites.csv` lineage was not verified.
- Low: the quality-summary cross-check skipped series with no entry.
- Low: the sensor-comparison overlap rule was stricter than its stated requirement.
- Low: tests were missing for nested captures, merged history/listing rows, and conflict and
  non-numeric markers.

## 9. Limitations

- Four captured history days (three analysed series-windows) and two listing snapshots cannot
  show seasonal, monsoon, network-wide or long-term missingness, nor sensor reliability.
  Broader history is blocked pending JPS permission.
- Window bounds are the first and last captured rows, because Phase 2 does not preserve the
  requested query interval: missing data at the edges of a request that JPS omitted entirely is
  invisible, and runs touching a window boundary are censored.
- The meaning of JPS `-9999`, value `ERROR` and severity `ERROR` is undocumented; they are
  recorded as source states only.
- `max_absent_gap_minutes` (60) is a project guard without JPS evidence; no local capture has an
  absent slot, so it is untested on real data.
- The Phase 2 quality-summary cadence report computes absent slots from a series' first to last
  history row across all captures; with multi-capture series it would count inter-capture time.
  This analysis does not use that number.
- Historical missingness is not live freshness; no FRESH/DELAYED/STALE rule is set here.
