# Feature Engineering and Feature Dictionary (`features/v1`)

Status: **COMPLETED** (2026-09-25, Phase 4). Code: `src/floodguard/features/` (`rainfall.py`, `water_level.py`, `weather.py`, `temporal.py`, `spatial.py`, `paired.py`, `table.py`, `pipeline.py`, `registry.py`); CLI: `scripts/build_features.py`; Tests: `tests/test_rainfall_features.py`, `tests/test_water_level_features.py`, `tests/test_weather_features.py`, `tests/test_temporal_features.py`, `tests/test_spatial_features.py`, `tests/test_feature_leakage.py`, `tests/test_feature_pipeline.py`.

---

## 1. Feature Architecture and Pipeline Flow

The Phase 4 Feature Engineering pipeline transforms Phase 2 canonical observations and Station Master metadata into deterministic, point-in-time feature tables.

```text
Phase 2 Canonical Observations (processed/observations/v1/<dataset_version>/)
  │
  ├─> Rainfall Feature Extractor (src/floodguard/features/rainfall.py)
  │     - Trailing rolling windows: (t - 15m, t], (t - 30m, t], (t - 60m, t], (t - 120m, t], (t - 180m, t]
  │     - Exact lags: t, t-5m, t-10m, t-15m, t-30m, t-60m
  │     - Antecedent windows: 6h, 12h, 24h
  │     - Time elapsed since latest wet interval
  │
  ├─> Water-Level Feature Extractor (src/floodguard/features/water_level.py)
  │     - Current level: WL(t)
  │     - Backward deltas & rise-rates: 5m, 15m, 30m, 60m, 120m
  │     - Window summaries: min, max, mean, range, trend (RISING/FALLING/STABLE)
  │     - Distance to reference thresholds (CURRENT_THRESHOLD_REFERENCE_ONLY)
  │
  ├─> Temporal & Cyclical Coordinates (src/floodguard/features/temporal.py)
  │     - Local hour, minute, day of week, month, weekend indicator
  │     - Exact cyclical encodings: sin/cos hour, sin/cos month, sin/cos day of week
  │
  ├─> Spatial & Basin Metadata (src/floodguard/features/spatial.py)
  │     - WGS84 lat/lon, district, main hydrological basin, sensor modality
  │
  ├─> Weather Forecast Features (src/floodguard/features/weather.py)
  │     - Point-in-time daily min/max temp, temp range, rain/thunderstorm indicators
  │
  └─> Multi-Sensor Site Pairing (src/floodguard/features/paired.py)
        - Combined feature vectors for the 13 confirmed shared monitoring sites
```

---

## 2. Temporal Safety and Leakage Guarantees

1. **Strict Point-in-Time Boundary**: For any prediction origin $t$, feature calculations consume exclusively observations with timestamp $t' \le t$. Future observations ($t' \ge t + 5\text{ min}$) and future labels ($t + 30\text{m}, t + 60\text{m}, t + 120\text{m}$) are strictly inaccessible.
2. **Left-Open, Right-Closed Windows**: All rolling lookbacks operate on $(t - W, t]$. The observation at $t$ is included; the observation at $t - W$ is excluded; observations beyond $t$ are excluded.
3. **Conservative Missingness Handling**: Missing sensor slots are **never** imputed as zero. Slot coverage ratio ($N_{\text{usable}} / N_{\text{expected}}$) is tracked for every window. If coverage falls below `min_coverage_ratio` (default 0.8 / 80%), aggregate features evaluate to `None`.
4. **Zero vs. Missing Distinction**: Observed zero rainfall ($0.0\text{ mm}$) contributes $0.0$ to sums and registers as a valid non-missing measurement, distinguishing clear dry weather from sensor outages.
5. **Station-Specific Water Levels**: Gauge datums differ across rivers; absolute water levels are never averaged across stations.
6. **Reference Threshold Provenance**: Distances to Waspada, Amaran, and Bahaya thresholds are tagged `CURRENT_THRESHOLD_REFERENCE_ONLY` because thresholds are unversioned operational proxies from current portals.

---

## 3. Comprehensive Feature Dictionary

### 3.1 Rainfall Rolling Features (`RAINFALL_ROLLING`)

