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
duplicates, blanks, "No Data" occur); neither is canonical. The station master (section 1a) replaces
`station_id` with `fg_sensor_id` (observations) and `fg_site_id` (locations). FloodGuard-derived columns are prefixed `fg_`. Source times carry no declared timezone.
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

## 1a. Station Master (conceptual)

Design, key rules, merge criteria and flags: `docs/STATION_MASTER_DESIGN.md`. Built locally by
`scripts/build_station_master.py` into git-ignored `data/local/station_master/` (JPS data is
PERMISSION REQUIRED). Schema version `station_master/v1`. Timestamps are timezone-aware, +08:00.

Site (one monitoring location; 1..n sensors):

| Field | Type | Description |
|---|---|---|
| fg_site_id | uuid | UUIDv5 of `site/v1\|source\|fg_source_site_key` (review sites add `\|review\|sensor_type`) |
| fg_source_site_key | string | `jps_internal_id` with outer whitespace stripped; key derivation only |
| source | enum | `JPS_PUBLIC_INFOBANJIR` |
| jps_internal_id | string | Raw source ID, verbatim (may contain whitespace) |
| fg_site_name | string | Derived display name (feed name, whitespace collapsed); not an identifier |
| jps_map_feed_name | string | Map-feed station name, verbatim |
| state, district | string | Listing values, checked against the map feed |
| latitude, longitude | string (decimal °) | Map-feed values, verbatim; blank if missing, collided or under review |
| coordinate_source | string | Map-feed URL |
| fg_crs_assumption | string | `EPSG:4326 (inferred)`; the source declares no CRS |
| main_basin, sub_basin | string | Map feed (WL listing as fallback) |
| fg_first_seen_at, fg_last_verified_at | datetime | Earliest / latest capture of the site's evidence |
| fg_quality_flags | list | Pipe-separated flags (design doc section 7) |

Sensor (one measurement type at one site; at most one per type per site):

| Field | Type | Description |
|---|---|---|
| fg_sensor_id | uuid | UUIDv5 of `sensor/v1\|source\|fg_source_site_key\|sensor_type` |
| fg_site_id | uuid | Owning site (exactly one) |
| sensor_type | enum | `RAINFALL`, `WATER_LEVEL` |
| jps_internal_id, jps_display_station_id, jps_sensor_name | string | Listing row, verbatim |
| measurement_type / unit | enum / string | `rainfall` / `mm`, `water_level` / `m` |
| fg_expected_listing_interval_minutes | int, nullable | 15 for "(F2)" stations (LIVE_ACCESS.md); blank where unverified |
| source_url | string | Listing endpoint |
| fg_first_seen_at, fg_last_verified_at | datetime | Listing capture time |
| fg_quality_flags | list | `MISSING_DISPLAY_ID`, `DUPLICATE_DISPLAY_ID` |

Threshold (WATER_LEVEL sensors only; versioned by capture):

| Field | Type | Description |
|---|---|---|
| fg_threshold_id | uuid | UUIDv5 of `threshold/v1\|fg_sensor_id\|threshold_source\|threshold_type\|captured_at` |
| fg_sensor_id | uuid | Must be a `WATER_LEVEL` sensor |
| threshold_type | enum | `NORMAL`, `WASPADA`, `AMARAN`, `BAHAYA` (JPS terms) |
| value / value_raw | decimal / string | m; published text kept |
| threshold_source | enum | `JPS_NATIONAL_LISTING`, `JPS_PENANG_PORTAL` |
| captured_at, source_verified_at | datetime | Capture of that source |
| valid_from | datetime, nullable | Blank: JPS publishes no validity period; history returns current thresholds |
| provenance | string | Source file/column or doc table |
| fg_label_eligible | bool | `false` for `NORMAL` (0.00 on 14/22 stations; reference offset, not a flood stage) |
| fg_quality_flags | list | `THRESHOLD_PROVENANCE_CONFLICT` |

Canonical observation identity: `(source, fg_sensor_id, observation_time)` (section 1d). Before
canonical mapping, the upstream dedup key is `(jps_internal_id, measurement_type, observation_time)`.

## 1b. Raw Records (`raw_record/v1`)

