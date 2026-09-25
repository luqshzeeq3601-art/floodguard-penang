# Water-Level Trend Analysis

Status: implemented 2026-09-25 (Phase 3 task "Analyze water-level trends"). Code:
`src/floodguard/analysis/water_level.py` (shared input contract in
`src/floodguard/analysis/dataset.py`); CLI `scripts/analyze_water_level.py`; tests
`tests/test_water_level_analysis.py` (synthetic data only).

This is descriptive EDA. It creates no flood labels, threshold-exceedance events, targets,
features, predictive windows, splits or fitted transformations. It does not interpolate, fill or
smooth, and it does not describe any change as dangerous, safe or flood-like.

## 1. Evidence levels

| Level | Meaning | Supported by the local captures? |
|---|---|---|
| `IMPLEMENTATION_VERIFICATION` | The code runs end to end on real processed data and the contract holds | Yes |
| `STATION_WINDOW_DESCRIPTIVE` | Statistics describe one station's analysed window, nothing more | Yes (two history windows) |
| `NETWORK_HISTORICAL` | Station comparisons, seasonal or long-term behaviour | No: needs `station_comparison` and `seasonal_trend` both SUFFICIENT |

## 2. Input contract

Input is one Phase 2 processed dataset, `processed/observations/v1/<dataset_version>/`
(`docs/HISTORICAL_PIPELINE.md`), loaded by the same verified loader as the rainfall analysis
(`analysis/dataset.py`): directory name = `dataset_version`, `observations.jsonl` matches
`observations_sha256` and `observations_rows`, all stored checks passed, summary is
`quality_summary/v1`. Raw JPS files are never read.

Row selection (`select_water_level`):

- `measurement_type = WATER_LEVEL`, i.e. the values Phase 2 promoted: history `final` and the
  listing `Aras Air (m)(Graf)` (`docs/UNIT_POLICY.md`). History `raw`, `ecm` and `clean` and all
  thresholds are not canonical observations; any unknown measurement type (e.g.
  `WATER_LEVEL_THRESHOLD`) is a contract error. Rainfall rows are counted in
  `excluded_rows_by_measurement_type` and never enter.
- A selected row must have unit `m` (anything else is rejected, not converted), sensor type
  `WATER_LEVEL`, sensor and site identity, tz-aware UTC and local times that are the same instant,
  a local offset matching the source's timezone policy, a boolean `usable`, and a unique
  `(fg_sensor_id, instant)`: a repeated instant is rejected, as the processed contract requires.
  A usable value must be a finite number; negative levels are valid (observed upstream).
- Violations raise `AnalysisContractError`.

Every output records `dataset_version`, `observations_sha256`, `station_master_sha256`
(sensors.csv + sites.csv) and `threshold_reference_sha256` (thresholds.csv) when a station
master is supplied. The script refuses a station master whose `sensors.csv` hash does not match
the manifest's `station_master_origin` (shared `load_station_context`, used by every Phase 3
analysis). `quality_summary.json` is not hashed by the manifest, so
each sensor's summary entry must match the loaded rows (row and usable counts) before its cadence
report is used; a mismatch is a contract error.

## 3. Per-station analysis

Everything is computed per `fg_sensor_id` (with its `fg_site_id`). Absolute levels of different
gauges refer to different datums, channels and thresholds: they are never pooled, averaged or
ranked across stations. The `network` block reports counts only
(`cross_station_level_aggregation: NONE`).

**Observation windows.** A sensor's canonical rows (usable or not) are split wherever consecutive
rows are more than `max_window_gap_minutes` (1 day) apart. Separate captures (e.g. a 2024 history
day and 2026 listing readings of one gauge) are separate windows; level statistics are reported
per window and never pooled across windows (`levels_pooled_across_windows: false`). Per window:
first/last row and usable time, observed duration, rows by source dataset, canonical and usable
rows, usable share, level statistics and net change.

**Level statistics** (per window, usable values only): count, mean, median, sample std
(`ddof=1`), min, max, range and quantiles p5, p25, p50, p75, p95 (`numpy.quantile`, linear =
Hyndman & Fan type 7). Quantile `q` is reported only if
`n ≥ ceil(5 / min(q, 1 − q))` (p50 10, p25/p75 20, p5/p95 100); otherwise
`INSUFFICIENT_SAMPLE` with `n` and `required_n`. Std needs 2 values.

**Net change** = last − first usable value of a window, reported only when the window's usable
values form one continuous run (section 4) and their span is ≤ `max_net_change_span_minutes`
(1 day). A break or continuity-breaking flag between the endpoints gives `SPANS_BREAKS` (with the
number of breaks); a longer span gives `SPAN_EXCEEDS_GUARD`. It is a difference of two readings,
not a fitted trend; the longest run's own net change is in `continuity.longest_run`.

