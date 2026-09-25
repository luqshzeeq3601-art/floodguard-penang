# Data Plan

## 1. Strategy

Use both:

- **historical data** for model development and backtesting;
- **live data** for production/replay inference and monitoring.

A model should not be trained only on incoming live observations.

## 2. Intended Sources

### JPS Public Infobanjir

Primary source for:

- rainfall station observations;
- river/water-level station observations;
- station thresholds/trends where available.

Implementation tasks:

1. identify all Penang stations;
2. verify export/API/access method;
3. verify historical depth;
4. verify observation frequency;
5. document station metadata;
6. verify acceptable automated access.

Prefer official export/API mechanisms over brittle scraping.

**Verified access (2026-09-24, rainfall and water level):** no documented API or server-side export
for station lists; each state page loads an unauthenticated, site-internal HTML fragment
(rainfall: `searchresultrainfall.php`, 56 Pulau Pinang rows; water level: `aras-air-data/`, 22 rows
with basin, latest level and per-station Normal/Waspada/Amaran/Bahaya thresholds). No coordinates,
trend or status field in either listing. The published "ID Stesen" is not a reliable key; rows are
keyed by the graph-link `stationid` (`jps_internal_id`). Details: `data/metadata/jps/README.md`.

**Verified history (2026-09-24):** per-station date-range JSON endpoints serve 5-min data. Sampled
stations are confirmed back to at least 2024-09-01 (one rainfall station to 2024-01-01); earlier
ranges return "No result". That is about 2 years, short of the "years of history" ADR-0004
assumes. Full-coverage and event counts are still unmeasured. data.gov.my does not extend depth
(verified 2026-09-24, see the data.gov.my section).
Details: `data/metadata/jps/HISTORICAL_AVAILABILITY.md`.

**Verified live access (2026-09-24):** poll the two state listings (2 requests per poll) every
5 min. F2 stations update every 15 min with 4–7 min publication lag; others update asynchronously.
There are no cache validators. Proposed observation key:
`source + jps_internal_id + measurement_type + observation_time`. Details:
`data/metadata/jps/LIVE_ACCESS.md`.

### METMalaysia

Potential uses:

- forecast rainfall/weather;
- warnings;
- radar/satellite context;
- weather observations.

**Verified access (2026-09-24):** the only open, structured, unauthenticated METMalaysia feed is
the data.gov.my Weather API (`api.data.gov.my/weather/forecast` and `/warning`: JSON, CC BY 4.0,
4 requests/min). The forecast has 28 Penang location IDs (state, 5 districts, 19 towns,
3 recreation centres), each with 7 daily records of categorical Malay text plus min/max °C. There is
no rainfall amount, **no issue time**, and **no archive** (past date ranges return `[]`). Warnings
carry issue and valid times but use free-text geography and serve only current records.
`api.met.gov.my` needs a registered token (deferred). Radar and satellite are rendered images only.
Forecast and warning features cannot be backfilled for training without leakage and must be
collected forward-only from go-live. Details: `data/metadata/metmalaysia/ACCESS.md`.

### data.gov.my

Potential uses:

- historical weather/climate;
- station observations;
- supporting contextual datasets.

**Verified historical coverage (2026-09-24):** none suitable for v1 training. The catalogue
(292 datasets) has no METMalaysia or JPS dataset and no rainfall, temperature, humidity, pressure,
wind or water-level data. The only historical weather is the unmaintained "Weather and Climate"
dashboard (42 METMalaysia manned stations incl. Bayan Lepas and Butterworth, officially published
lat/lon): **daily** rainfall total and mean temperature 2020-12-31 → 2022-12-31, monthly/yearly
2013–2022, frozen at 2022-12-31, no documented API, undocumented day boundary. It does not overlap
the JPS history (2024+), so it gives no model features; monthly/yearly may serve as EDA climatology
context only. Details: `data/metadata/data_gov_my/HISTORICAL_WEATHER.md`.

