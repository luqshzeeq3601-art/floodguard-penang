# FloodGuard Penang — Master Task Backlog

Status values:

- `TODO`
- `IN_PROGRESS`
- `BLOCKED`
- `DONE`

## Phase 0 — Foundation

- [x] DONE Confirm repository structure. (`src/` layout, `tests/`, `data/` stages, `.gitignore`; see `docs/14_FOLDER_STRUCTURE.md`. Note: directory is not yet a git repository.)
- [x] DONE Configure Python 3.11+ environment. (`.venv` on Python 3.11.9, `.python-version`, `scripts/verify_environment.py`.)
- [x] DONE Configure `pyproject.toml`. (hatchling, `src/` layout, core deps numpy/pandas/pydantic, `[ml]` extra, PEP 735 `dev` group; editable install verified.)
- [x] DONE Configure Ruff, mypy, pytest. (Configured in `pyproject.toml`; mypy strict + pydantic plugin; pytest-cov; smoke tests in `tests/test_package.py`.)
- [x] DONE Add `.env.example`. (4 active Phase 0 variables; later-phase variables commented and phase-tagged; config-loading strategy in `docs/11_SECURITY_RELIABILITY.md`.)
- [ ] BLOCKED Add Docker Compose baseline. (`compose.yaml` written; config validated and image tag confirmed on Docker Hub. Runtime verification blocked: Docker engine cannot start because Windows "Virtual Machine Platform"/WSL features are disabled — user must enable them and reboot.)
- [x] DONE Install/select Claude skills. (6 project-scope plugins + 4 K-Dense skills; Ponytail/Caveman/Graphify pre-existing; state in `docs/15_CLAUDE_SKILLS_SETUP.md`.)
- [x] DONE Configure Graphify ignore paths. (`.graphifyignore` for vendored skills; ML artifact patterns root-anchored in `.gitignore`/`.claudeignore`; verified via Graphify file-selection dry run.)
- [x] DONE Create architecture decision records. (ADR-0001 to ADR-0010 in `docs/decisions/`, indexed in `docs/decisions/README.md`.)

## Phase 1 — Data Discovery