| Feature Name | Lookback $W$ | Unit | Formula / Definition | Min Coverage | Null Semantics | Leakage Classification |
|---|---|---|---|---|---|---|
| `rf_roll_15m_sum_mm` | 15 min | mm | $\sum v_i$ in $(t - 15\text{m}, t]$ | 80% (3 slots) | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_15m_max_mm` | 15 min | mm | $\max v_i$ in $(t - 15\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_15m_wet_count` | 15 min | count | Count of $v_i > 0\text{ mm}$ in window | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_15m_coverage_ratio` | 15 min | ratio | $N_{\text{usable}} / N_{\text{expected}}$ in $[0.0, 1.0]$ | 0% | Always present | `STRICT_POINT_IN_TIME` |
| `rf_roll_15m_is_wet` | 15 min | binary | $\mathbb{I}[\sum v_i > 0]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_30m_sum_mm` | 30 min | mm | $\sum v_i$ in $(t - 30\text{m}, t]$ | 80% (6 slots) | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_30m_max_mm` | 30 min | mm | $\max v_i$ in $(t - 30\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_30m_wet_count` | 30 min | count | Count of $v_i > 0\text{ mm}$ in window | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_30m_coverage_ratio` | 30 min | ratio | $N_{\text{usable}} / N_{\text{expected}}$ in $[0.0, 1.0]$ | 0% | Always present | `STRICT_POINT_IN_TIME` |
| `rf_roll_30m_is_wet` | 30 min | binary | $\mathbb{I}[\sum v_i > 0]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_60m_sum_mm` | 60 min | mm | $\sum v_i$ in $(t - 60\text{m}, t]$ | 80% (12 slots) | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_60m_max_mm` | 60 min | mm | $\max v_i$ in $(t - 60\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_60m_wet_count` | 60 min | count | Count of $v_i > 0\text{ mm}$ in window | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_60m_coverage_ratio` | 60 min | ratio | $N_{\text{usable}} / N_{\text{expected}}$ in $[0.0, 1.0]$ | 0% | Always present | `STRICT_POINT_IN_TIME` |
| `rf_roll_60m_is_wet` | 60 min | binary | $\mathbb{I}[\sum v_i > 0]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_120m_sum_mm` | 120 min | mm | $\sum v_i$ in $(t - 120\text{m}, t]$ | 80% (24 slots) | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_120m_max_mm` | 120 min | mm | $\max v_i$ in $(t - 120\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_120m_wet_count` | 120 min | count | Count of $v_i > 0\text{ mm}$ in window | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_120m_coverage_ratio` | 120 min | ratio | $N_{\text{usable}} / N_{\text{expected}}$ in $[0.0, 1.0]$ | 0% | Always present | `STRICT_POINT_IN_TIME` |
| `rf_roll_120m_is_wet` | 120 min | binary | $\mathbb{I}[\sum v_i > 0]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_180m_sum_mm` | 180 min | mm | $\sum v_i$ in $(t - 180\text{m}, t]$ | 80% (36 slots) | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_180m_max_mm` | 180 min | mm | $\max v_i$ in $(t - 180\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_180m_wet_count` | 180 min | count | Count of $v_i > 0\text{ mm}$ in window | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_roll_180m_coverage_ratio` | 180 min | ratio | $N_{\text{usable}} / N_{\text{expected}}$ in $[0.0, 1.0]$ | 0% | Always present | `STRICT_POINT_IN_TIME` |
| `rf_roll_180m_is_wet` | 180 min | binary | $\mathbb{I}[\sum v_i > 0]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_minutes_since_last_wet` | 0 min | min | $(t - t_{\text{last\_wet}})$ in min | 0% | Null if no wet interval prior | `STRICT_POINT_IN_TIME` |

### 3.2 Antecedent Rainfall Features (`ANTECEDENT_RAINFALL`)

