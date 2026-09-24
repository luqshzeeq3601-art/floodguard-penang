# Implementation Roadmap

## Phase 0 — Project Foundation

Deliverables:

- repository structure;
- Claude instructions;
- dependency management;
- test/lint/typecheck baseline;
- Docker baseline;
- ADR folder.

Gate:

- project installs;
- tests run;
- lint works.

## Phase 1 — Data Discovery

Deliverables:

- Penang station inventory;
- source access notes;
- historical coverage report;
- live-access proof;
- data licensing/access notes.

Gate:

- at least one reproducible rainfall source;
- at least one reproducible water-level source.

## Phase 2 — Historical Data Engineering

Deliverables:

- ingestion scripts;
- canonical station IDs;
- raw snapshot storage;
- validation rules;
- processed tables.

Gate:

- deterministic pipeline;
- quality report.

## Phase 3 — EDA + Label Definition

Deliverables:

- EDA;
- event analysis;
- label specification;
- class balance;
- temporal split plan.

Gate:

- target definition frozen/versioned.

## Phase 4 — Feature Engineering

Deliverables:

- backward-looking rainfall features;
- water-level deltas/rise rate;
- contextual features;
- feature tests.

Gate:

- leakage tests pass.

## Phase 5 — Flood Classification

Deliverables:

- rule baseline;
- Logistic Regression;
- Random Forest;
- XGBoost/LightGBM;
- out-of-time comparison;
- error analysis.

Gate:

- candidate beats meaningful baseline operationally.

## Phase 6 — Water-Level Forecasting

Deliverables:

- persistence;
- statistical/ML baseline;
- optional sequence model;
- horizon-specific evaluation.

Gate:

- result provides value over persistence.

## Phase 7 — MLOps

Deliverables:

- MLflow;
- dataset/feature lineage;
- model registry;
- model card;
- promotion rules.

Gate:

- selected model reproducible from recorded run.

## Phase 8 — Backend + Database

Deliverables:

- PostgreSQL/PostGIS;
- FastAPI;
- prediction endpoint;
- station endpoint;
- health/readiness;
- integration tests.

Gate:

- model can be served reproducibly.

## Phase 9 — Streamlit

Deliverables:

- all planned analytics pages;
- API/service integration;
- SHAP;
- quality/drift views.

Gate:

- user can inspect data, predictions, and model quality without a notebook.

## Phase 10 — Live Pipeline

Deliverables:

- live polling;
- deduplication;
- freshness checks;
- real-time inference;
- persistence;
- replay mode.

Gate:

- controlled event replay works E2E.

## Phase 11 — React + Alerts

Deliverables:

- operational map;
- station detail;
- risk display;
- alert history;
- external alert integration where appropriate.

Gate:

- E2E workflow passes.

## Phase 12 — Monitoring + Deployment

Deliverables:

- Prometheus;
- Grafana;
- drift checks;
- CI/CD;
- cloud deployment;
- runbook.

Gate:

- production-like failure scenarios are observable.

## Phase 13 — Optional Satellite CV

Deliverables:

- Sentinel-1 preprocessing;
- flood mask dataset;
- segmentation baseline;
- U-Net candidate;
- spatial evaluation;
- map overlay.

Do this only after the core system is strong.