- [x] DONE Inventory Penang JPS rainfall stations. (56 rows from the official state-view HTML fragment; `scripts/discover_jps_rainfall_stations.py` + offline tests; runs identical; display IDs (`jps_display_station_id`) non-unique so rows keyed by graph-link `jps_internal_id`; derived columns `fg_`-prefixed; no coordinates in source. See `data/metadata/jps/README.md`.)
- [x] DONE Inventory Penang JPS water-level stations. (22 rows from the official `aras-air-data` HTML fragment; `scripts/discover_jps_water_level_stations.py` + offline tests; two runs 3.5 min apart identical; basin and per-station thresholds as published; no coordinates/trend/status in listing; 13 `jps_internal_id`s shared with rainfall, not merged. See `data/metadata/jps/README.md`.)
- [x] DONE Verify historical data availability. (JPS date-range JSON endpoints, 5-min, keyed by `jps_internal_id`; 66 probes: confirmed back to at least 2024-09-01 for 3 RF + 3 WL sites and 2024-01-01 for 1 RF site; earlier ranges return "No result"; `-9999`/absent rows/`ERROR` severity documented; event counts unmeasured; depth (~2 yr) flagged against ADR-0004, ADR not edited. See `data/metadata/jps/HISTORICAL_AVAILABILITY.md`.)
- [x] DONE Verify live data access method. (State listings re-verified; 47 requests incl. 14 samples/sensor over 23 min: F2 stations publish every 15 min in sync with 4–7 min lag, others async; no ETag/Last-Modified, conditional requests not honoured; errors signalled in body (`Tiada Data`); recommended 5-min polling of the 2 listings; `fg_live_status` rules provisional; `scripts/probe_jps_live.py`. See `data/metadata/jps/LIVE_ACCESS.md`.)
- [x] DONE Verify METMalaysia API/data access. (Open source is the data.gov.my Weather API: forecast has 28 Penang location IDs, 7-day categorical text + min/max °C, no mm rainfall, no issue time, no archive, so forward-only collection is required; warnings are current-only with issue/valid times and free-text areas. `api.met.gov.my` needs a token (deferred). Radar/satellite are images only. `scripts/probe_metmalaysia.py` + offline tests. See `data/metadata/metmalaysia/ACCESS.md`.)
- [x] DONE Verify data.gov.my historical weather coverage. (25 requests: catalogue (292 datasets) has no METMalaysia/JPS or rainfall/temperature/humidity/pressure/wind/water-level dataset; only historical source is the unmaintained "Weather and Climate" dashboard, daily rainfall total + mean temperature for Bayan Lepas/Butterworth 2020-12-31 → 2022-12-31 (monthly/yearly 2013–2022), frozen, no API, undocumented day boundary, no overlap with JPS 2024+ history, so NOT SUITABLE as features, monthly/yearly OPTIONAL EDA context; no probe script. See `data/metadata/data_gov_my/HISTORICAL_WEATHER.md`.)
- [x] DONE Verify GIS/historical flood datasets. (135 requests: official lat/lon for 56/56 RF + 22/22 WL inventory IDs from the JPS map feed `latestreadingstrendabc.json` (CRS inferred WGS84); JPS basin/river/district GeoJSON and DOSM district GeoJSON (CRS84); Penang GeoHub ArcGIS `Sejarah_Banjir` 1991–2017 (2,222 features, dated only 2011–2015/2017, custom Cassini WKT) plus undated hotspot/potential layers; no official event-dated record overlaps JPS 2024+, so JPS threshold exceedance is the leading label option; thresholds differ between national and Penang JPS portals for 3/5 compared stations; MyGDI needs application, NADMA PDFs unread; `scripts/probe_gis_sources.py` + offline tests. See `data/metadata/gis/GIS_FLOOD_DATASETS.md`.)
- [x] DONE Document licensing/terms/access constraints. (71 evidence requests; JPS website copyright notice requires prior written consent to copy/redistribute/publish and no API terms or polling permission exist, so JPS use is PERMISSION REQUIRED (training UNCERTAIN) pending a JPS reply; GeoHub/SPHTN UNKNOWN (empty licence fields); data.gov.my Weather API CC BY 4.0 (4 req/min); DOSM boundaries open; 37 third-party raw captures untracked (kept locally, sha256 manifest `data/metadata/RAW_EVIDENCE_MANIFEST.csv`); embedded Google Maps key redacted from a fixture; already-pushed public history unchanged. See `docs/DATA_LICENSING_AND_ACCESS.md`.)
- [x] DONE Define station master table. (Site/sensor/threshold model; UUIDv5 IDs under a pinned namespace from source + whitespace-stripped `jps_internal_id` (+ sensor type), never names/times; shared IDs merged only on one official map-feed record + exact district/basin match, else separate review sites flagged; local build: 65 sites, 56 RF + 22 WL sensors, all 13 shared IDs confirmed multi-sensor, 0 ambiguous, 103 threshold records (NORMAL never label-eligible; 3 sensors with national/Penang conflict); real output git-ignored in `data/local/station_master/`; `src/floodguard/station_master.py`, `scripts/build_station_master.py`, synthetic-fixture tests. See `docs/STATION_MASTER_DESIGN.md`.)

## Phase 2 — Historical Data Pipeline

