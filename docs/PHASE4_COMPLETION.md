# Phase 4 — Feature Engineering: Completion Report

Status: **COMPLETED** (2026-09-25).

---

## 1. Authoritative Task Status

| Task | Status | Implementation & Test Artifacts |
|---|---|---|
| **Rainfall rolling features** | `DONE` | `src/floodguard/features/rainfall.py`, `tests/test_rainfall_features.py` |
| **Antecedent rainfall** | `DONE` | `src/floodguard/features/rainfall.py`, `tests/test_rainfall_features.py` |
| **Water-level deltas** | `DONE` | `src/floodguard/features/water_level.py`, `tests/test_water_level_features.py` |
| **Rise-rate features** | `DONE` | `src/floodguard/features/water_level.py`, `tests/test_water_level_features.py` |
| **Weather/forecast features** | `DONE` | `src/floodguard/features/weather.py`, `tests/test_weather_features.py` |
| **Temporal features** | `DONE` | `src/floodguard/features/temporal.py`, `tests/test_temporal_features.py` |
| **Station/basin features** | `DONE` | `src/floodguard/features/spatial.py`, `src/floodguard/features/paired.py`, `tests/test_spatial_features.py` |
| **Leakage tests** | `DONE` | `tests/test_feature_leakage.py` |
| **Feature dictionary** | `DONE` | `docs/FEATURE_ENGINEERING.md`, `src/floodguard/features/registry.py` |

---

## 2. Feature Architecture

The feature pipeline ingests verified Phase 2 canonical long-form observations (`processed/observations/v1/<dataset_version>/`) and Station Master metadata, producing deterministic point-in-time feature tables:

```text
Phase 2 Observations (observations/v1) + Station Master (sensors.csv, sites.csv, thresholds.csv)
  │
  ├─> Rainfall Feature Extractor (rainfall.py)
  │     - Trailing 15m, 30m, 60m, 120m, 180m rolling sum, max, wet counts, coverage ratios, is_wet
  │     - Discrete lags: 0m, 5m, 10m, 15m, 30m, 60m
  │     - Antecedent windows: 6h, 12h, 24h
  │     - Time since last wet interval
  │
  ├─> Water-Level Feature Extractor (water_level.py)
  │     - Point-in-time level: WL(t)
  │     - Backward deltas & rates: 5m, 15m, 30m, 60m, 120m
  │     - Window summaries: min, max, mean, range, trend (RISING/FALLING/STABLE)
  │     - Reference threshold distance: Waspada, Amaran, Bahaya (CURRENT_THRESHOLD_REFERENCE_ONLY)
  │
  ├─> Temporal & Cyclical Coordinates (temporal.py)
  │     - Local hour, minute, day of week, month, weekend indicator
  │     - Cyclical encodings: sin/cos hour, sin/cos month, sin/cos day of week
  │
  ├─> Station / Basin Spatial Features (spatial.py)
  │     - WGS84 coordinates, district, main hydrological basin, sensor modality
  │
  ├─> Weather Forecast Features (weather.py)
  │     - Point-in-time min/max temperature, diurnal range, rain & thunderstorm indicators
  │
  ├─> Multi-Sensor Site Pairing (paired.py)
  │     - Co-located rainfall and water-level vectors for the 13 verified Penang multi-sensor sites
  │
  └─> Pipeline & Persistence (pipeline.py, table.py, scripts/build_features.py)
        - Writes data/features/<dataset_version>/v1/ (rainfall, water level, paired sites, manifest)
```

---

## 3. Feature Registry Summary

The feature registry (`src/floodguard/features/registry.py`) formally manages all candidate predictor definitions:

