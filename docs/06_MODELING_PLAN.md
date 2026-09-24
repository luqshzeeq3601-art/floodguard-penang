# Modeling Plan

## 1. Model Tasks

### Task A — Flood-Risk Classification

Separate horizon models or a well-designed multi-horizon approach for:

- 30 min;
- 60 min;
- 120 min.

Start with separate models because evaluation and calibration are easier to interpret.

### Task B — Water-Level Forecasting

Forecast:

- t+30;
- t+60;
- t+120.

Use only stations with sufficient history and timestamp consistency.

## 2. Candidate Feature Groups

### Rainfall

- 15m / 1h / 3h / 6h / 24h accumulations;
- 72h antecedent rainfall;
- intensity;
- recent maximum.

### Water level

- current level;
- deltas;
- rise rate;
- rolling trend;
- threshold distance.

### Weather

- forecast rainfall;
- weather warnings;
- temperature/humidity if stable and useful.

### Context

- station;
- district;
- basin;
- month;
- hour;
- seasonal indicator.

## 3. Baseline Matrix

| Model | Purpose |
|---|---|
| Threshold/rule | Operational sanity baseline |
| Persistence | Forecast sanity baseline |
| Logistic Regression | Interpretable ML baseline |
| Random Forest | Nonlinear baseline |
| XGBoost/LightGBM | Main tabular candidate |
| LSTM/GRU | Sequence candidate only if justified |
| Statsmodels model | Forecast baseline/diagnostics |
| TimesFM | Optional forecasting benchmark |

## 4. Classification Metrics

Prioritize:

1. recall;
2. false-negative rate;
3. PR-AUC;
4. F1;
5. precision;
6. calibration;
7. ROC-AUC;
8. latency.

Why:

Flood events may be imbalanced, making accuracy misleading.

## 5. Threshold Selection

Do not default to 0.5.

Choose operating thresholds using validation data based on:

- recall requirement;
- false-negative tolerance;
- false-positive burden;
- calibration.

Keep threshold selection separate for each horizon if necessary.

## 6. Regression Metrics

Use:

- MAE;
- RMSE;
- horizon-specific error;
- station-specific error.

Consider a naive persistence forecast as the minimum baseline.

## 7. Hyperparameter Tuning

Tune only after:

- data contract stable;
- leakage tests pass;
- baseline established;
- temporal validation fixed.

Record every tuning run in MLflow.

## 8. Model Selection

The production candidate should optimize the operational trade-off, not leaderboard accuracy.

Evaluate:

- recall;
- false negatives;
- PR-AUC;
- stability;
- calibration;
- latency;
- feature availability;
- robustness to missing data;
- operational maintenance.

## 9. SHAP

Provide:

- global feature summary;
- per-event explanation;
- station-level analysis.

Do not expose raw SHAP plots without plain-language interpretation in Streamlit.

## 10. Model Artifacts

Each released model should have:

```text
model artifact
preprocessing artifact/pipeline
feature schema
threshold configuration
training data version
feature version
code commit
metrics
model card
```