- [x] DONE Implement raw ingestion. (`src/floodguard/ingestion/` + `scripts/ingest_raw.py`: one offline batch per run for JPS rainfall/water-level listings and history and the data.gov.my forecast; payload kept byte-for-byte under its sha256 with records/quarantine JSONL, append-only manifest, SUCCEEDED/FAILED/DUPLICATE idempotency, all-or-nothing writes, values/times as received, `fg_sensor_id` via the station master with unmapped rows quarantined; JPS network fetch disabled pending permission; 47 offline tests. Includes payload preservation for ingested batches; validation/normalisation tasks remain TODO. See `docs/RAW_INGESTION_DESIGN.md`.)
- [x] DONE Preserve source payload/CSV. (Audit of raw ingestion, no code change needed: all five adapters store the supplied bytes via binary write-once temp-then-rename; SHA-256 of the stored file = manifest `payload_sha256`; records/quarantine in separate files; a repeat is DUPLICATE with the file unchanged; history partitioned by station; storage is format-agnostic (`<sha256>.<ext>`), so CSV needs no change. `tests/test_raw_payload_preservation.py`: 13 offline tests incl. CRLF/trailing-whitespace/BOM variants and a synthetic CSV. See `docs/RAW_INGESTION_DESIGN.md` §2.)
- [x] DONE Normalize timestamps. (Derived layer `src/floodguard/preprocessing/timestamps.py` + `scripts/normalize_timestamps.py`: re-parses raw time text with the verified per-dataset formats, one source-timezone registry (JPS and data.gov.my: `Asia/Kuala_Lumpur` assumed, undocumented upstream, marked `UNSPECIFIED_ASSUMED`), tz-aware local + UTC, DATE/MINUTE/SECOND precision (forecast dates stay date labels), `timestamp_quality_flag` VALID/MISSING/INVALID_FORMAT/AMBIGUOUS/FUTURE (> `retrieved_at` + 10 min)/UNSPECIFIED_TIMEZONE, monotonicity/duplicate report for history; write-once output under `data/interim/timestamps/v1/`, raw untouched. 47 offline tests. See `docs/TIMESTAMP_POLICY.md`.)
- [x] DONE Normalize station IDs. (Derived layer `src/floodguard/preprocessing/station_ids.py` + `scripts/normalize_station_ids.py`: re-resolves every raw record (accepted and quarantined) from its preserved `jps_internal_id` + sensor type with the single shared resolver `SensorMapper.lookup`; the ingest-time `fg_sensor_id` is provisional and cross-checked (conflicting non-null IDs rejected); adds `fg_site_id`, exact raw IDs, stripped `lookup_key`, status MAPPED/UNMAPPED/SENSOR_TYPE_MISMATCH/INVALID_SOURCE_ID/INVALID_SENSOR_TYPE; master inconsistencies are hard load errors (no AMBIGUOUS status); never maps by name or display ID, never drops or deduplicates; write-once output under `data/interim/station_ids/v1/`, raw untouched; local captures: 1,023/1,023 rows MAPPED, 0 raw/derived disagreements; 28 offline tests. See `docs/STATION_MASTER_DESIGN.md` §12.)
- [x] DONE Validate units. (Derived layer `src/floodguard/preprocessing/units.py` + `scripts/validate_units.py`: one registry promotes only evidence-backed fields: JPS listing 1 h rainfall and history `raw` (5-min interval) in mm, listing/history water level in m, Normal/Waspada/Amaran/Bahaya thresholds in m (category separate, history thresholds stay `CURRENT_NOT_HISTORICAL`), data.gov.my forecast min/max temperature in °C [doc]; `clean`/`chourly`/`c15min`/`tdaily`/`cdaily`/`cyearly`, WL `raw`/`ecm`/`clean`, rainfall thresholds and listing daily totals excluded; `unit_validation_status` VALID/MISSING_UNIT/UNKNOWN_UNIT/UNIT_MISMATCH/SENSOR_TYPE_MISMATCH/UNKNOWN_MEASUREMENT_SEMANTICS kept apart from `value_parse_status`; no conversion, bounds or imputation; write-once output under `data/interim/units/v1/`, raw untouched; local captures: 9,507 rows, 3,903 VALID, 0 unit/sensor failures; 55 offline tests. See `docs/UNIT_POLICY.md`.)
- [x] DONE Add quality flags. (`src/floodguard/validation/quality_flags.py`: joins the rows the timestamp, station-ID and unit layers already produced (no re-parsing/re-resolving) and emits a sorted multi-flag list per raw record and measurement field, with every component status preserved; 29 granular flags (raw quarantine/structure, timestamp MISSING/INVALID_FORMAT/AMBIGUOUS/FUTURE/UNSPECIFIED_TIMEZONE/DATE_ONLY, TIMEZONE_ASSUMED, sensor UNMAPPED/SOURCE_ID_INVALID/SENSOR_TYPE_MISMATCH/INVALID, unit MISSING/UNKNOWN/MISMATCH/SENSOR_TYPE_MISMATCH, MEASUREMENT_SEMANTICS_UNKNOWN, separate `-9999`/`ERROR`/`Tiada Data`/empty/non-numeric value flags, definitional RAINFALL_NEGATIVE, JPS SOURCE_SEVERITY_ERROR, duplicate flags), blocking vs informational, `usable`; zero rainfall never flagged; no range/freshness rules; no Normal/Waspada/Amaran/Bahaya; join defects raise `PipelineJoinError`; local captures: 1,611 rows, 599 usable; 30 offline tests. JPS README threshold unit fixed to metres. See `docs/QUALITY_FLAGS.md`.)
- [x] DONE Build raw -> validated -> processed pipeline. (`src/floodguard/validation/build.py` + one-shot `scripts/build_historical_dataset.py`: every SUCCEEDED raw batch, payload/records/quarantine hashes checked against the manifest, raw store only read; component layers run with their own functions and written to the same interim paths/bytes as their scripts; validated layer `interim/quality/v1`; canonical long-form table `processed/observations/v1/<dataset_version>/` keyed by `source + fg_sensor_id + observation_time_utc` (+ measurement type), markers kept with null value, cross-batch duplicates collapsed only when identical (full provenance), conflicts kept unresolved with null value and candidates, FUTURE/unmapped/forecast rows excluded and counted, strict chronological order, no filling or windows, `first_retrieved_at`; input-hash dataset version independent of ingestion order; write-once, rerun no-op; quality summary with per-sensor/per-day counts and 5-min absent-slot report; local captures: 9 batches, 1,611 validated rows, 1,017 canonical rows (593 usable), 5 identical duplicate groups, 0 conflicts; 12 offline tests. See `docs/HISTORICAL_PIPELINE.md`.)
- [x] DONE Add data-quality tests. (`src/floodguard/validation/checks.py`: 15 invariant checks run on every build before anything processed is written (exit 1 on failure, results stored in the dataset manifest): unique canonical key, strict chronological order, no row lost between validated and canonical layers, verified measurement types and units only, complete identity, value/null consistent with parse status and missing-value flags, zero never missing, usable consistent with flags, no observation after capture + 10 min, timezone assumption flagged, complete provenance, conflicts unresolved, no usable negative rainfall, known/sorted flags; `tests/test_data_quality_checks.py` breaks each invariant and asserts detection, plus summary-before-exclusion and determinism tests (22 offline tests); with the pipeline and quality-flag suites, Phase 2 steps 6–8 add 64 tests. See `docs/HISTORICAL_PIPELINE.md` §5.)