**Missingness** (per station): canonical, usable and not-usable rows, usable share, not-usable
rows by source value (`SOURCE_MARKER:-9999`, blank, …) and by quality flag
(`VALUE_MISSING_SENTINEL`, `SOURCE_SEVERITY_ERROR`, …), plus the quality summary's history cadence
(expected and absent 5-min slots). Missing values are never zero and never filled. A window with
many missing values is reported as such; no station is labelled faulty from a short window.

## 4. Consecutive changes and the gap policy

- **Trend-eligible** row: usable and without a continuity-breaking flag
  (`continuity_breaking_flags`, default `SOURCE_SEVERITY_ERROR`, the JPS `ERROR` severity). In
  the local data every `ERROR` row is also `-9999`; the flag rule makes the break explicit.
- **Pair**: two consecutive trend-eligible observations of one sensor with **no other canonical
  row between them** and a gap ≤ `max_gap_minutes`. Change = later − earlier (m); rate =
  change / gap in hours (m/h); both carry the pair's gap. The change is attributed to the later
  time and uses only that observation and the one before it: it is backward-looking, and no later
  observation can alter it (tested).
- **Break**: any other consecutive eligible observations, with reason `NOT_USABLE_ROW_BETWEEN`
  (a `-9999`, `ERROR`, blank or other not-usable row lies between them) or `GAP_EXCEEDS_MAX`
  (absent slots or a longer gap). No change or rate is computed across a break.
- **Run**: maximal chain of pairs. Reported: number of runs and breaks, breaks by reason, the
  longest run (observations, start, end, duration, net change) and the largest gap between
  consecutive usable observations.