| Feature Name | Lookback $W$ | Unit | Formula / Definition | Min Coverage | Null Semantics | Leakage Classification |
|---|---|---|---|---|---|---|
| `rf_lag_0m_mm` | 0 min | mm | Interval rainfall at instant $t$ | 100% | Null if $t$ is missing | `STRICT_POINT_IN_TIME` |
| `rf_lag_5m_mm` | 5 min | mm | Interval rainfall at instant $t - 5\text{m}$ | 100% | Null if $t-5\text{m}$ missing | `STRICT_POINT_IN_TIME` |
| `rf_lag_10m_mm` | 10 min | mm | Interval rainfall at instant $t - 10\text{m}$ | 100% | Null if $t-10\text{m}$ missing | `STRICT_POINT_IN_TIME` |
| `rf_lag_15m_mm` | 15 min | mm | Interval rainfall at instant $t - 15\text{m}$ | 100% | Null if $t-15\text{m}$ missing | `STRICT_POINT_IN_TIME` |
| `rf_lag_30m_mm` | 30 min | mm | Interval rainfall at instant $t - 30\text{m}$ | 100% | Null if $t-30\text{m}$ missing | `STRICT_POINT_IN_TIME` |
| `rf_lag_60m_mm` | 60 min | mm | Interval rainfall at instant $t - 60\text{m}$ | 100% | Null if $t-60\text{m}$ missing | `STRICT_POINT_IN_TIME` |
| `rf_antecedent_6h_sum_mm` | 360 min | mm | $\sum v_i$ in $(t - 6\text{h}, t]$ | 80% (72 slots) | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_antecedent_6h_coverage_ratio` | 360 min | ratio | $N_{\text{usable}} / 72$ | 0% | Always present | `STRICT_POINT_IN_TIME` |
| `rf_antecedent_6h_wet_count` | 360 min | count | Wet intervals in trailing 6h | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_antecedent_12h_sum_mm` | 720 min | mm | $\sum v_i$ in $(t - 12\text{h}, t]$ | 80% (144 slots) | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_antecedent_12h_coverage_ratio` | 720 min | ratio | $N_{\text{usable}} / 144$ | 0% | Always present | `STRICT_POINT_IN_TIME` |
| `rf_antecedent_12h_wet_count` | 720 min | count | Wet intervals in trailing 12h | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_antecedent_24h_sum_mm` | 1440 min | mm | $\sum v_i$ in $(t - 24\text{h}, t]$ | 80% (288 slots) | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `rf_antecedent_24h_coverage_ratio` | 1440 min | ratio | $N_{\text{usable}} / 288$ | 0% | Always present | `STRICT_POINT_IN_TIME` |
| `rf_antecedent_24h_wet_count` | 1440 min | count | Wet intervals in trailing 24h | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |

### 3.3 Water-Level Deltas & Rise-Rates (`WATER_LEVEL_DELTA`, `WATER_LEVEL_RATE`, `WATER_LEVEL_WINDOW`)