## Phase 3 — EDA and Label Design

- [x] DONE Analyze rainfall distributions. (`src/floodguard/analysis/rainfall.py` + one-shot `scripts/analyze_rainfall.py`: reads one processed dataset (manifest hash, checks and schemas verified), selects only `RAINFALL_INTERVAL`/mm/usable rows (water level, 1-hour totals and unknown types cannot enter; malformed rows rejected), per-station zero/wet counts and proportions (wet = value > configurable 0 mm), all-interval and wet-only statistics, type-7 quantiles, median, std and skewness guarded by sample size (`INSUFFICIENT_SAMPLE`, p99 needs 500), concentration, calendar coverage, and a data-sufficiency report (basic, wet-only, station comparison, seasonal, monsoon, extreme events) with evidence levels; dataset version and station-master hash in every output; write-once, deterministic JSON under git-ignored `data/analysis/rainfall/<dataset_version>/`; no plots, labels, features, windows or thresholds; 43 synthetic offline tests; ml-reviewer findings fixed. Local check: 1 station, 1 day (289 intervals): implementation and station-window descriptive only; seasonal/monsoon/extreme/station comparison INSUFFICIENT. See `docs/RAINFALL_DISTRIBUTION_ANALYSIS.md`.)
- [x] DONE Analyze water-level trends. (`src/floodguard/analysis/water_level.py` + one-shot `scripts/analyze_water_level.py`, input contract shared with rainfall in `analysis/dataset.py`: selects only canonical `WATER_LEVEL`/m rows (rainfall, thresholds, WL `raw`/`ecm`/`clean`, wrong units and repeated instants rejected or excluded); per sensor and per observation window (captures > 1 day apart never pooled; no cross-station level aggregation): coverage and `-9999`/`ERROR` missingness, guarded level statistics and quantiles, guarded net change; backward consecutive changes and m/h rates only between adjacent trend-eligible rows <= 5 min apart (verified history grid; no interpolation, fill or centred window), neutral RISING/FALLING/STABLE (tolerance 0 = equality), runs and breaks with reasons; current Waspada/Amaran/Bahaya as `CURRENT_REFERENCE_ONLY` metadata with provenance, NORMAL excluded, never labels; sufficiency report (basic, quantiles, consecutive change, rate, station comparison, seasonal, monsoon, threshold events, long-term); dataset version and observation/station-master/threshold hashes in every output; write-once deterministic JSON under git-ignored `data/analysis/water_level/<dataset_version>/`; 52 synthetic offline tests; ml-reviewer findings (1 medium, 3 low) fixed with regression tests. Local check: 2 history station-windows (26460: 35/289 usable; 27608: 119/289) + listing snapshots: implementation and station-window descriptive only; station comparison, seasonal, monsoon, threshold-event and long-term INSUFFICIENT. See `docs/WATER_LEVEL_TREND_ANALYSIS.md`.)
- [x] DONE Analyze missingness and outages. (`src/floodguard/analysis/missingness.py` + one-shot `scripts/analyze_missingness.py`: all three canonical types analysed separately per sensor and per cadence window. Expected 5-min slots exist only inside JPS history captures: ingestion batches merge when they overlap or touch; separate captures or internal gaps > 60 min end the window and are never counted as missing. Listing rows are point-in-time only, with no cadence or outage. Slot states: USABLE, `DUPLICATE_CONFLICT`, `SENTINEL_-9999`, value `ERROR`, `TIADA_DATA`, `BLANK`, `NON_NUMERIC`, other, `LISTING_ONLY_SLOT`, `ABSENT_SLOT`. JPS severity `ERROR` is a separate source state; zero is never missing. Missing/usable runs with exact durations and window-edge censoring; guarded run-length statistics; slot-weighted network summary per type; sufficiency report (window, run length, sensor, network, seasonal, monsoon, long-term, live outage). No cause, reliability label, freshness rule or imputation. The station-master lineage check moved into the shared `load_station_context` for all Phase 3 scripts (rainfall now enforces it; outputs unchanged). Write-once deterministic JSON under git-ignored `data/analysis/missingness/<dataset_version>/`. 34 synthetic offline tests plus a rainfall lineage regression test; ml-reviewer findings (2 medium, 4 low) fixed with regression tests. Local check: 3 one-day history windows (rainfall 289/289; WL 26460 35/289; WL 27608 119/289, with 167 of its 170 `-9999` carrying severity `ERROR`), 0 absent slots. Supports window-descriptive only; run-length distribution, sensor/network, seasonal, monsoon, long-term and live-outage analyses INSUFFICIENT. See `docs/MISSINGNESS_OUTAGE_ANALYSIS.md`.)
- [x] DONE Identify flood/threshold events. (`src/floodguard/analysis/events.py` + one-shot `scripts/identify_events.py`: segments contiguous threshold exceedance episodes against current reference thresholds (Waspada, Amaran, Bahaya; NORMAL excluded); preserves event start/end times, durations, peaks, missing-data interruption reasons (ENDED_BELOW_THRESHOLD, INTERRUPTED_BY_MISSING_DATA, WINDOW_EDGE); strictly distinguishes observed exceedances, contiguous episodes, and confirmed flood disasters (count = 0; no official event-dated flood catalogue overlapping JPS 2024+); thresholds marked CURRENT_THRESHOLD_REFERENCE_ONLY; write-once deterministic JSON under `data/analysis/events/<dataset_version>/`; 7 synthetic offline tests. See `docs/EVENT_IDENTIFICATION.md`.)
- [x] DONE Define +30/+60/+120 labels. (`src/floodguard/analysis/labels.py` + one-shot `scripts/define_labels.py`: defines prediction targets independently for +30, +60, +120 min horizons; separates target construction from feature space; supports binary proxy exceedance, threshold escalation onset, and level delta regression; missing future observations strictly marked MISSING_FUTURE_TARGET without imputation; write-once deterministic JSON under `data/analysis/labels/<dataset_version>/`; 3 synthetic offline tests. See `docs/LABEL_DEFINITION.md`.)
- [x] DONE Verify class imbalance. (`src/floodguard/analysis/class_imbalance.py` + one-shot `scripts/verify_class_imbalance.py`: computes positive counts, prevalence, and negative:positive imbalance ratios across horizons and thresholds; separates row-level exceedance counts from distinct event episodes; evaluates 3-way chronological train/val/test splitting viability (requires >= 10 distinct episodes, >= 30 positives; marked INSUFFICIENT on current local captures); write-once deterministic JSON under `data/analysis/class_imbalance/<dataset_version>/`; 2 synthetic offline tests. See `docs/CLASS_IMBALANCE.md`.)
- [x] DONE Document label limitations. (Comprehensive technical audit in `docs/LABEL_LIMITATIONS.md`: operational proxy targets vs confirmed flood ground truth, lack of historical threshold versioning, national vs Penang threshold conflicts, non-flood semantics of NORMAL, missing-target safety protocols, horizon boundary truncation, and empirical sample feasibility constraints.)
- [x] DONE Produce baseline EDA figures. (`src/floodguard/analysis/figures.py` + one-shot `scripts/produce_baseline_figures.py`: automated offline figure generation for 5-min rainfall hyetographs & distributions, water-level time series with explicit gap breaks (never connecting lines across missing intervals), CURRENT_REFERENCE_ONLY threshold indicators, and slot-level missingness summaries; saved under git-ignored `data/analysis/figures/<dataset_version>/`; 4 synthetic offline tests. See `docs/BASELINE_EDA_FIGURES.md`.)

