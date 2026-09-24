# Streamlit Plan

## 1. Purpose

Streamlit is the internal ML engineering and analytics interface.

It is used for:

- rapid model experimentation;
- EDA;
- feature inspection;
- live station monitoring;
- prediction testing;
- SHAP explanations;
- model comparison;
- data-quality analysis;
- model/data drift analysis.

It does not replace the production React interface.

## 2. Proposed Structure

```text
streamlit_app/
├── app.py
├── pages/
│   ├── 01_Overview.py
│   ├── 02_Live_Monitoring.py
│   ├── 03_Flood_Prediction.py
│   ├── 04_Station_Analysis.py
│   ├── 05_Model_Performance.py
│   ├── 06_SHAP_Explainability.py
│   ├── 07_Data_Quality.py
│   └── 08_Model_Drift.py
├── components/
├── services/
├── charts/
└── utils/
```

## 3. Overview

Show:

- station coverage;
- latest data freshness;
- current risk distribution;
- model version;
- ingestion health.

Avoid decorative KPIs.

## 4. Live Monitoring

Show:

- map;
- latest rainfall;
- latest water level;
- recent trend;
- station freshness;
- quality flag;
- current prediction.

Clearly distinguish:

- observed;
- forecast;
- ML prediction.

## 5. Flood Prediction

Allow controlled testing:

- station selection;
- timestamp/event selection;
- model version;
- horizon.

Show:

- probability;
- threshold;
- risk category;
- explanation;
- input quality.

## 6. Station Analysis

Show:

- historical rainfall;
- water-level trend;
- event markers;
- missing-data periods;
- prediction history.

## 7. Model Performance

Show:

- recall;
- precision;
- F1;
- PR-AUC;
- confusion matrix;
- performance by horizon;
- performance by station;
- false negatives.

## 8. SHAP Explainability

Show:

- global SHAP summary;
- local event explanation;
- plain-language explanation.

Do not frame SHAP as causal.

## 9. Data Quality

Show:

- missing observations;
- stale stations;
- invalid range;
- duplicates;
- schema issues;
- recent ingestion delay.

## 10. Model Drift

Show:

- feature drift;
- prediction distribution;
- confidence changes;
- label-based performance once available.

## 11. Architecture Rule

Streamlit should use shared services/FastAPI.

Do not duplicate:

- feature engineering;
- model loading;
- threshold logic;
- database business logic.

## 12. Performance

Use caching only when:

- cache key is clear;
- stale data risk is acceptable;
- the page visibly communicates data timestamp.
