# FloodGuard Penang — Agent Contract

## 1. Mission

FloodGuard Penang is a production-grade ML flood early-warning platform for Pulau Pinang, Malaysia.

The system must support:

- historical training data;
- live environmental observations;
- flood-risk predictions for +30, +60, and +120 minutes;
- future water-level forecasting where supported by data;
- GIS-aware station and flood context;
- explainable predictions;
- reproducible experiments;
- deployment and serving;
- Streamlit internal analytics;
- React operational UI;
- drift, quality, latency, and reliability monitoring.

## 2. Engineering Priorities

In order:

1. correctness;
2. temporal integrity;
3. data quality;
4. low false-negative flood detection;
5. reproducibility;
6. reliability;
7. observability;
8. maintainability;
9. security;
10. portfolio clarity.

## 3. Geographic Scope

Initial geographic scope: **Pulau Pinang only**.

Do not silently mix non-Penang stations into training or validation.

Each station should have, where available:

- stable station ID;
- station name;
- district;
- latitude;
- longitude;
- basin/river;
- source;
- threshold metadata;
- active/inactive status.

## 4. Data Sources

Primary intended sources:

- JPS Public Infobanjir:
  - rainfall observations;
  - river/water-level observations;
  - station metadata;
  - thresholds/trends where available.
- METMalaysia:
  - weather observations/forecasts;
  - warnings;
  - rainfall/weather context.
- data.gov.my:
  - historical Malaysian weather/climate data where suitable.
- MyGDI/JPS geospatial datasets:
  - historical flood areas/hazard context where accessible.
- Sentinel-1 SAR:
  - optional historical flood-extent / segmentation module.

Source availability, licensing, access method, and schema must be verified during implementation.

## 5. Prediction Tasks

### Classification

Predict whether flood risk / threshold escalation occurs at:

- +30 minutes;
- +60 minutes;
- +120 minutes.

### Regression

Forecast future river/water level where sufficient history exists.

### Optional Computer Vision

Sentinel-1 SAR flood-extent segmentation is a separate optional module.

Do not block the core station-based early-warning system on the satellite module.

## 6. Model Order

Use simple-to-complex progression:

1. rule/persistence baseline;
2. Logistic Regression;
3. Random Forest;
4. XGBoost or LightGBM;
5. LSTM/GRU only if sequence data volume and validation justify it;
6. optional TimesFM benchmark for appropriate univariate forecasting;
7. optional U-Net or similar segmentation model for Sentinel-1.

## 7. Evaluation

Flood classification:

- recall;
- precision;
- F1;
- PR-AUC;
- false-negative rate;
- confusion matrix;
- calibration;
- inference latency.

Water level:

- MAE;
- RMSE;
- horizon-specific error.

Optional segmentation:

- IoU;
- Dice/F1;
- precision/recall.

Never use a single metric as the sole promotion criterion.

## 8. Engineering Targets

Targets, not claims:

- flood-event recall >= 90%;
- F1 >= 0.85;
- API inference latency < 500 ms;
- water-level MAE <= 0.20 m where feasible;
- automated ingestion-to-inference path;
- monitored data-quality failures;
- reproducible model experiments;
- critical-path automated test coverage >= 80%.

Actual results may be lower and must be reported honestly.

## 9. Temporal Safety

This is time-series data.

Never:

- use future rows in rolling features;
- fit preprocessing on validation/test data;
- random-shuffle temporal rows when it causes leakage;
- create labels using information unavailable at inference without documenting the horizon;
- tune hyperparameters on the final test set.

Prefer:

- chronological split;
- rolling/walk-forward validation;
- station-aware temporal holdout;
- event-based analysis.

## 10. Data Pipeline

Raw data is immutable.

```text
raw
 ↓
validated
 ↓
interim
 ↓
processed
 ↓
model-ready
```

Preserve:

- observation timestamp;
- ingestion timestamp;
- source;
- station ID;
- unit;
- original value;
- cleaned value;
- quality flags;
- schema version.

Use `Asia/Kuala_Lumpur` explicitly when appropriate.

## 11. Missing Data

Never treat all missing sensor data as zero.

Differentiate:

- true zero rainfall;
- missing observation;
- stale observation;
- offline sensor;
- invalid value;
- delayed ingestion.