## Phase 4 — Feature Engineering

- [x] DONE Rainfall rolling features. (`src/floodguard/features/rainfall.py` + `tests/test_rainfall_features.py`: trailing 15, 30, 60, 120, 180 min backward-looking rolling sums, max, wet counts, coverage ratios, and wet indicators on (t - W, t]; strict minimum coverage guards; 0.0 distinct from missing; elapsed time since last wet interval; see `docs/FEATURE_ENGINEERING.md` §3.1.)
- [x] DONE Antecedent rainfall. (`src/floodguard/features/rainfall.py` + `tests/test_rainfall_features.py`: exact backward lags 0, 5, 10, 15, 30, 60 min; extended 6h, 12h, 24h antecedent accumulation windows and coverage ratios; missing slots evaluate to None without imputation; see `docs/FEATURE_ENGINEERING.md` §3.2.)
- [x] DONE Water-level deltas. (`src/floodguard/features/water_level.py` + `tests/test_water_level_features.py`: point-in-time level; backward deltas over 5, 15, 30, 60, 120 min; continuity-breaking gaps evaluate to None; station-specific datums preserved; see `docs/FEATURE_ENGINEERING.md` §3.3.)
- [x] DONE Rise-rate features. (`src/floodguard/features/water_level.py` + `tests/test_water_level_features.py`: backward rise rates in m/h; trailing window min/max/mean/range; categorical RISING/FALLING/STABLE trends; distance-to-threshold reference features marked CURRENT_THRESHOLD_REFERENCE_ONLY; see `docs/FEATURE_ENGINEERING.md` §3.3 & §3.4.)
- [x] DONE Weather/forecast features. (`src/floodguard/features/weather.py` + `tests/test_weather_features.py`: point-in-time daily min/max temperature, temperature range, and rain/thunderstorm forecast indicators from data.gov.my forecast with retrieved_at <= t guard; see `docs/FEATURE_ENGINEERING.md` §3.7.)
- [x] DONE Temporal features. (`src/floodguard/features/temporal.py` + `tests/test_temporal_features.py`: local hour, minute, day of week, month, weekend flag; exact stateless cyclical encodings for hour, month, day of week in [-1.0, 1.0]; see `docs/FEATURE_ENGINEERING.md` §3.5.)
- [x] DONE Station/basin features. (`src/floodguard/features/spatial.py`, `src/floodguard/features/paired.py`, `tests/test_spatial_features.py`: WGS84 coordinates, district, main basin, sensor modality; multi-sensor paired site feature vectors for the 13 verified Penang shared sites; see `docs/FEATURE_ENGINEERING.md` §3.6 & §3.8.)
- [x] DONE Leakage tests. (`tests/test_feature_leakage.py`: adversarial future mutation test over feature tables, left-open/right-closed boundary tests, target label modification independence, appended future data invariance, and threshold classification verification; see `docs/FEATURE_ENGINEERING.md` §2.)
- [x] DONE Feature dictionary. (`docs/FEATURE_ENGINEERING.md` + `src/floodguard/features/registry.py`: 97 registered features with name, family, measurement type, unit, lookback window, min coverage, null semantics, point-in-time semantics, and leakage classification; `scripts/build_features.py` + `tests/test_feature_pipeline.py`.)