### MyGDI / JPS GIS

Potential uses:

- flood-prone areas;
- historical flood polygons;
- river/basin context.

**Verified (2026-09-24):**

- **Station coordinates.** Official lat/lon exist for all 56 rainfall and 22 water-level
  inventory rows (65 unique `jps_internal_id`). They come from the JPS map feed
  `latestreadingstrendabc.json`, joined on `stationid`. The CRS is not declared; WGS84 is
  inferred from the Leaflet usage. See `data/metadata/gis/penang_station_coordinates_jps.csv`.
- **Boundaries and rivers.** JPS publishes Peninsular basin, main-river and district GeoJSON
  (RFC 7946) on the Penang JPS portal. DOSM publishes district GeoJSON (explicit CRS84).
- **Historical floods.** The Penang GeoHub (`pegis.penang.gov.my`) has a public ArcGIS REST
  `Sejarah_Banjir` service: 1991–2017, 2,222 point/polygon features, in a custom Cassini WKT with
  no EPSG code. Features carry calendar dates only for 2011–2015 and 2017.
- **Hazard layers.** Hotspot (124), potential (93) and flood-area layers are undated and static.
- **No overlap with training data.** No official event-dated flood record overlaps the JPS 2024+
  history. Flood labels will therefore be derived from JPS water-level thresholds (Phase 3).
  National and Penang JPS portals publish different thresholds for 3 of 5 compared stations.
- **MyGDI** requires a formal application. **MyDIMS** (NADMA, 2025+) reports are PDF only; not read.

Details: `data/metadata/gis/GIS_FLOOD_DATASETS.md`.

### Licensing and access constraints

**Verified (2026-09-24):** JPS content (listings, history, map feed) falls under a JPS website
copyright notice requiring prior written consent to copy, redistribute or publish; no data
licence, API terms or polling permission exists, so bulk history (Phase 2), production polling
(Phase 10) and any public display remain **PERMISSION REQUIRED**. Penang GeoHub and SPHTN layers:
UNKNOWN (no licence). data.gov.my Weather API: CC BY 4.0, 4 requests/min. DOSM boundaries: open
licence. Third-party raw captures stay local. Details and draft permission requests:
`docs/DATA_LICENSING_AND_ACCESS.md`.

### Sentinel-1 SAR

Optional module:

- historical flood extent;
- flood segmentation;
- map overlays.

This is not required for the core station-based warning system.

## 3. Station Master

Implemented design (2026-09-24): `docs/STATION_MASTER_DESIGN.md`, which splits this sketch into
site, sensor and versioned threshold records. Elevation, `active` and `valid_to` are not included:
no source supports them yet. Original sketch:

```text
station_id
source
station_name
station_type
district
river
basin
latitude
longitude
elevation_m
alert_level_m
warning_level_m
danger_level_m
active
valid_from
valid_to
```

Only include fields actually supported by source data.

## 4. Observation Schema

Core long-form schema:

```text
source
station_id
observation_time
ingested_at
measurement_type
value
unit
quality_flag
raw_reference
schema_version
```

Examples of `measurement_type`:

- rainfall;
- water_level;
- temperature;
- humidity.

### Raw ingestion contract (implemented 2026-09-24)

The first pipeline stage is `src/floodguard/ingestion/` (`scripts/ingest_raw.py`, one batch per
run). Each captured payload is stored byte-for-byte under its content hash with a records JSONL
(`raw_record/v1`) and a quarantine JSONL, and every attempt is logged in
`data/raw/_manifest/raw_batches.jsonl` (`SUCCEEDED`/`FAILED`/`DUPLICATE`). Raw records keep IDs,
time text and value text exactly as received (`-9999`, `ERROR`, blanks, `Tiada Data`, zero), add a
naive parsed time flagged `UNVERIFIED_ASSUMED_MYT`, a UTC `retrieved_at`, and `fg_sensor_id` from
the station master (unmapped rows are quarantined). Idempotency key: source + dataset + partition
+ payload SHA-256. The long-form schema above is produced later, by validation/normalisation, from
these records. JPS network fetching is disabled pending permission. Details:
`docs/RAW_INGESTION_DESIGN.md`.