| Feature Name | Lookback $W$ | Unit | Formula / Definition | Min Coverage | Null Semantics | Leakage Classification |
|---|---|---|---|---|---|---|
| `wl_level_m` | 0 min | m | $WL(t)$ | 100% | Null if $t$ missing | `STRICT_POINT_IN_TIME` |
| `wl_delta_5m_m` | 5 min | m | $WL(t) - WL(t - 5\text{m})$ | 100% | Null if gap/missing | `STRICT_POINT_IN_TIME` |
| `wl_rate_5m_m_per_h` | 5 min | m/h | $(WL(t) - WL(t - 5\text{m})) / (5/60)$ | 100% | Null if gap/missing | `STRICT_POINT_IN_TIME` |
| `wl_delta_15m_m` | 15 min | m | $WL(t) - WL(t - 15\text{m})$ | 100% | Null if gap/missing | `STRICT_POINT_IN_TIME` |
| `wl_rate_15m_m_per_h` | 15 min | m/h | $(WL(t) - WL(t - 15\text{m})) / (15/60)$ | 100% | Null if gap/missing | `STRICT_POINT_IN_TIME` |
| `wl_delta_30m_m` | 30 min | m | $WL(t) - WL(t - 30\text{m})$ | 100% | Null if gap/missing | `STRICT_POINT_IN_TIME` |
| `wl_rate_30m_m_per_h` | 30 min | m/h | $(WL(t) - WL(t - 30\text{m})) / (30/60)$ | 100% | Null if gap/missing | `STRICT_POINT_IN_TIME` |
| `wl_delta_60m_m` | 60 min | m | $WL(t) - WL(t - 60\text{m})$ | 100% | Null if gap/missing | `STRICT_POINT_IN_TIME` |
| `wl_rate_60m_m_per_h` | 60 min | m/h | $(WL(t) - WL(t - 60\text{m})) / (60/60)$ | 100% | Null if gap/missing | `STRICT_POINT_IN_TIME` |
| `wl_delta_120m_m` | 120 min | m | $WL(t) - WL(t - 120\text{m})$ | 100% | Null if gap/missing | `STRICT_POINT_IN_TIME` |
| `wl_rate_120m_m_per_h` | 120 min | m/h | $(WL(t) - WL(t - 120\text{m})) / (120/60)$ | 100% | Null if gap/missing | `STRICT_POINT_IN_TIME` |
| `wl_min_15m_m` | 15 min | m | $\min WL$ in $(t - 15\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_max_15m_m` | 15 min | m | $\max WL$ in $(t - 15\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_mean_15m_m` | 15 min | m | $\text{mean}(WL)$ in $(t - 15\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_range_15m_m` | 15 min | m | $\max(WL) - \min(WL)$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_trend_15m` | 15 min | text | `RISING`, `FALLING`, or `STABLE` | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_coverage_15m_ratio` | 15 min | ratio | $N_{\text{usable}} / 3$ | 0% | Always present | `STRICT_POINT_IN_TIME` |
| `wl_min_30m_m` | 30 min | m | $\min WL$ in $(t - 30\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_max_30m_m` | 30 min | m | $\max WL$ in $(t - 30\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_mean_30m_m` | 30 min | m | $\text{mean}(WL)$ in $(t - 30\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_range_30m_m` | 30 min | m | $\max(WL) - \min(WL)$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_trend_30m` | 30 min | text | `RISING`, `FALLING`, or `STABLE` | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_coverage_30m_ratio` | 30 min | ratio | $N_{\text{usable}} / 6$ | 0% | Always present | `STRICT_POINT_IN_TIME` |
| `wl_min_60m_m` | 60 min | m | $\min WL$ in $(t - 60\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_max_60m_m` | 60 min | m | $\max WL$ in $(t - 60\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_mean_60m_m` | 60 min | m | $\text{mean}(WL)$ in $(t - 60\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_range_60m_m` | 60 min | m | $\max(WL) - \min(WL)$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_trend_60m` | 60 min | text | `RISING`, `FALLING`, or `STABLE` | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_coverage_60m_ratio` | 60 min | ratio | $N_{\text{usable}} / 12$ | 0% | Always present | `STRICT_POINT_IN_TIME` |
| `wl_min_120m_m` | 120 min | m | $\min WL$ in $(t - 120\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_max_120m_m` | 120 min | m | $\max WL$ in $(t - 120\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_mean_120m_m` | 120 min | m | $\text{mean}(WL)$ in $(t - 120\text{m}, t]$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_range_120m_m` | 120 min | m | $\max(WL) - \min(WL)$ | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_trend_120m` | 120 min | text | `RISING`, `FALLING`, or `STABLE` | 80% | Null if coverage < 80% | `STRICT_POINT_IN_TIME` |
| `wl_coverage_120m_ratio` | 120 min | ratio | $N_{\text{usable}} / 24$ | 0% | Always present | `STRICT_POINT_IN_TIME` |

### 3.4 Threshold Distance Reference (`THRESHOLD_REFERENCE`)

| Feature Name | Lookback $W$ | Unit | Formula / Definition | Min Coverage | Null Semantics | Leakage Classification |
|---|---|---|---|---|---|---|
| `wl_dist_to_waspada_m` | 0 min | m | $WL(t) - \theta_{\text{Waspada}}$ | 100% | Null if no threshold | `CURRENT_THRESHOLD_REFERENCE_ONLY` |
| `wl_dist_to_amaran_m` | 0 min | m | $WL(t) - \theta_{\text{Amaran}}$ | 100% | Null if no threshold | `CURRENT_THRESHOLD_REFERENCE_ONLY` |
| `wl_dist_to_bahaya_m` | 0 min | m | $WL(t) - \theta_{\text{Bahaya}}$ | 100% | Null if no threshold | `CURRENT_THRESHOLD_REFERENCE_ONLY` |

### 3.5 Temporal Features (`TEMPORAL`)

| Feature Name | Lookback $W$ | Unit | Formula / Range | Null Semantics | Leakage Classification |
|---|---|---|---|---|---|
| `time_hour` | 0 min | unitless | Integer $0 \le \text{hour} \le 23$ | Always present | `STRICT_POINT_IN_TIME` |
| `time_minute` | 0 min | unitless | Integer $0 \le \text{minute} \le 55$ | Always present | `STRICT_POINT_IN_TIME` |
| `time_day_of_week` | 0 min | unitless | Integer $0 \le \text{dow} \le 6$ (Mon=0) | Always present | `STRICT_POINT_IN_TIME` |
| `time_month` | 0 min | unitless | Integer $1 \le \text{month} \le 12$ | Always present | `STRICT_POINT_IN_TIME` |
| `time_hour_sin` | 0 min | unitless | $\sin(2\pi \cdot \text{hour} / 24.0) \in [-1.0, 1.0]$ | Always present | `STRICT_POINT_IN_TIME` |
| `time_hour_cos` | 0 min | unitless | $\cos(2\pi \cdot \text{hour} / 24.0) \in [-1.0, 1.0]$ | Always present | `STRICT_POINT_IN_TIME` |
| `time_month_sin` | 0 min | unitless | $\sin(2\pi \cdot (\text{month}-1) / 12.0) \in [-1.0, 1.0]$ | Always present | `STRICT_POINT_IN_TIME` |
| `time_month_cos` | 0 min | unitless | $\cos(2\pi \cdot (\text{month}-1) / 12.0) \in [-1.0, 1.0]$ | Always present | `STRICT_POINT_IN_TIME` |
| `time_day_of_week_sin` | 0 min | unitless | $\sin(2\pi \cdot \text{dow} / 7.0) \in [-1.0, 1.0]$ | Always present | `STRICT_POINT_IN_TIME` |
| `time_day_of_week_cos` | 0 min | unitless | $\cos(2\pi \cdot \text{dow} / 7.0) \in [-1.0, 1.0]$ | Always present | `STRICT_POINT_IN_TIME` |
| `time_is_weekend` | 0 min | unitless | Binary $\mathbb{I}[\text{dow} \in \{5, 6\}]$ | Always present | `STRICT_POINT_IN_TIME` |

### 3.6 Station & Basin Spatial Features (`STATION_BASIN`)

| Feature Name | Lookback $W$ | Unit | Definition | Null Semantics | Leakage Classification |
|---|---|---|---|---|---|
| `station_latitude` | 0 min | deg | WGS84 decimal degrees | Null if missing in master | `STATIC_PROVENANCE_ASSUMED` |
| `station_longitude` | 0 min | deg | WGS84 decimal degrees | Null if missing in master | `STATIC_PROVENANCE_ASSUMED` |
| `station_district` | 0 min | text | Penang district name | Null if missing in master | `STATIC_PROVENANCE_ASSUMED` |
| `station_main_basin` | 0 min | text | Hydrological river basin name | Null if missing in master | `STATIC_PROVENANCE_ASSUMED` |
| `station_sensor_type` | 0 min | text | `RAINFALL` or `WATER_LEVEL` | Always present | `STATIC_PROVENANCE_ASSUMED` |

### 3.7 Weather Forecast Features (`WEATHER_FORECAST`)

| Feature Name | Lookback $W$ | Unit | Definition | Null Semantics | Leakage Classification |
|---|---|---|---|---|---|
| `fc_temp_min_c` | 0 min | °C | Point-in-time daily minimum temperature | Null if forecast unavailable at $t$ | `STRICT_POINT_IN_TIME` |
| `fc_temp_max_c` | 0 min | °C | Point-in-time daily maximum temperature | Null if forecast unavailable at $t$ | `STRICT_POINT_IN_TIME` |
| `fc_temp_range_c` | 0 min | °C | Diurnal range ($T_{\max} - T_{\min}$) | Null if forecast unavailable at $t$ | `STRICT_POINT_IN_TIME` |
| `fc_is_rain_forecast` | 0 min | binary | Forecast predicts rain / thunderstorm | Null if forecast unavailable at $t$ | `STRICT_POINT_IN_TIME` |
| `fc_is_thunderstorm_forecast` | 0 min | binary | Forecast predicts thunderstorm | Null if forecast unavailable at $t$ | `STRICT_POINT_IN_TIME` |

### 3.8 Paired Multi-Sensor Site Identifiers (`PAIRED_SITE`)

| Feature Name | Lookback $W$ | Unit | Definition | Null Semantics | Leakage Classification |
|---|---|---|---|---|---|
| `paired_rainfall_sensor_id` | 0 min | text | Canonical sensor ID for co-located rain gauge | Present on paired records | `STATIC_PROVENANCE_ASSUMED` |
| `paired_water_level_sensor_id` | 0 min | text | Canonical sensor ID for co-located WL gauge | Present on paired records | `STATIC_PROVENANCE_ASSUMED` |

---

## 4. Machine-Readable Feature Output & Manifest

Outputs are written under:
```text
data/features/<dataset_version>/v1/
    rainfall_features.jsonl
    water_level_features.jsonl
    paired_site_features.jsonl
    feature_manifest.json
```

The `feature_manifest.json` preserves:
- Exact `dataset_version`, `observations_sha256`, and `station_master_sha256`.
- Configuration dictionary (`min_coverage_ratio`, rolling windows, cadence).
- Per-feature row counts and SHA-256 digests.
- Per-feature column coverage and null statistics.
- Automated invariant check results.

---

## 5. Feasibility and Limitations

- **Coverage Sufficiency**: Local captures contain 289 rainfall intervals and 2 water-level history captures. While algorithmically complete and verified with 100% offline tests, long-term lookbacks ($> 24\text{h}$) and station-wide ML models require extended historical data.
- **Proxy Labels**: Targets constructed against current reference thresholds serve as operational proxy targets, not verified disaster flood inundation ground truth.
