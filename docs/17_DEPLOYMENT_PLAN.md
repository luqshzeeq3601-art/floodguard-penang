# Deployment Plan

## 1. Environments

Suggested:

- local;
- test;
- staging;
- production/demo.

## 2. Local

Use Docker Compose for:

- PostgreSQL/PostGIS;
- FastAPI;
- Streamlit;
- React;
- MLflow;
- Prometheus/Grafana as needed.

Do not add every service on day one.

Current baseline (`compose.yaml`): a single `db` service, `postgis/postgis:17-3.5`, with the `floodguard-pgdata` named volume, a `pg_isready` health check, `restart: unless-stopped`, and the host port bound to `127.0.0.1` (`FLOODGUARD_POSTGRES_PORT`, default 5432). Credentials come from environment interpolation with development-only defaults. The PostGIS image creates the `postgis` extensions in the default database on first start; no application tables or migrations exist yet. Other services are added when their phase starts.

## 3. Container Boundaries

Possible containers:

- api;
- streamlit;
- frontend;
- ingestion worker;
- PostgreSQL/PostGIS;
- MLflow;
- monitoring.

Training may run separately from the serving stack.

## 4. Cloud

Choose one cloud when deployment phase begins.

Demonstrate:

- managed compute or container service;
- managed PostgreSQL if practical;
- object storage for artifacts;
- secrets management;
- logs/metrics.

Do not add Kubernetes only for resume keywords.

Kubernetes is optional after Docker deployment is stable.

## 5. Release Process

```text
merge
 ↓
CI
 ↓
Docker build
 ↓
staging deploy
 ↓
health + smoke
 ↓
model/API compatibility
 ↓
production/demo deploy
```

## 6. Model Deployment

Separate application deployment from model promotion where practical.

A new API build should not silently change the production model.

## 7. Rollback

Support:

- application rollback;
- model rollback;
- database migration rollback strategy where safe.