### Timestamp normalisation (implemented 2026-09-24)

A derived layer (`src/floodguard/preprocessing/timestamps.py`, `scripts/normalize_timestamps.py`)
re-parses each raw record's time text and writes `data/interim/timestamps/v1/` without touching the
raw store: tz-aware local and UTC times, the zone and whether it was explicit or assumed
(JPS and data.gov.my: `Asia/Kuala_Lumpur`, assumed, not documented by either source), precision
(date-only forecast dates stay date labels), and a `timestamp_quality_flag`
(`VALID`/`MISSING`/`INVALID_FORMAT`/`AMBIGUOUS`/`FUTURE`/`UNSPECIFIED_TIMEZONE`). History sequences
get a monotonicity/duplicate report; nothing is reordered or dropped. Policy:
`docs/TIMESTAMP_POLICY.md`.

### Station-ID normalisation (implemented 2026-09-24)

A second derived layer (`src/floodguard/preprocessing/station_ids.py`,
`scripts/normalize_station_ids.py`) re-resolves each raw record (accepted or quarantined) from its
preserved source IDs with the same resolver the raw layer uses, and writes
`data/interim/station_ids/v1/`: the exact raw `jps_internal_id` and display ID, the stripped lookup
key, `fg_site_id`, `fg_sensor_id`, a `station_id_mapping_status`
(`MAPPED`/`UNMAPPED`/`SENSOR_TYPE_MISMATCH`/`INVALID_SOURCE_ID`/`INVALID_SENSOR_TYPE`) and a check
against the ingest-time mapping. Nothing is dropped, deduplicated or invented.

### Unit validation (implemented 2026-09-24)

A third derived layer (`src/floodguard/preprocessing/units.py`, `scripts/validate_units.py`)
checks each record's primary value, published thresholds and policy-named fields against one unit
registry and writes `data/interim/units/v1/`: canonical measurement type and unit (`mm`, `m`,
`°C`, no conversion), unit provenance, a `unit_validation_status` and a separate
`value_parse_status`. Fields with unverified semantics (e.g. JPS `clean`, `chourly`, `c15min`,
`tdaily`, listing daily totals) are reported but never promoted. Policy: `docs/UNIT_POLICY.md`.

Derived-layer sequence (each step reads the raw records independently; outputs join on
`ingestion_batch_id` + `source_row_index`):

```text
raw records (+ quarantine) ─┬─> interim/timestamps/v1   observation time, timestamp_quality_flag
                            ├─> interim/station_ids/v1  fg_site_id, fg_sensor_id, mapping status
                            ├─> interim/units/v1        measurement type, canonical unit, statuses
                            └─> interim/quality/v1      quality flags per record (validated layer)
                                  └─> processed/observations/v1/<dataset_version>/
                                        canonical long-form table, quality summary, manifest
```

### Quality flags, validated and processed layers (implemented 2026-09-24)

`scripts/build_historical_dataset.py` runs the three component layers over every SUCCEEDED raw
batch, joins their statuses into granular multi-valued quality flags (`docs/QUALITY_FLAGS.md`),
builds the canonical long-form observation table with duplicate/conflict handling, checks
invariants and writes a versioned processed dataset with a quality summary
(`docs/HISTORICAL_PIPELINE.md`). The quality flags in section 7 below are the original proposal;
`STALE`, `OFFLINE`, `INVALID_RANGE`, `DELAYED` and `IMPUTED` are not implemented because no
evidence-backed rule or imputation exists yet.

Canonical observation identity: `(source, fg_sensor_id, observation_time)`. Policy:
`docs/STATION_MASTER_DESIGN.md` section 12.

