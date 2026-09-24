# MLOps Plan

## 1. Goals

Make model development:

- reproducible;
- traceable;
- comparable;
- deployable;
- monitorable;
- reversible.

## 2. MLflow

Track:

- experiment name;
- dataset version;
- feature version;
- code commit;
- model;
- hyperparameters;
- random seed;
- temporal validation details;
- classification metrics;
- forecasting metrics;
- artifacts.

## 3. DVC / Data Lineage

Use DVC when practical to version:

- processed training datasets;
- selected intermediate artifacts;
- model-ready tables.

Do not commit huge raw files to Git.

## 4. Model Registry States

Suggested stages:

```text
candidate
validated
staging
production
archived
```

Promotion is a gated engineering decision.

## 5. Promotion Gate

A candidate must:

- beat or match the relevant baseline;
- meet acceptable recall/false-negative behavior;
- pass leakage checks;
- pass model loading test;
- pass schema compatibility;
- meet latency requirement;
- have a model card;
- have reproducible run metadata.

## 6. CI

CI should include:

- Ruff;
- mypy where relevant;
- pytest;
- data schema tests using fixtures;
- model artifact smoke test;
- API tests;
- Docker build.

Do not run expensive full retraining on every commit unless cost is acceptable.

## 7. Training Pipeline

```text
dataset version
    ↓
quality gate
    ↓
feature build
    ↓
temporal split
    ↓
training
    ↓
evaluation
    ↓
baseline comparison
    ↓
MLflow logging
    ↓
candidate registration
```

## 8. Inference Versioning

Every stored prediction should include:

- model version;
- feature version;
- input observation timestamp;
- inference timestamp;
- horizon;
- threshold configuration.

## 9. Drift

Monitor:

- feature distribution;
- missingness;
- station activity;
- prediction distribution.

A drift alert creates an investigation.

It does not automatically trigger model replacement.

## 10. Rollback

Keep previous validated model available.

Rollback conditions may include:

- artifact loading failure;
- latency regression;
- schema incompatibility;
- severe prediction behavior regression.

## 11. Reproducibility

A reviewer should be able to answer:

> Which code, data, features, parameters, and validation produced this model?

If not, the model is not release-ready.
