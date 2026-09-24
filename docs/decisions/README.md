# Architecture Decision Records

Each ADR records one decision, its alternatives, and its trade-offs. Copy `0000_TEMPLATE.md`, use the next number, and keep the status current (`Proposed`, `Accepted`, `Superseded by ADR-NNNN`).

Record only decisions that have been made. Choices that need later evidence (XGBoost vs LightGBM, LSTM/GRU, TimesFM, Kafka vs MQTT, cloud provider, alert channel, upstream access method, operating threshold, deployment strategy) get an ADR when that evidence exists.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-python-3-11-runtime.md) | Python 3.11 as the project runtime | Accepted |
| [0002](0002-src-layout-hatchling.md) | `src/` layout with `pyproject.toml` and Hatchling | Accepted |
| [0003](0003-postgresql-postgis.md) | PostgreSQL + PostGIS as the operational database | Accepted |
| [0004](0004-historical-training-live-inference.md) | Historical training with live inference | Accepted |
| [0005](0005-temporal-validation.md) | Temporal validation instead of random splitting | Accepted |
| [0006](0006-simple-to-complex-models.md) | Simple-to-complex model progression | Accepted |
| [0007](0007-fastapi-service-boundary.md) | FastAPI as the shared service boundary | Accepted |
| [0008](0008-streamlit-react-separation.md) | Separate Streamlit and React responsibilities | Accepted |
| [0009](0009-polling-before-streaming-broker.md) | Scheduled polling before Kafka/MQTT | Accepted |
| [0010](0010-mlflow-data-lineage.md) | MLflow for lineage, DVC where useful | Accepted |
