# System Architecture

## 1. High-Level Architecture

```text
                     OFFLINE / TRAINING
┌─────────────────────────────────────────────────────────────┐
│ JPS historical rainfall + water level                      │
│ METMalaysia / historical weather                           │
│ GIS / historical flood context                             │
└───────────────────────┬─────────────────────────────────────┘
                        ↓
                 Raw data storage
                        ↓
                Validation / quality
                        ↓
                 Feature engineering
                        ↓
             Temporal train / validation
                        ↓
        Baseline → RF → XGBoost → sequence model
                        ↓
                 Model evaluation
                        ↓
               MLflow model registry
                        ↓
                 Production model
└───────────────────────┬─────────────────────────────────────┘
                        │
                        │
                     ONLINE
                        │
┌───────────────────────▼─────────────────────────────────────┐
│ Live JPS / METMalaysia observations                        │
└───────────────────────┬─────────────────────────────────────┘
                        ↓
             Polling / streaming ingestion
                        ↓
                   Validation
                        ↓
                Online features
                        ↓
                Model inference
                        ↓
                      FastAPI
                        ↓
               PostgreSQL / PostGIS
             ┌──────────┼──────────┐
             ↓          ↓          ↓
         Streamlit     React      Alerts
             │          │          │
             └──────────┴──────────┘
                        ↓
           Monitoring / drift / telemetry
```

## 2. Offline Components

### Ingestion

Responsibilities:

- download/import historical observations;
- persist raw source files;
- preserve source metadata;
- normalize station catalog.

### Validation

Checks:

- schema;
- units;
- timestamp order;
- duplicates;
- impossible values;
- missingness;
- station IDs;
- coordinate validity.

### Feature Pipeline

Produces reusable deterministic features.

Do not keep production feature logic only inside notebooks.

### Training

Candidate models use the same:

- dataset version;
- feature version;
- temporal split;
- evaluation protocol.

### Registry

MLflow tracks experiments and model versions.

## 3. Online Components

### Live Ingestion

Start with scheduled polling.

Move to Kafka/MQTT only if measured requirements justify it.

### Online Validation

Reject or flag:

- malformed data;
- stale observations;
- duplicate observations;
- invalid ranges;
- unknown stations.

### Inference

Output should include:

```json
{
  "station_id": "...",
  "observation_time": "...",
  "prediction_time": "...",
  "horizon_minutes": 60,
  "risk_probability": 0.82,
  "risk_level": "warning",
  "predicted_water_level_m": 3.21,
  "model_version": "...",
  "data_quality": "valid"
}
```

## 4. FastAPI

FastAPI is the shared service layer.

Streamlit and React should consume FastAPI/service interfaces instead of duplicating model code.

## 5. Streamlit

Internal engineering and analytics interface.

Primary users:

- ML engineer;
- analyst;
- project reviewer.

## 6. React

Operational/public-facing interface.

Primary focus:

- fast station scanning;
- map;
- risk;
- trends;
- alerts;
- clear distinction between observations and predictions.

## 7. Database Domains

Suggested conceptual tables:

```text
stations
observations_rainfall
observations_water_level
weather_observations
weather_forecasts
data_quality_events
model_versions
predictions
alerts
flood_events
```

PostGIS stores station geometry and relevant spatial layers.

## 8. Monitoring

Use separate concerns:

- operational monitoring;
- data quality;
- model quality.

Do not conflate them.