## Phase 5 — Baselines and ML

- [ ] TODO Persistence/rule baseline.
- [ ] TODO Logistic Regression.
- [ ] TODO Random Forest.
- [ ] TODO XGBoost/LightGBM.
- [ ] TODO Chronological validation.
- [ ] TODO Walk-forward validation where practical.
- [ ] TODO Calibration analysis.
- [ ] TODO SHAP analysis.
- [ ] TODO Select candidate production model.

## Phase 6 — Water-Level Forecasting

- [ ] TODO Persistence baseline.
- [ ] TODO Statistical baseline.
- [ ] TODO Gradient boosting with lag features.
- [ ] TODO LSTM/GRU only if justified.
- [ ] TODO Optional TimesFM benchmark.
- [ ] TODO Horizon-specific MAE/RMSE.

## Phase 7 — MLOps

- [ ] TODO MLflow experiments.
- [ ] TODO Model registry.
- [ ] TODO DVC/lineage strategy.
- [ ] TODO Model card.
- [ ] TODO Dataset card.
- [ ] TODO Automated model tests.
- [ ] TODO Promotion gate.

## Phase 8 — Backend + Database

- [ ] TODO PostgreSQL/PostGIS.
- [ ] TODO Station schema.
- [ ] TODO Observation schema.
- [ ] TODO Prediction schema.
- [ ] TODO Alert schema.
- [ ] TODO FastAPI `/health`.
- [ ] TODO FastAPI `/ready`.
- [ ] TODO Prediction endpoints.
- [ ] TODO Integration tests.