One JSON Lines object per source row in `data/raw/**/<sha256>.records.jsonl` (accepted) or
`.quarantine.jsonl`. Nothing is cleaned or converted. Design: `docs/RAW_INGESTION_DESIGN.md`.

| Field | Type | Description |
|---|---|---|
| record_schema_version | string | `raw_record/v1` |
| source | string | `JPS_PUBLIC_INFOBANJIR`, `DATA_GOV_MY_WEATHER_API` |
| dataset | string | `rainfall_listing`, `water_level_listing`, `rainfall_history`, `water_level_history`, `weather_forecast` |
| source_reference | string | Request URL or file reference, as supplied |
| source_licence / source_attribution | string / null | Licence status; attribution text where the licence requires it (CC BY 4.0) |
| retrieved_at | datetime (UTC) | Capture time, tz-aware |
| payload_sha256 | string | SHA-256 of the payload bytes |
| ingestion_batch_id | string | Deterministic UUIDv5 of the batch |
| parser_name / parser_version | string | Adapter that produced the record |
| source_row_index / source_line | int / int or null | 0-based data-row position; 1-based payload line (HTML) |
| source_station_id | string or null | JPS `jps_internal_id` exactly as published (whitespace kept); forecast `location_id` |
| source_display_station_id | string or null | JPS listing "ID Stesen" as published; null where the payload has none |
| source_station_name | string or null | Name as published |
| sensor_type | enum or null | `RAINFALL`, `WATER_LEVEL` (station master); null for forecasts |
| measurement_type | string | `rainfall`, `water_level`, `weather_forecast` |
| source_time_raw / source_time_field | string | Time text as received and the column/key it came from |
| observation_time_naive | string or null | Same time parsed, ISO without offset; no UTC conversion |
| timezone_interpretation | string | `UNVERIFIED_ASSUMED_MYT` |
| value_field / value_raw | string / string or null | Primary field name and its text as received (`-9999`, `ERROR`, blank, `Tiada Data`, `0` kept) |
| unit / unit_basis | string or null / enum | `mm`, `m`; `SOURCE_HEADER`, `SOURCE_DOCUMENTATION`, `NONE` |
| source_fields_raw | object | Every cell/key of the row, text as received |
| threshold_values_raw / threshold_temporal_scope | object or null / enum or null | Published thresholds as source metadata; `CURRENT_AT_RETRIEVAL` or `CURRENT_NOT_HISTORICAL` |
| source_metadata_raw | object | Payload-level metadata (JPS history `info`) |
| fg_sensor_id | string or null | From the station master at ingest time; never invented. Provisional: re-resolved by the station-ID layer (1d) |
| mapping_status | enum | `MAPPED`, `UNMAPPED`, `NOT_APPLICABLE` |
| quarantine_reason / quarantine_detail | enum or null / string or null | `UNMAPPED_SENSOR`, `INVALID_SOURCE_ID`, `MISSING_TIMESTAMP`, `UNPARSEABLE_TIMESTAMP`, `INVALID_ROW_STRUCTURE` |

## 1c. Normalised Timestamps (`timestamp_normalization/v1`)

Derived by `scripts/normalize_timestamps.py` into
`data/interim/timestamps/v1/.../<sha256>.timestamps.jsonl`, one line per accepted raw record; raw
files are never changed. Policy and flags: `docs/TIMESTAMP_POLICY.md`.

| Field | Type | Description |
|---|---|---|
| timestamp_schema_version | string | `timestamp_normalization/v1` |
| ingestion_batch_id / payload_sha256 / source_row_index | string / string / int | Join keys back to the raw record |
| source / dataset / source_station_id / fg_sensor_id / source_time_field | string | Copied from the raw record |
| retrieved_at | datetime (UTC) | Capture time; only the FUTURE reference, never an observation time |
| future_skew_seconds | int | FUTURE tolerance (600) |
| observation_time_raw | string or null | Source time text exactly as in the raw record |
| observation_time_local | string or null | ISO 8601 with offset; null for MISSING, INVALID_FORMAT, AMBIGUOUS, UNSPECIFIED_TIMEZONE, DATE precision |
| observation_time_utc | string or null | ISO 8601 `+00:00`; null under the same conditions |
| observation_date_local | string or null | `YYYY-MM-DD` calendar label for DATE precision only |
| precision | enum or null | `DATE`, `MINUTE`, `SECOND` |
| timezone_name | string or null | IANA zone applied (`Asia/Kuala_Lumpur`) or the explicit zone label (`UTC`, `UTC+05:30`) |
| timezone_status | enum or null | `EXPLICIT_IN_SOURCE`, `UNSPECIFIED_ASSUMED`, `UNSPECIFIED_NO_POLICY` |
| timestamp_quality_flag | enum | `VALID`, `MISSING`, `INVALID_FORMAT`, `AMBIGUOUS`, `FUTURE`, `UNSPECIFIED_TIMEZONE` |