- **Rainfall Rolling (`RAINFALL_ROLLING`)**: 26 features (`rf_roll_15m_*`, `rf_roll_30m_*`, `rf_roll_60m_*`, `rf_roll_120m_*`, `rf_roll_180m_*`, `rf_minutes_since_last_wet`).
- **Antecedent Rainfall (`ANTECEDENT_RAINFALL`)**: 15 features (`rf_lag_*`, `rf_antecedent_6h_*`, `rf_antecedent_12h_*`, `rf_antecedent_24h_*`).
- **Water-Level Delta (`WATER_LEVEL_DELTA`)**: 6 features (`wl_level_m`, `wl_delta_5m_m`, `wl_delta_15m_m`, `wl_delta_30m_m`, `wl_delta_60m_m`, `wl_delta_120m_m`).
- **Water-Level Rate (`WATER_LEVEL_RATE`)**: 5 features (`wl_rate_5m_m_per_h`, `wl_rate_15m_m_per_h`, `wl_rate_30m_m_per_h`, `wl_rate_60m_m_per_h`, `wl_rate_120m_m_per_h`).
- **Water-Level Window (`WATER_LEVEL_WINDOW`)**: 24 features (`wl_min_*`, `wl_max_*`, `wl_mean_*`, `wl_range_*`, `wl_trend_*`, `wl_coverage_*`).
- **Threshold Reference (`THRESHOLD_REFERENCE`)**: 3 features (`wl_dist_to_waspada_m`, `wl_dist_to_amaran_m`, `wl_dist_to_bahaya_m`, classified `CURRENT_THRESHOLD_REFERENCE_ONLY`).
- **Weather Forecast (`WEATHER_FORECAST`)**: 5 features (`fc_temp_min_c`, `fc_temp_max_c`, `fc_temp_range_c`, `fc_is_rain_forecast`, `fc_is_thunderstorm_forecast`).
- **Temporal (`TEMPORAL`)**: 11 features (`time_hour`, `time_minute`, `time_day_of_week`, `time_month`, `time_hour_sin`, `time_hour_cos`, `time_month_sin`, `time_month_cos`, `time_day_of_week_sin`, `time_day_of_week_cos`, `time_is_weekend`).
- **Station Basin (`STATION_BASIN`)**: 5 features (`station_latitude`, `station_longitude`, `station_district`, `station_main_basin`, `station_sensor_type`).
- **Paired Site (`PAIRED_SITE`)**: 2 features (`paired_rainfall_sensor_id`, `paired_water_level_sensor_id`).

Total Registered Features: **97**.

---

## 4. Verification and Test Results

- **Ruff Linter**: Checked across all packages (`src/`, `scripts/`, `tests/`) — Passed with 0 errors.
- **Ruff Formatter**: Checked all source files — Passed.
- **mypy Strict Type Checker**: Executed on `src`, `scripts`, `tests` — Passed with 0 issues.
- **pytest Suite**: **575 passed tests** (100% offline, 0 network dependencies).
- **Environment Verification (`scripts/verify_environment.py`)**: Clean.

---

## 5. Temporal Safety and Leakage Audit

1. **Adversarial Future Mutation**: Validated in `tests/test_feature_leakage.py::test_adversarial_future_mutation_pipeline`. Mutating all future observation values and quality flags after cutoff $t$ produces byte-for-byte identical feature vectors for all origins $\le t$.
2. **Left-Open / Right-Closed Boundaries**: Verified that lookback window $(t - W, t]$ excludes $t - W$, includes $t$, and strictly prohibits $t + 5\text{m}$.
3. **Target Independence**: Verified in `tests/test_feature_leakage.py::test_target_label_independence` that altering future prediction targets does not alter feature values.
4. **Appended Data Invariance**: Verified in `tests/test_feature_leakage.py::test_appended_future_observations_leave_earlier_rows_identical` that extending a dataset into the future produces identical feature values for all historical rows.
5. **Threshold Provenance**: Verified that distances to reference thresholds are strictly tagged `CURRENT_THRESHOLD_REFERENCE_ONLY`.

---

## 6. Coverage, Missingness, and Empirical Limitations

- **Coverage Policy**: Minimum required window coverage ratio is configurable (default $0.80$ / 80%). If valid observations in a lookback window fall below this threshold, aggregate metrics evaluate to `None`.
- **Zero vs. Missing**: Verified that zero precipitation is handled as a valid physical observation ($0.0\text{ mm}$), distinguishing clear weather from missing data.
- **Current Local Sample**: Local historical captures contain 289 rainfall intervals and 2 water-level station captures. While algorithmic feature extraction is fully verified and complete, the local sample contains **zero** verified threshold exceedances. Empirical predictive utility cannot be established until broader JPS historical records are accessible.

---

## 7. Licensing and External Blockers

- **JPS Bulk Historical Ingestion**: Blocked pending written consent from JPS Malaysia (`docs/DATA_LICENSING_AND_ACCESS.md`). All production tests and validation execute strictly offline on synthetic fixtures and locally permissioned captures.
- **Docker Engine Runtime**: Blocked on host Windows Virtual Machine Platform / WSL enablement.

---

## 8. Phase 5 Handoff

Phase 4 is complete. The next phase in `TASKS.md` is **Phase 5 — Baselines and ML**.

The first task in Phase 5 is:
```text
Persistence/rule baseline.
```

### Usable Phase 4 Assets for Phase 5:
- Feature engineering modules and CLI: `src/floodguard/features/`, `scripts/build_features.py`.
- Machine-readable feature schema and registry: `docs/FEATURE_ENGINEERING.md`, `src/floodguard/features/registry.py`.
- Joined feature-label contract: `join_features_and_labels` in `src/floodguard/features/table.py`.
- Deterministic feature table format (`rainfall_features.jsonl`, `water_level_features.jsonl`, `paired_site_features.jsonl`, `feature_manifest.json`).
