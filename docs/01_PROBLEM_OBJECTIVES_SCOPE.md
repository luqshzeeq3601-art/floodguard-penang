# Problem Statements, Objectives, and Scope

## 1. Problem Statements

### Problem 1 — Flood monitoring can be reactive

Environmental monitoring can tell users what rainfall and river levels are now, but operational value improves when the system estimates whether conditions may become dangerous before the threshold is reached.

**ML opportunity:**

Predict flood-risk escalation 30–120 minutes ahead using recent rainfall, water-level behavior, weather context, and station history.

### Problem 2 — Relevant flood data is fragmented

Rainfall, water level, forecasts, station metadata, flood maps, and satellite information may exist in different formats and systems.

**Engineering opportunity:**

Build a reproducible pipeline that unifies environmental observations, station metadata, GIS context, and model-ready features.

### Problem 3 — A prediction model alone is not an operational system

A notebook can produce good offline metrics but still fail in production because of:

- stale sensors;
- missing readings;
- schema changes;
- delayed data;
- false alarms;
- API failures;
- model drift;
- unclear model reasoning.

**Production opportunity:**

Build an ML platform that validates data, tracks models, serves predictions, explains outputs, and monitors failures.

## 2. Objectives

### Objective 1 — Early flood-risk prediction

Develop models that predict risk at:

- +30 minutes;
- +60 minutes;
- +120 minutes.

Primary target metrics:

- recall >= 90%;
- F1 >= 0.85;
- low false-negative rate.

These are engineering targets until validated.

### Objective 2 — Automated end-to-end ML platform

Automate:

- ingestion;
- validation;
- storage;
- feature generation;
- model inference;
- prediction storage;
- monitoring;
- alert triggering.

### Objective 3 — Production-grade, explainable deployment

Deliver:

- FastAPI model service;
- PostgreSQL/PostGIS storage;
- Streamlit ML dashboard;
- React operational UI;
- SHAP explanations;
- MLflow tracking;
- DVC/lineage;
- data/model monitoring;
- CI/CD;
- Dockerized deployment.

## 3. Project Scope

### Geographic

Pulau Pinang.

### Data

- rainfall;
- river/water level;
- weather/forecast context;
- station metadata;
- geospatial metadata;
- historical flood/hazard context when available.

### ML

- classification;
- regression/time-series forecasting;
- optional satellite segmentation.

### User Interfaces

- Streamlit for ML/analytics.
- React for production operations/public presentation.

### Deployment

Local Docker first, then cloud deployment.

## 4. Quantified Outcome Targets

| Outcome | Target |
|---|---:|
| Flood-event recall | >= 90% |
| F1 | >= 0.85 |
| Prediction lead time | 30–120 min |
| Water-level MAE | <= 0.20 m where feasible |
| Prediction API latency | < 500 ms |
| Ingestion-to-inference automation | End to end |
| Stale/missing sensor detection | Automated |
| Experiment tracking | Reproducible |
| Critical-path test coverage | >= 80% target |

Do not present targets as achieved portfolio numbers.

## 5. Success Criteria

The project is portfolio-ready when it can demonstrate:

1. a documented Penang dataset;
2. leakage-safe temporal validation;
3. multiple baseline/model comparisons;
4. reproducible experiments;
5. live or replayed streaming inference;
6. FastAPI serving;
7. Streamlit analytics;
8. operational monitoring;
9. clear limitations;
10. verified measured results.