## 1d. Normalised Station IDs (`station_id_normalization/v1`)

Derived by `scripts/normalize_station_ids.py` into
`data/interim/station_ids/v1/.../<sha256>[.quarantine].station_ids.jsonl`, one line per raw record
(accepted or quarantined); raw files are never changed. Policy and statuses:
`docs/STATION_MASTER_DESIGN.md` section 12.

| Field | Type | Description |
|---|---|---|
| station_id_schema_version | string | `station_id_normalization/v1` |
| ingestion_batch_id / payload_sha256 / source_row_index | string / string / int | Join keys back to the raw record |
| source / dataset / measurement_type | string | Copied from the raw record |
| station_master_origin | string | Station-master file name + SHA-256 prefix used for this row |
| raw_fg_sensor_id / raw_mapping_status | string or null / enum | Ingest-time values, for comparison only |
| jps_internal_id_raw | string or null | Source internal ID exactly as in the raw record (whitespace kept) |
| jps_display_station_id_raw | string or null | Display ID exactly as in the raw record; never used for mapping |
| lookup_key | string or null | Internal ID with outer whitespace stripped; null when unusable |
| sensor_type | string or null | As supplied by the adapter |
| fg_site_id / fg_sensor_id | uuid or null | From the station master; both set only when `MAPPED` |
| station_id_mapping_status | enum | `MAPPED`, `UNMAPPED`, `SENSOR_TYPE_MISMATCH`, `INVALID_SOURCE_ID`, `INVALID_SENSOR_TYPE` |
| mapping_reason | string or null | Why a row is not mapped; null when `MAPPED` |

## 1e. Unit Validation (`unit_validation/v1`)

Derived by `scripts/validate_units.py` into
`data/interim/units/v1/.../<sha256>[.quarantine].units.jsonl`, one line per validated field of a
raw record (primary value, thresholds, other fields the policy names); raw files are never changed.
Policy, evidence and statuses: `docs/UNIT_POLICY.md`.

| Field | Type | Description |
|---|---|---|
| unit_schema_version / unit_policy_version | string | `unit_validation/v1` / `unit_policy/v1` |
| ingestion_batch_id / payload_sha256 / source_row_index | string / string / int | Join keys back to the raw record |
| source / dataset / source_station_id / sensor_type / source_time_raw | string | Copied exactly from the raw record |
| source_field / field_role | string / enum | Source key or label; `PRIMARY_VALUE`, `THRESHOLD`, `SOURCE_FIELD` |
| value_raw | string or null | Value text exactly as in the raw record |
| value_parse_status | enum | `NUMERIC`, `SOURCE_MARKER` (`-9999`, `ERROR`, `Tiada Data`), `EMPTY`, `NON_NUMERIC` |
| parsed_value | float or null | Set only when the unit is `VALID` and the value `NUMERIC`; zero stays `0.0` |
| source_unit_raw / raw_record_unit | string or null | Unit printed in the payload label; unit in the raw record (primary value only) |
| measurement_type | enum or null | `RAINFALL_INTERVAL`, `RAINFALL_1H_TOTAL`, `WATER_LEVEL`, `WATER_LEVEL_THRESHOLD`, `FORECAST_TEMPERATURE_MIN`, `FORECAST_TEMPERATURE_MAX`; null when not promoted |
| canonical_unit | string or null | `mm`, `m`, `°C`; no conversion is applied |
| unit_provenance | enum or null | `IN_PAYLOAD`, `OFFICIAL_UI_OR_DOCS` (`INFERRED` is never promoted) |
| semantics_status | enum | `VERIFIED`, `UNVERIFIED` |
| threshold_category / threshold_temporal_scope | enum or null | `NORMAL`, `WASPADA`, `AMARAN`, `BAHAYA` / `CURRENT_AT_RETRIEVAL`, `CURRENT_NOT_HISTORICAL` (threshold rows only) |
| unit_validation_status | enum | `VALID`, `MISSING_UNIT`, `UNKNOWN_UNIT`, `UNIT_MISMATCH`, `SENSOR_TYPE_MISMATCH`, `UNKNOWN_MEASUREMENT_SEMANTICS` |
| reason | string or null | Why a row is not `VALID` |