`max_gap_minutes` defaults to **5** (it may not exceed `max_window_gap_minutes`, so no pair
joins two windows), one step of the JPS history grid, which is verified: every
captured history window is on a 5-min grid (`data/metadata/jps/HISTORICAL_AVAILABILITY.md`;
the quality summary's `history_cadence` reports `off_grid_rows = 0`). Any absent slot therefore
breaks continuity. The value was not chosen to increase the number of valid pairs; a larger value
is a configuration change and is recorded in the output's `config`.

**Cadence status** per station: `VERIFIED_5MIN_HISTORY_GRID` when the quality summary reports a
history cadence with no off-grid rows, otherwise `UNVERIFIED` (e.g. listing-only sensors, whose
readings are hours apart and never form pairs under the default). Rate-of-change sufficiency
requires a verified cadence.

**Direction** (neutral, descriptive): `RISING` if change > `stable_tolerance_m`, `FALLING` if
change < −`stable_tolerance_m`, else `STABLE`. The default tolerance is **0**: `STABLE` means the
two readings are numerically equal (changes are rounded to 6 decimals first, removing float
noise; JPS publishes 2 decimals). There is no evidence for a hydrological stability tolerance,
so none is assumed.

Per station: valid pairs, direction counts, pair gaps, statistics of the changes and rates (same
guards as levels), the largest absolute change, and every pair and break with its times.

**Trailing windows** (e.g. 15/30/60-min changes) are not implemented: they are not an acceptance
criterion of this task and would be predictive features (Phase 4). No centred window exists.

## 5. Thresholds (reference only)

JPS Waspada, Amaran and Bahaya are current values: the history endpoint returns today's
thresholds beside old observations, and no threshold version history exists
(`docs/UNIT_POLICY.md`, `docs/PHASE2_COMPLETION.md`). When the station master's
`thresholds.csv` is present they are attached per station as reference metadata:

- `captured_at` must carry a UTC offset and the unit must be `m`, otherwise the file is rejected;
- each entry keeps `threshold_type`, `value_m`, `threshold_source`, `captured_at` and
  `valid_from` (empty in the station master), with `temporal_validity: CURRENT_REFERENCE_ONLY`,
  `valid_at_observation_times: NOT_ESTABLISHED` and `captured_after_last_usable_observation`;
- `NORMAL` is excluded and counted (`excluded_threshold_types`); it is never a target level;
- the station master's `fg_label_eligible` column is not read; `used_as_label: false`;
- no proximity, exceedance or event is computed. `threshold_event_analysis` is always
  INSUFFICIENT.

## 6. Sufficiency rules

Each rule is a configurable project **analysis guard** (`WaterLevelAnalysisConfig`), not a
universal statistical minimum; none was tuned to the local data.

| Analysis | SUFFICIENT when |
|---|---|
| `basic_descriptive` | one station window has ≥ 30 usable observations |
| `quantiles` | one station window has enough usable observations for every configured quantile (100 for p5/p95) |
| `consecutive_change` | one station has ≥ 30 pairs |
| `rate_of_change` | the consecutive-change rule on a station with verified cadence |
| `station_comparison` | ≥ 2 stations with the basic sample share ≥ 30 covered days; coverage and quality metrics only, never raw levels |
| `seasonal_trend` | one station has all 12 calendar months complete (≥ 20 covered days) in ≥ 2 years |
| `monsoon_comparison` | the seasonal rule and a verified METMalaysia season definition (`monsoon_definition_source`, unset) |
| `threshold_event_analysis` | never here: needs thresholds versioned with the period they applied to |
| `long_term_trend` | one station has ≥ 10 complete years |

Covered day: local date with ≥ 80% of its 288 five-minute slots usable. JPS history reaches back
about two years (`HISTORICAL_AVAILABILITY.md`), so `long_term_trend` cannot become SUFFICIENT from
JPS history alone.

## 7. Outputs

```text
.venv\Scripts\python.exe scripts\analyze_water_level.py --dataset <processed dataset dir or manifest>
```

Options: `--output-root` (default `data/analysis/water_level`), `--station-master-dir` (default
`data/local/station_master`; optional; adds `jps_internal_id`, district, basin and the threshold
reference). No network access. Exit 0 written or already present; 2 rejected.

`<output-root>/<dataset_version>/water_level_trends.json` (`water_level_trends/v1`): input hashes
and selection, definitions, config, `network` (counts only), `stations[]` (coverage, observation
windows, continuity, consecutive changes with pairs and breaks, calendar coverage, threshold
reference), `sufficiency`, `evidence_levels_supported`, scope. Keys sorted, floats rounded to 6
decimals, no run timestamp: identical inputs give identical bytes. Write-once: an identical rerun
is a no-op; different content is refused (write to a new `--output-root`).

No plots: no plotting library is a project dependency. Figures belong to the Phase 3 task
"Produce baseline EDA figures".

## 8. Local validation (2026-09-25)

Input: processed dataset `f4cf1c25f5cda102` (the same local rebuild used for the rainfall
analysis, in a scratch directory outside the repository; `docs/RAINFALL_DISTRIBUTION_ANALYSIS.md`
section 7). **These are two captured history windows plus two listing snapshots. They validate
the implementation and describe those windows only.**

| Measure | Value |
|---|---|
| `WATER_LEVEL` rows / usable | 620 / 196 (397 rainfall rows excluded) |
| Sensors analysed / in station master | 22 / 22 (20 listing-only sensors with 2 readings each) |
| 26460 | 1 window: 289 history rows (+1 identical listing row merged), 35 usable (12.1%), 254 `-9999`; one run of 35 observations, 34 pairs, 0 breaks; window net change OK |
| 27608 | 2 windows: 2024 history day, 289 rows, 119 usable (41.2%), 170 `-9999` (167 with `ERROR`); 2026 listing, 2 rows; 117 pairs, 3 breaks, longest run 117 observations; both window net changes `SPANS_BREAKS` |
| Listing-only sensors | 20 × 2 readings hours apart: no pairs, cadence `UNVERIFIED`, net change `SPANS_BREAKS` |
| Cadence | both history sensors `VERIFIED_5MIN_HISTORY_GRID`, 0 absent slots |
| Covered days / complete months / years | 0 / 0 / 0 for every sensor |
| Sufficiency | basic descriptive, quantiles, consecutive change, rate of change SUFFICIENT; station comparison, seasonal, monsoon, threshold events, long-term INSUFFICIENT |
| Evidence levels | `IMPLEMENTATION_VERIFICATION`, `STATION_WINDOW_DESCRIPTIVE` |
| Threshold reference | 81 current thresholds on 22 sensors (NORMAL excluded), all `CURRENT_REFERENCE_ONLY`, captured 2026-09-24 |
| Two runs (separate output roots) | byte-identical, SHA-256 `c525d094…df63d0b594`; rerun wrote nothing; 135 raw, capture, station-master and processed file hashes unchanged |

Water levels, changes and rates are derived JPS values whose publication is UNCERTAIN
(`docs/DATA_LICENSING_AND_ACCESS.md` section 4); they stay in the git-ignored local output. This
document records counts and statuses only.

The first local run pooled 27608's 2024 history day with its 2026 listing readings into one
level sample, which gave an artefactual range; observation windows were introduced to fix it
(regression test `test_levels_not_pooled_across_separate_captures`).

An independent review (ml-reviewer) found no high-severity defect. Its medium finding (window net
change reported across `-9999` rows and long gaps) and three low findings (tz-naive threshold
`captured_at` crashing the script, the unhashed quality summary and an unchecked station master
driving lineage/cadence, `max_gap_minutes` able to exceed the window split) were fixed, each with
a regression test.

## 9. Limitations

- Two station-days cannot show seasonal, monsoon, long-term, flood-frequency, recurrence or
  station-reliability behaviour, nor Penang-wide hydrology. Broader history is blocked pending
  JPS permission.
- Datums of JPS gauges are not documented; levels are comparable only within one gauge.
- The timezone is assumed (`Asia/Kuala_Lumpur`, `docs/TIMESTAMP_POLICY.md`).
- The meaning of JPS `ERROR` severity and the pre-QC fields is undocumented; `final` is used as
  promoted.
- Thresholds are current values only; no historical exceedance can be established.
- Rates at 5-min resolution amplify the 0.01 m publication step (one step = 0.12 m/h); single
  pairs are not evidence of a sustained rate.
