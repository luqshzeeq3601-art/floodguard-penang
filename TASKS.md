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
- [ ] TODO Document licensing/terms/access constraints.
- [ ] TODO Define station master table.

## Phase 2 — Historical Data Pipeline

- [ ] TODO Implement raw ingestion.
- [ ] TODO Preserve source payload/CSV.
- [ ] TODO Normalize timestamps.
- [ ] TODO Normalize station IDs.
- [ ] TODO Validate units.
- [ ] TODO Add quality flags.
- [ ] TODO Build raw -> validated -> processed pipeline.
- [ ] TODO Add data-quality tests.

## Phase 3 — EDA and Label Design

- [ ] TODO Analyze rainfall distributions.
- [ ] TODO Analyze water-level trends.
- [ ] TODO Analyze missingness and outages.
- [ ] TODO Identify flood/threshold events.
- [ ] TODO Define +30/+60/+120 labels.
- [ ] TODO Verify class imbalance.
- [ ] TODO Document label limitations.
- [ ] TODO Produce baseline EDA figures.

## Phase 4 — Feature Engineering

- [ ] TODO Rainfall rolling features.
- [ ] TODO Antecedent rainfall.
- [ ] TODO Water-level deltas.
- [ ] TODO Rise-rate features.
- [ ] TODO Weather/forecast features.
- [ ] TODO Temporal features.
- [ ] TODO Station/basin features.
- [ ] TODO Leakage tests.
- [ ] TODO Feature dictionary.

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

- [ ] TODO Penang GIS map.
- [ ] TODO Station detail.
- [ ] TODO Risk status.
- [ ] TODO Forecast/prediction distinction.
- [ ] TODO Alert history.
- [ ] TODO Alert service.
- [ ] TODO E2E tests.

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