Every imputation policy must be documented.

## 12. Production Architecture

Core services:

- ingestion;
- validation;
- feature pipeline;
- PostgreSQL/PostGIS;
- ML training;
- MLflow registry;
- FastAPI;
- live inference;
- Streamlit;
- React;
- alerts;
- monitoring.

Kafka or MQTT is optional and should be introduced only when streaming requirements justify it.

## 13. Streamlit Role

Streamlit is the internal ML/analytics surface.

Use it for:

- EDA;
- feature inspection;
- live monitoring;
- prediction testing;
- station analysis;
- model comparison;
- SHAP;
- data quality;
- drift.

Do not duplicate core business logic in Streamlit.

Call shared services or APIs.

## 14. React Role

React/TypeScript is the polished operational/public-facing interface.

It should consume FastAPI rather than directly importing ML code.

## 15. MLOps

Use:

- MLflow for experiment/model tracking;
- DVC where useful for dataset/version lineage;
- Git for source control;
- Docker for reproducible runtime;
- GitHub Actions for CI;
- Evidently for suitable drift/data-quality analysis;
- Prometheus/Grafana for operational telemetry.

Each meaningful ML run should record:

- dataset version;
- feature version;
- code commit;
- model;
- hyperparameters;
- random seed;
- validation design;
- metrics;
- artifact;
- timestamp.

## 16. Model Promotion

A candidate model must be evaluated against the current baseline/production model.

Check:

- recall;
- false-negative rate;
- PR-AUC;
- calibration;
- robustness;
- latency;
- data dependencies;
- explainability;
- operational complexity.

Do not promote a model only because accuracy is higher.

## 17. Explainability

Use SHAP where appropriate.

Correct framing:

> Recent rainfall accumulation and a rapid water-level rise contributed strongly to the prediction.

Do not present SHAP as causal proof.

## 18. APIs

FastAPI requirements:

- Pydantic validation;
- explicit response models;
- structured errors;
- health endpoint;
- readiness endpoint;
- structured logging;
- model-version metadata;
- no stack traces/secrets in external responses.

Likely endpoints:

```text
/health
/ready
/api/v1/stations
/api/v1/observations
/api/v1/predictions
/api/v1/model
/api/v1/monitoring
```

## 19. Database

Use PostgreSQL.

Use PostGIS for spatial data.

Store:

- stations;
- observations;
- quality flags;
- prediction history;
- model metadata;
- alerts;
- relevant geospatial context.

Do not store large model binaries directly in PostgreSQL.

Use migrations.

## 20. Reliability

Design for:

- upstream API unavailable;
- partial station outage;
- delayed observation;
- duplicate ingestion;
- malformed payload;
- model artifact unavailable;
- database unavailable;
- prediction failure;
- alert delivery failure.

Prefer idempotent ingestion and explicit retries with bounded backoff.

## 21. Monitoring

System:

- API latency;
- error rate;
- readiness;
- pipeline failures;
- ingestion lag.

Data:

- missingness;
- stale stations;
- schema changes;
- range violations;
- feature drift.

Model:

- prediction distribution;
- confidence;
- calibration where measurable;
- event performance when labels arrive;
- false positives;
- false negatives.

Drift alone does not mean model failure.

## 22. Testing

Required categories:

- unit;
- data quality;
- temporal leakage;
- model;
- API;
- integration;
- migration;
- pipeline;
- E2E for critical workflows.

Never delete or weaken tests merely to make CI pass.

## 23. Security

Never commit:

- API keys;
- passwords;
- tokens;
- cloud credentials;
- private endpoints.

Use environment variables and `.env.example`.

Validate all external input.

## 24. Skill Precedence

1. project correctness/safety;
2. domain skill;
3. workflow skill;
4. Graphify;
5. Ponytail;
6. Caveman.

A lower-priority skill may not weaken a higher-priority requirement.

## 25. Definition of Done

A task is complete only when:

- implementation works;
- targeted tests pass;
- relevant broader checks pass;
- lint passes;
- relevant type checks pass;
- temporal/data-quality impact is reviewed;
- documentation is updated where needed;
- no secrets are added;
- claims are supported by reproducible evidence.

For ML tasks also require:

- dataset version;
- validation strategy;
- baseline comparison;
- recorded metrics;
- traceable artifact.