## 1f. Quality Flags (`quality_flags/v1`)

Written by `scripts/build_historical_dataset.py` into
`data/interim/quality/v1/.../<sha256>[.quarantine].quality.jsonl`: one line per raw record
(accepted or quarantined) for its primary value, plus one per other promoted field. Flags and
rules: `docs/QUALITY_FLAGS.md`.

| Field | Type | Description |
|---|---|---|
| quality_schema_version | string | `quality_flags/v1` |
| ingestion_batch_id / payload_sha256 / source_row_index / source_field | string / string / int / string | Join keys back to the raw record and component rows |
| source / dataset / retrieved_at / source_station_id / sensor_type | string | Copied from the raw record |
| raw_file | enum | `records`, `quarantine` |
| fg_site_id / fg_sensor_id | uuid or null | From the station-ID layer; null without a station master |
| observation_time_raw | string or null | Source time text as received |
| observation_time_local / observation_time_utc / observation_date_local / timezone_name / timezone_status | string or null | From the timestamp layer; null for quarantined rows |
| field_role / measurement_type / canonical_unit / value_raw / parsed_value | — | From the unit layer |
| raw_quarantine_reason / timestamp_quality_flag / station_id_mapping_status / unit_validation_status / value_parse_status | enum or null | Component statuses, unchanged |
| timestamp_schema_version / station_id_schema_version / station_master_origin / unit_schema_version / unit_policy_version | string or null | Component versions |
| quality_flags | list of enum | Sorted, unique; see `docs/QUALITY_FLAGS.md` |
| usable | bool | Only informational flags and a parsed number |

## 1g. Canonical Observations (`observations/v1`)

Written by `scripts/build_historical_dataset.py` into
`data/processed/observations/v1/<dataset_version>/observations.jsonl`, sorted by source, sensor,
measurement type and time. Key: `source + fg_sensor_id + observation_time_utc + measurement_type`.
Rules: `docs/HISTORICAL_PIPELINE.md`.

| Field | Type | Description |
|---|---|---|
| observation_schema_version | string | `observations/v1` |
| source / fg_site_id / fg_sensor_id / sensor_type | string / uuid / uuid / enum | Canonical identity |
| measurement_type | enum | `RAINFALL_INTERVAL`, `RAINFALL_1H_TOTAL`, `WATER_LEVEL` |
| observation_time_utc / observation_time_local | datetime | Instant (UTC) and its local form (`+08:00`, assumed zone) |
| timezone_name / timezone_status | string / enum | `Asia/Kuala_Lumpur` / `UNSPECIFIED_ASSUMED` |
| value / unit | float or null / string | Parsed number (`mm`, `m`); null for markers, empty, non-numeric and conflicts; zero stays `0.0` |
| value_raw / value_parse_status | string or null / enum or null | Source text and parse status; null on conflict |
| quality_flags / usable | list / bool | Union of member flags plus duplicate flags; usable = value and only informational flags |
| duplicate_status / duplicate_count | enum / int | `UNIQUE`, `IDENTICAL`, `CONFLICT`; source rows collapsed into this row |
| conflict_reason / conflicting_values | enum or null / list | `NUMERIC_VALUES_DIFFER`, `MARKER_VS_NUMERIC`, `MARKERS_DIFFER`; candidate `STATUS:value` strings |
| first_retrieved_at | datetime (UTC) | Earliest capture of this observation |
| datasets / provenance | list / list of objects | Contributing datasets; every source row (`ingestion_batch_id`, `payload_sha256`, `dataset`, `source_row_index`, `source_field`, `retrieved_at`, `value_signature`) |

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
