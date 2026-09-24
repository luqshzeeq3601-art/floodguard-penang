# Data Dictionary

This document starts as a specification and should be updated from real source schemas.

## 1. Core Observation Fields

| Field | Type | Unit | Description |
|---|---|---|---|
| source | string | — | Upstream data provider |
| station_id | string | — | Stable canonical station ID |
| observation_time | datetime | Asia/Kuala_Lumpur | Time measurement applies to |
| ingested_at | datetime | UTC or explicit TZ | Time received by FloodGuard |
| measurement_type | enum | — | rainfall, water_level, etc. |
| value | float | source-specific | Raw/cleaned value |
| unit | string | — | mm, m, °C, etc. |
| quality_flag | enum | — | Data-quality status |
| schema_version | string | — | Ingestion schema version |

JPS Public Infobanjir note (verified 2026-09-24): discovery inventories use `jps_internal_id`
(graph-link `stationid`, unique per inventory as observed) and `jps_display_station_id` ("ID Stesen";
duplicates, blanks, "No Data" occur); neither is the canonical `station_id`, which the station master
task decides. FloodGuard-derived columns are prefixed `fg_`. Source times carry no declared timezone.
JPS history uses `-9999` as its missing sentinel (never convert to 0). Rainfall `raw` is the 5-min
increment in mm; rainfall `clean` depends on the request's `datafreq`. Water level and thresholds are
in metres. See `data/metadata/jps/README.md` and `data/metadata/jps/HISTORICAL_AVAILABILITY.md`.
Live probes keep `observation_time` (source time) and `retrieved_at` (FloodGuard clock, +08:00)
separate. `fg_age_minutes` = `retrieved_at − observation_time`, and `fg_live_status` ∈
{FRESH, DELAYED, STALE, NO_DATA, INVALID}; rules are in `data/metadata/jps/LIVE_ACCESS.md`.

GIS note (verified 2026-09-24): `data/metadata/gis/penang_station_coordinates_jps.csv` keeps
`latitude`/`longitude` as the JPS feed's verbatim decimal-degree strings (4–6 decimals). The CRS is
not declared by the source; WGS84 is inferred. Penang GeoHub flood layers use a custom GDM2000
Cassini WKT with no EPSG code. Their `tarikh` dates are epoch-ms values at 00:00 UTC, i.e.
calendar dates with no time of day. See `data/metadata/gis/GIS_FLOOD_DATASETS.md`.

## 2. Rainfall Features

| Feature | Unit | Definition |
|---|---:|---|
| rainfall_15m | mm | Rain accumulated over trailing 15 minutes |
| rainfall_1h | mm | Trailing 1-hour accumulation |
| rainfall_3h | mm | Trailing 3-hour accumulation |
| rainfall_6h | mm | Trailing 6-hour accumulation |
| rainfall_24h | mm | Trailing 24-hour accumulation |
| antecedent_rainfall_3d | mm | Trailing 72-hour accumulation |
| rainfall_intensity | mm/h | Recent intensity estimate |

All rolling windows must be strictly backward-looking.

## 3. Water-Level Features

| Feature | Unit | Definition |
|---|---:|---|
| water_level | m | Most recent valid water level |
| water_level_delta_15m | m | Current minus level 15 min earlier |
| water_level_delta_30m | m | Current minus level 30 min earlier |
| water_level_delta_1h | m | Current minus level 1h earlier |
| water_level_rise_rate | m/h | Estimated recent rate of rise |
| distance_to_alert | m | Alert threshold minus current level |
| distance_to_warning | m | Warning threshold minus current level |
| distance_to_danger | m | Danger threshold minus current level |

Threshold-distance features may only be used if the threshold is known at inference time.

## 4. Weather Features

Possible fields:

- forecast_rainfall_1h;
- forecast_rainfall_3h;
- temperature;
- humidity;
- weather_condition;
- warning_active.

Only retain features with sufficiently reliable source availability.

METMalaysia note (verified 2026-09-24, `data/metadata/metmalaysia/ACCESS.md`): the data.gov.my
forecast gives, per `location_id` (e.g. `St003`, `Ds012`) and calendar `date`, categorical Malay
text for `morning_forecast`/`afternoon_forecast`/`night_forecast`/`summary_forecast`, a
`summary_when` phrase, and integer `min_temp`/`max_temp` in °C. It gives **no mm rainfall**, so
`forecast_rainfall_1h`/`_3h` have no verified source. It also has no issue time, so the availability
time of a forecast is FloodGuard's first-seen `retrieved_at`. Warnings carry naive local
`issued`/`valid_from`/`valid_to` and free-text areas, and are not FloodGuard labels.

data.gov.my historical note (verified 2026-09-24, `data/metadata/data_gov_my/HISTORICAL_WEATHER.md`):
no historical `temperature` or `humidity` source overlaps the JPS training period. The only
historical series (Weather and Climate dashboard, daily 2021–2022, frozen) is not a feature source.

## 5. Temporal Features

Possible fields:

- hour;
- day_of_week;
- month;
- season/monsoon indicator.

Avoid encoding seasonal labels without documenting the rule/source.

## 6. Targets

### Classification

`target_30m`

Whether the defined risk/threshold event occurs within the next 30 minutes.

`target_60m`

Same for 60 minutes.

`target_120m`

Same for 120 minutes.

The precise target definition must be frozen and versioned before model comparison.

### Regression

Examples:

- `water_level_t_plus_30m`;
- `water_level_t_plus_60m`;
- `water_level_t_plus_120m`.

## 7. Target Leakage Checklist

Before accepting a feature, ask:

1. Was this information available at prediction time?
2. Does the feature indirectly contain the future target?
3. Did a rolling operation center the window?
4. Was interpolation performed using future values?
5. Was normalization fit on the full dataset?
6. Was the future forecast timestamp aligned correctly?
