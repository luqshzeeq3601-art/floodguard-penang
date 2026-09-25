# Rainfall Distribution Analysis

Status: implemented 2026-09-25 (Phase 3 task "Analyze rainfall distributions"). Code:
`src/floodguard/analysis/rainfall.py`; CLI `scripts/analyze_rainfall.py`; tests
`tests/test_rainfall_analysis.py` (synthetic data only).

This is descriptive EDA. It creates no labels, features, rolling or cumulative windows, splits,
fitted transformations or rainfall thresholds, and it does not use Waspada/Amaran/Bahaya (those
are water-level thresholds).

## 1. Evidence levels

| Level | Meaning | Supported by the local captures? |
|---|---|---|
| `IMPLEMENTATION_VERIFICATION` | The code runs end to end on real processed data and the contract holds | Yes |
| `STATION_WINDOW_DESCRIPTIVE` | Statistics describe the analysed window of one station, nothing more | Yes (one station, one day) |
| `NETWORK_HISTORICAL` | Station comparisons, seasonal/monsoon behaviour, Penang-wide characteristics | No: needs `station_comparison` and `seasonal_analysis` both SUFFICIENT |

The output lists the supported levels in `evidence_levels_supported`.

## 2. Input contract

Input is one Phase 2 processed dataset, `processed/observations/v1/<dataset_version>/`
(`docs/HISTORICAL_PIPELINE.md`). `load_processed_dataset` (shared with the water-level analysis
in `analysis/dataset.py` since 2026-09-25) rejects it unless the directory name
equals `dataset_version`, `observations.jsonl` matches `observations_sha256` and
`observations_rows`, all stored checks passed and the summary is `quality_summary/v1`.

Row selection (`select_rainfall_intervals`):

- `measurement_type = RAINFALL_INTERVAL`: JPS history `raw`, rain in the 5-min interval ending at
  the observation time (`docs/UNIT_POLICY.md`). `RAINFALL_1H_TOTAL` and `WATER_LEVEL` rows are
  counted in `excluded_rows_by_measurement_type` and never enter any statistic. Unpromoted JPS
  fields (`clean`, `chourly`, `c15min`, `tdaily`, `cdaily`, `cyearly`) cannot appear in the table;
  an unknown measurement type is a contract error.
- A selected row must have unit `mm`, sensor type `RAINFALL`, sensor and site identity, tz-aware
  UTC and local times that are the same instant, a local offset equal to the source's zone in the timestamp policy registry
  (`docs/TIMESTAMP_POLICY.md`), a boolean `usable`, and a unique
  `(fg_sensor_id, observation_time_utc)`.
  A usable row must have a finite value ≥ 0. Any violation raises `RainfallContractError` (an
  alias of the shared `AnalysisContractError`).
- Only `usable = true` values enter the statistics. Non-usable rows (markers such as `-9999`,
  conflicts) are counted with their flags; a missing value is never treated as zero.

The per-series 5-min cadence report of the quality summary (expected and absent slots) is copied
into each station's `coverage`.

## 3. Definitions

| Term | Definition |
|---|---|
| Value | mm per 5-min interval, as observed; no conversion or transformation |
| Zero interval | usable value == 0 mm (a true zero) |
| Wet interval | usable value > `wet_threshold_mm` (default 0 mm) |
| All-interval statistics | over every usable interval, zeros included |
| Wet-only statistics | over wet intervals only |
| Quantile | `numpy.quantile(method="linear")` (Hyndman & Fan type 7) |
| Standard deviation | sample, `ddof=1` |
| Skewness | adjusted Fisher-Pearson G1 (the pandas `Series.skew` estimator) |
| Concentration | largest interval's share of the window total; fewest intervals holding half of it |
| Covered day | local date with ≥ 80% (231) of its 288 intervals usable; an interval belongs to the date of its start, so a 00:00 value counts for the previous day |
| Complete month | year-month with ≥ 20 covered days; complete year = 12 complete months |

Precipitation is zero-inflated, so every station reports zero and wet counts and proportions,
all-interval statistics and wet-only statistics side by side; the mean and standard deviation are
never reported alone. No logarithm or other transformation is applied.

## 4. Sample-size guards and sufficiency rules

All rules are fields of `RainfallAnalysisConfig`; defaults are conservative guards, not
hydrological thresholds, and were not tuned to the local data.

- Quantile `q` is reported only if `n ≥ ceil(min_tail_count / min(q, 1 − q))` with
  `min_tail_count = 5`: p50 10, p75 20, p90 50, p95 100, p99 500 values. Otherwise the result is
  `{"status": "INSUFFICIENT_SAMPLE", "n", "required_n"}`.
- The median is the p50 quantile and follows the same rule (10 values).
- Skewness needs 30 values; a constant sample gives `UNDEFINED_ZERO_VARIANCE`. Std needs 2.
- The concentration metrics need `min_wet_samples` (10) positive intervals.
- Count, total, mean, min and max are always reported: they describe the window.

