# ADR-0006: Simple-to-Complex Model Progression

## Status

Accepted

## Context

Flood-risk classification on lagged rainfall/water-level features is a tabular problem with a small number of positive events. Added model complexity has to earn its place in recall, false negatives, calibration, and operational cost.

## Decision

Build models in this order, each compared against the ones before it on the same dataset version, features, and temporal validation:

```text
rule/persistence baseline
        ↓
Logistic Regression
        ↓
Random Forest
        ↓
XGBoost / LightGBM
        ↓
LSTM / GRU only if justified
```

- A sequence model is considered only if data volume and validation show a measured gain over the tabular models.
- Deep learning is not added for portfolio appearance.
- Optional forecasting benchmarks such as TimesFM are a separate, later decision and are not part of this progression.

See `docs/06_MODELING_PLAN.md` and `AGENTS.md` §6.

## Alternatives

- **Start with gradient boosting or deep learning:** may reach a strong score faster; gives no baseline to show the complexity is needed.
- **Stop at a rule baseline:** simplest to operate; likely misses achievable recall.

## Consequences

Positive:

- every added model has a measured reason;
- simpler models are easier to serve, explain, and monitor.

Trade-off:

- more experiments before reaching the strongest model;
- the chosen production model may be less sophisticated than possible if gains are small.

## Validation

Each stage's results are recorded with dataset version, validation periods, and metrics (recall, false-negative rate, PR-AUC, F1, calibration, latency). XGBoost vs LightGBM and any LSTM/GRU adoption get their own ADRs when evidence exists.

## Date

2026-09-24
