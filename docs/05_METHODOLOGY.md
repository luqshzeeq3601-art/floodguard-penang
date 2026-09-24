# Methodology

## 1. Methodological Approach

Use an ML engineering lifecycle combining:

- problem framing;
- data understanding;
- data engineering;
- temporal feature engineering;
- baseline modelling;
- temporal validation;
- model interpretation;
- deployment;
- monitoring.

## 2. Phase A — Data Understanding

Analyze:

- station coverage;
- observation intervals;
- historical depth;
- missingness;
- duplicates;
- extreme values;
- sensor outages;
- rainfall/water-level relationships;
- flood/threshold event frequency;
- seasonal behavior.

Outputs:

- station inventory;
- data-quality report;
- EDA notebook/report;
- initial event definition.

## 3. Phase B — Data Preparation

Steps:

1. preserve raw source;
2. standardize timestamps;
3. map station IDs;
4. validate units;
5. remove exact duplicates;
6. flag invalid readings;
7. align rainfall and water level;
8. create backward-looking features;
9. construct versioned targets.

## 4. Phase C — Temporal Validation

Do not use naive random train/test split.

Preferred design:

```text
earlier period        later period       latest period
TRAIN                  VALIDATION         TEST
```

For model selection, consider rolling validation:

```text
Fold 1: train ───── validate
Fold 2: train ─────────── validate
Fold 3: train ───────────────── validate
```

Final test remains untouched until model selection is complete.

## 5. Phase D — Baseline Models

Required baselines:

### Rule/persistence

Examples:

- current threshold state;
- water-level persistence;
- simple rise-rate extrapolation.

### Logistic Regression

Provides:

- interpretable baseline;
- probability baseline;
- sanity check against complex models.

## 6. Phase E — Candidate Models

### Random Forest

Useful nonlinear baseline.

### XGBoost/LightGBM

Likely strong candidate for tabular, lagged environmental features.

### LSTM/GRU

Only when:

- sufficient sequence history exists;
- model improves out-of-time performance;
- operational complexity is justified.

### Statistical / foundation forecast benchmark

For water-level forecasting:

- persistence;
- ARIMA/ETS where appropriate;
- gradient boosting with lags;
- optional TimesFM benchmark.

## 7. Phase F — Explainability

Use:

- global feature importance;
- SHAP summary;
- station/event-level SHAP;
- calibration plots.

Explain contribution, not causality.

## 8. Phase G — Error Analysis

Analyze separately:

- false negatives;
- false positives;
- performance by station;
- performance by horizon;
- performance by season;
- high-rainfall events;
- sensor-quality conditions;
- unseen/rare conditions.

For flood warning, false negatives deserve explicit investigation.

## 9. Phase H — Production Validation

Before production/replay release:

- model artifact loads;
- input schema matches;
- feature pipeline matches training;
- latency acceptable;
- prediction version recorded;
- missing sensor behavior defined;
- fallback behavior defined;
- alert thresholds versioned.

## 10. Phase I — Monitoring

Continuously track:

- data freshness;
- distribution drift;
- prediction distribution;
- latency;
- errors;
- delayed labels;
- realized event performance.

Retraining should be triggered by evidence, not automatically by any drift alert.
