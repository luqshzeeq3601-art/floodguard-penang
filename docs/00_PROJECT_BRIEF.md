# Project Brief — FloodGuard Penang

## 1. One-Sentence Idea

Build a production-grade AI flood early-warning platform for Penang that combines historical and live rainfall, river-level, weather, and geospatial data to predict flood risk before dangerous conditions are reached.

## 2. Why This Project

A simple flood classifier is not enough for an AI/ML Engineer portfolio.

FloodGuard Penang is designed to demonstrate:

- machine learning;
- time-series feature engineering;
- data engineering;
- real-time inference;
- GIS;
- MLOps;
- FastAPI;
- PostgreSQL/PostGIS;
- Streamlit;
- React/TypeScript;
- Docker;
- CI/CD;
- monitoring;
- explainable AI.

## 3. Core System

```text
Historical JPS / MET data
        ↓
Data validation + cleaning
        ↓
Feature engineering
        ↓
Temporal model training
        ↓
MLflow model registry
        ↓
Production model
        ↓
──────────────────────────
Live JPS / MET data
        ↓
Live ingestion
        ↓
Validation
        ↓
Feature pipeline
        ↓
Production inference
        ↓
FastAPI + PostgreSQL/PostGIS
        ↓
Streamlit / React / Alerts
```

## 4. Primary ML Outputs

For each relevant Penang station:

- flood-risk probability;
- risk category;
- prediction horizon:
  - +30 min;
  - +60 min;
  - +120 min;
- future water-level estimate where supported;
- key contributing features;
- model version;
- data-quality status.

## 5. Intended Portfolio Story

The project should communicate:

> I did not only train a model. I designed the data pipeline, prevented temporal leakage, compared baselines, productionized inference, added explainability, monitored drift/data quality, and built both an internal ML interface and an operational application.

## 6. Suggested Project Name

**FloodGuard Penang — AI-Powered Flood Early Warning and Flood Intelligence Platform**

## 7. Main Technology Stack

| Layer | Technology |
|---|---|
| Language | Python |
| Data | Pandas, NumPy |
| Classical ML | scikit-learn, XGBoost/LightGBM |
| Deep learning | PyTorch only when justified |
| Explainability | SHAP |
| Database | PostgreSQL + PostGIS |
| API | FastAPI |
| Internal ML UI | Streamlit |
| Operational UI | React + TypeScript |
| Maps | MapLibre / Leaflet / Plotly / Folium as appropriate |
| MLOps | MLflow + DVC |
| Monitoring | Evidently + Prometheus + Grafana |
| Streaming | Scheduled polling first; Kafka/MQTT if justified |
| Deployment | Docker + cloud |
| CI/CD | GitHub Actions |
| Testing | pytest, Ruff, mypy |

## 8. Non-Goals

Initial version does not claim to:

- replace official JPS warnings;
- operate as an emergency-dispatch system;
- provide legally authoritative warnings;
- predict nationwide Malaysian flooding;
- infer precise flood extent from station-level classification alone.