### Phase 3 rainfall-distribution analysis (implemented 2026-09-25)

`scripts/analyze_rainfall.py` reads one processed dataset, selects `RAINFALL_INTERVAL` rows (mm,
usable) and writes per-station descriptive statistics (zero and wet counts, all-interval and
wet-only statistics, sample-size-guarded quantiles) plus a data-sufficiency report to the
git-ignored `data/analysis/rainfall/<dataset_version>/`. Descriptive only: no labels, features or
thresholds. `docs/RAINFALL_DISTRIBUTION_ANALYSIS.md`.

### Phase 3 water-level trend analysis (implemented 2026-09-25)

`scripts/analyze_water_level.py` reads one processed dataset through the shared verified loader
(`analysis/dataset.py`), selects `WATER_LEVEL` rows (m) and writes per-station, per-observation-
window level statistics, missingness, continuity and backward consecutive changes/rates (no
change across a not-usable row, absent slot or gap > 5 min) plus a data-sufficiency report to the
git-ignored `data/analysis/water_level/<dataset_version>/`. Levels are never pooled across
stations or captures; current JPS thresholds are reference metadata only. No labels, events,
features or windows. `docs/WATER_LEVEL_TREND_ANALYSIS.md`.

### Phase 3 missingness analysis (implemented 2026-09-25)

`scripts/analyze_missingness.py` reads one processed dataset through the shared verified loader
(which now enforces station-master lineage for every Phase 3 analysis) and writes, per sensor,
measurement type and cadence window, expected 5-min slots, usable and missing slots by source
marker (`-9999`, value `ERROR`, `Tiada Data`, blank, non-numeric, duplicate conflict, absent
slot), JPS severity `ERROR` as a separate source state, missing/usable runs and a sufficiency
report to the git-ignored `data/analysis/missingness/<dataset_version>/`. Expected slots exist
only inside history captures; listing rows are point-in-time counts. No cause, reliability label,
freshness status or imputation. `docs/MISSINGNESS_OUTAGE_ANALYSIS.md`.

## 5. Candidate Training Table

```text
timestamp
station_id
district
latitude
longitude

rainfall_15m
rainfall_1h
rainfall_3h
rainfall_6h
rainfall_24h
antecedent_rainfall_3d

water_level
water_level_delta_15m
water_level_delta_30m
water_level_delta_1h
water_level_rise_rate

forecast_rainfall_1h
forecast_rainfall_3h

hour
day_of_week
month
monsoon_or_season

target_30m
target_60m
target_120m
```

Do not create a feature unless its value would be available at serving time.

## 6. Data Quality Rules

Check:

- duplicates;
- non-monotonic timestamps;
- missing time intervals;
- negative rainfall;
- implausible water levels;
- sudden impossible jumps;
- stale data;
- timezone mismatch;
- unit mismatch;
- station re-identification;
- schema drift.

## 7. Missing Data Categories

Use explicit quality flags such as:

```text
VALID
MISSING
STALE
OFFLINE
INVALID_RANGE
DUPLICATE
DELAYED
IMPUTED
```

Do not represent all of them with NaN alone.

## 8. Live Data Strategy

Recommended order:

1. scheduled pull;
2. persist raw response;
3. validate;
4. deduplicate;
5. transform;
6. store;
7. build online features;
8. infer;
9. persist prediction;
10. update dashboard/alerts.

Measure actual update frequency before introducing a broker.

## 9. Replay Mode

Before true live deployment, support deterministic replay:

```text
historical event
     ↓
timestamp-controlled replay
     ↓
same online feature code
     ↓
same inference service
```

Replay mode is useful for:

- E2E testing;
- demos;
- alert logic;
- incident simulations.

## 10. Dataset Versioning

A dataset version should identify:

- source snapshot;
- date range;
- station set;
- cleaning version;
- feature version;
- label version.

Avoid relying on filenames such as `final_v7.csv`.