| Analysis | SUFFICIENT when |
|---|---|
| `basic_descriptive` | one station has ≥ 1 covered day |
| `wet_only_statistics` | one station has ≥ 10 wet intervals |
| `wet_only_quantiles` | one station has enough wet intervals for every configured quantile (≥ 500 for p99) |
| `station_comparison` | 2 stations share ≥ 30 covered days |
| `seasonal_analysis` | one station has all 12 calendar months complete in ≥ 2 years |
| `monsoon_comparison` | the seasonal rule, **and** season boundaries from a verified METMalaysia definition (`monsoon_definition_source`, unset; the code records the source, it cannot verify it) |
| `extreme_event_analysis` | one station has ≥ 20 complete years (annual-maximum / return-period methods) |

JPS history reaches back only about two years (`data/metadata/jps/HISTORICAL_AVAILABILITY.md`),
so `extreme_event_analysis` cannot become SUFFICIENT from JPS history alone.

## 5. Outputs

```text
.venv\Scripts\python.exe scripts\analyze_rainfall.py --dataset <processed dataset dir or manifest>
```

Options: `--output-root` (default `data/analysis/rainfall`), `--station-master-dir` (default
`data/local/station_master`; optional, adds `jps_internal_id`, district and basin to each station
for later grouping; its SHA-256 is recorded as `input.station_master_sha256`). No network access.
Exit 0 written or already present; 2 rejected. Since the missingness task, the shared
`load_station_context` refuses a station master whose `sensors.csv` hash does not match the
manifest's `station_master_origin` (as the water-level script already did); the local output for
`f4cf1c25f5cda102` is unchanged. A changed `sites.csv` gives different bytes for the same
`dataset_version` and is refused by the write-once rule: write it to a new `--output-root`.

`<output-root>/<dataset_version>/rainfall_distribution.json` (`rainfall_distribution/v1`):
`dataset_version`, input hash and selection, definitions, config, `network` (stations analysed,
rainfall sensors in the station master), `stations[]` (window, coverage, occurrence,
`all_intervals`, `wet_only`, concentration, calendar coverage), `sufficiency`,
`evidence_levels_supported`, scope note. Keys are sorted and floats rounded to 6 decimals, with no
run timestamp, so identical inputs give identical bytes. The file is write-once: an identical
rerun is a no-op, different content is refused.

No plots are produced: no plotting library is a project dependency, and none was added for this
task. Figures belong to the Phase 3 task "Produce baseline EDA figures".

## 6. Leakage

Every statistic is a function of the set of usable values of one station window; no value is
transformed using other rows, nothing is filled, and no window, lag or centred operation exists.
Full-window statistics are exploratory. Any transformation later fitted for training (e.g. a
scaler) must be fitted on the training period only (Phase 4/5).

## 7. Local validation (2026-09-25)

Input: the 9 local Phase 1 captures re-ingested into a scratch raw store outside the repository
(the Phase 2 scratch output no longer existed) and rebuilt with `build_historical_dataset.py`:
dataset version `f4cf1c25f5cda102`, with the same row counts as the Phase 2 record (1,611
validated, 1,017 canonical, 593 usable). The version differs from the Phase 2 record
(`9995ddafeb644d7d`) because each raw record stores the `--source-reference` given at ingestion,
and the reference strings used then were not recorded.

**This is one station and one day. It is an implementation check, not a sample of Penang
rainfall.**

| Measure | Value |
|---|---|
| Stations analysed / rainfall sensors in station master | 1 / 56 |
| `RAINFALL_INTERVAL` rows / usable / not usable | 289 / 289 / 0 |
| Absent 5-min slots (quality summary) | 0 of 289 |
| Covered days / complete months / complete years | 1 / 0 / 0 |
| Estimable all-interval quantiles | p50, p75, p90, p95 (p99 needs 500) |
| Estimable wet-only quantiles | p50, p75 (p90 needs 50 wet intervals) |
| Sufficiency | basic descriptive and wet-only statistics SUFFICIENT; wet-only quantiles, station comparison, seasonal, monsoon and extreme-event INSUFFICIENT |
| Evidence levels | `IMPLEMENTATION_VERIFICATION`, `STATION_WINDOW_DESCRIPTIVE` |
| Two runs (separate output roots) | byte-identical, SHA-256 `051ac570…af18c06f`; rerun wrote nothing; 39 raw, capture and processed file hashes unchanged |

Rainfall amounts (totals, means, quantiles in mm) are derived JPS values whose publication is
UNCERTAIN (`docs/DATA_LICENSING_AND_ACCESS.md` section 4), so they stay in the git-ignored local
output only. Zero and wet counts of this identifiable station-day are also kept local; this
document records coverage counts and statuses.

An independent review (ml-reviewer) found no high-severity defect. Its 2 medium and 4 low findings
(unguarded median, missing station-master lineage, unguarded concentration metric, a
basic-descriptive rule of 30 intervals, unchecked local offset, derived counts in this document)
were fixed, each with a test where code changed.

## 8. Limitations

- One station-day cannot show seasonality, monsoon behaviour, station differences, flood-trigger
  rainfall, extremes or return periods. Those need bulk JPS history, which is blocked pending JPS
  permission; synthetic data is used for tests only, never as evidence.
- The timezone is assumed (`Asia/Kuala_Lumpur`), so day and month boundaries inherit the
  assumption (`docs/TIMESTAMP_POLICY.md`).
- Whether a JPS `raw` value after absent 5-min rows covers the gap is unknown
  (`docs/UNIT_POLICY.md`); absent slots are reported, not filled.
- The observed values' measurement resolution is not documented by JPS; it is not asserted here.
- Rainfall-event segmentation is not part of this task.
