# Resume Impact Plan

## 1. Rule

Only use measured, reproducible achievements.

Do not write targets as achievements.

Bad:

> Achieved 90% flood recall.

if the model has not actually produced that result.

Good before final evaluation:

> Built a multi-horizon flood-risk pipeline targeting 30–120 minute early warning using rainfall and water-level features.

## 2. Resume Bullet Templates

Replace placeholders only with verified values.

### ML

> Developed and benchmarked Logistic Regression, Random Forest, and XGBoost models for Penang flood-risk prediction across 30/60/120-minute horizons, achieving **[verified recall] recall**, **[verified F1] F1**, and **[verified PR-AUC] PR-AUC** on out-of-time evaluation.

### Data Engineering

> Built an automated environmental-data pipeline integrating **[verified sources]** across **[verified station count] Penang stations**, with schema validation, duplicate control, freshness checks, and PostgreSQL/PostGIS storage.

### Production Serving

> Productionized ML inference with FastAPI and Docker, achieving **[verified p95 latency] ms p95** prediction latency and persisting model-versioned predictions for reproducible monitoring.

### MLOps

> Implemented MLflow experiment tracking, dataset/feature lineage, model promotion gates, CI testing, and drift/data-quality monitoring across **[verified experiment/model count]** reproducible runs.

### Live System

> Built a live/replay flood-monitoring workflow from observation ingestion through validation, feature generation, inference, dashboard visualization, and alert generation with **[verified ingestion latency/uptime]**.

## 3. Strong Quantifiable Metrics

Track from day one:

- number of Penang stations;
- historical rows;
- years/months of history;
- number of engineered features;
- recall;
- false-negative rate;
- F1;
- PR-AUC;
- calibration error/Brier score where used;
- MAE/RMSE;
- p50/p95 API latency;
- ingestion lag;
- stale-sensor detection time;
- test count;
- critical-path coverage;
- number of MLflow runs;
- Docker image size if meaningful;
- deployment uptime only if actually monitored.

## 4. Portfolio Results Table

Create this after evaluation:

| Metric | Baseline | Candidate | Production |
|---|---:|---:|---:|
| Recall | TBD | TBD | TBD |
| F1 | TBD | TBD | TBD |
| PR-AUC | TBD | TBD | TBD |
| False-negative rate | TBD | TBD | TBD |
| p95 latency | TBD | TBD | TBD |
| MAE 60m | TBD | TBD | TBD |

## 5. Interview Narrative

Be able to explain:

1. why flood prediction is temporal;
2. how leakage was prevented;
3. why a model was selected;
4. how live data enters the system;
5. what happens when sensors fail;
6. how model drift differs from data drift;
7. why Streamlit and React serve different users;
8. which outcomes are measured versus planned.
