---
name: evaluate-model
description: Evaluate FloodGuard flood-risk or water-level models with temporal, operational, and error-analysis checks.
---

# Evaluate Model

## Classification

Report:

- recall;
- precision;
- F1;
- PR-AUC;
- false-negative rate;
- confusion matrix;
- calibration;
- inference latency.

Break down by:

- horizon;
- station;
- time period;
- data-quality state where useful.

## Forecasting

Report:

- MAE;
- RMSE;
- horizon;
- station.

Always compare to baseline.

Explicitly analyze false negatives.