## Phase 9 — Streamlit

- [ ] TODO Overview.
- [ ] TODO Live Monitoring.
- [ ] TODO Flood Prediction.
- [ ] TODO Station Analysis.
- [ ] TODO Model Performance.
- [ ] TODO SHAP Explainability.
- [ ] TODO Data Quality.
- [ ] TODO Model Drift.

## Phase 10 — Live Ingestion

- [ ] TODO Implement polling/scheduled ingestion first.
- [ ] TODO Measure ingestion latency.
- [ ] TODO Add stale-station detection.
- [ ] TODO Add idempotency.
- [ ] TODO Decide whether Kafka/MQTT is justified.
- [ ] TODO Live inference pipeline.
- [ ] TODO Prediction persistence.

## Phase 11 — React UI + Alerts

- [ ] IN_PROGRESS Penang GIS map. (UI built in `frontend/` against the planned API contract; awaits `/api/v1/stations` with station-master coordinates.)
- [ ] IN_PROGRESS Station detail. (UI built; awaits stations/observations/predictions endpoints.)
- [ ] IN_PROGRESS Risk status. (UI built; FloodGuard risk labels await the Phase 3 label definition.)
- [ ] IN_PROGRESS Forecast/prediction distinction. (UI separates JPS observed data, official thresholds, FloodGuard-derived freshness and predictions; see `frontend/design.md`.)
- [ ] IN_PROGRESS Alert history. (UI built; awaits alert schema/service.)
- [ ] TODO Alert service.
- [ ] IN_PROGRESS E2E tests. (Playwright + axe against the synthetic mock API in `frontend/e2e/`; rerun against the real API when it exists.)

## Phase 12 — Observability / Deployment

- [ ] TODO Prometheus metrics.
- [ ] TODO Grafana dashboards.
- [ ] TODO Drift checks.
- [ ] TODO Docker production build.
- [ ] TODO Cloud deployment.
- [ ] TODO CI/CD.
- [ ] TODO Runbook.
- [ ] TODO Failure drills.

## Phase 13 — Optional Satellite CV

- [ ] TODO Acquire Sentinel-1 historical flood scenes.
- [ ] TODO Preprocess SAR.
- [ ] TODO Build flood masks/labels.
- [ ] TODO Segmentation baseline.
- [ ] TODO U-Net or equivalent.
- [ ] TODO IoU/Dice evaluation.
- [ ] TODO GIS overlay.
