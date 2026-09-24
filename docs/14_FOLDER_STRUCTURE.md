# Recommended Repository Structure

```text
floodguard-penang/
├── CLAUDE.md
├── AGENTS.md
├── README.md
├── TASKS.md
├── pyproject.toml
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .claudeignore
│
├── .claude/
│   ├── settings.json
│   ├── rules/
│   ├── agents/
│   └── skills/
│
├── config/
│   ├── development.yaml
│   ├── production.yaml
│   ├── logging.yaml
│   └── thresholds.yaml
│
├── data/
│   ├── README.md
│   ├── raw/
│   │   ├── jps/
│   │   ├── metmalaysia/
│   │   └── gis/
│   ├── interim/
│   ├── processed/
│   └── external/
│
├── src/
│   └── floodguard/
│       ├── __init__.py
│       ├── ingestion/
│       │   ├── jps.py
│       │   ├── metmalaysia.py
│       │   ├── scheduler.py
│       │   └── schemas.py
│       ├── validation/
│       │   ├── data_quality.py
│       │   ├── rules.py
│       │   └── schemas.py
│       ├── preprocessing/
│       │   ├── cleaning.py
│       │   ├── alignment.py
│       │   └── missing_values.py
│       ├── features/
│       │   ├── rainfall.py
│       │   ├── water_level.py
│       │   ├── temporal.py
│       │   ├── weather.py
│       │   └── build_features.py
│       ├── models/
│       │   ├── baseline.py
│       │   ├── random_forest.py
│       │   ├── xgboost.py
│       │   ├── lstm.py
│       │   ├── registry.py
│       │   └── predict.py
│       ├── training/
│       │   ├── train.py
│       │   ├── evaluate.py
│       │   ├── tune.py
│       │   └── experiment.py
│       ├── streaming/
│       │   ├── producer.py
│       │   ├── consumer.py
│       │   └── events.py
│       ├── monitoring/
│       │   ├── data_drift.py
│       │   ├── model_drift.py
│       │   ├── performance.py
│       │   └── alerts.py
│       ├── database/
│       │   ├── models.py
│       │   ├── repository.py
│       │   └── session.py
│       ├── api/
│       │   ├── main.py
│       │   ├── schemas.py
│       │   ├── dependencies.py
│       │   └── routes/
│       │       ├── health.py
│       │       ├── predictions.py
│       │       ├── observations.py
│       │       ├── stations.py
│       │       └── monitoring.py
│       └── utils/
│
├── streamlit_app/
│   ├── app.py
│   ├── pages/
│   ├── components/
│   ├── services/
│   ├── charts/
│   └── utils/
│
├── frontend/
│   ├── package.json
│   └── src/
│       ├── components/
│       ├── features/
│       ├── pages/
│       ├── services/
│       ├── hooks/
│       └── types/
│
├── pipelines/
│   ├── ingestion_pipeline.py
│   ├── training_pipeline.py
│   ├── inference_pipeline.py
│   └── monitoring_pipeline.py
│
├── mlops/
│   ├── mlflow/
│   ├── dvc/
│   ├── evidently/
│   └── model_cards/
│
├── infrastructure/
│   ├── docker/
│   ├── kubernetes/
│   ├── prometheus/
│   └── grafana/
│
├── notebooks/
│   ├── 01_data_understanding.ipynb
│   ├── 02_eda.ipynb
│   ├── 03_feature_engineering.ipynb
│   └── 04_model_experiments.ipynb
│
├── scripts/
│   ├── download_data.py
│   ├── seed_database.py
│   ├── train_model.py
│   └── verify_environment.py
│
├── tests/
│   ├── unit/
│   ├── data/
│   ├── models/
│   ├── api/
│   ├── integration/
│   └── e2e/
│
├── docs/
│   ├── decisions/
│   └── templates/
│
└── .github/
    └── workflows/
        ├── ci.yml
        ├── model-tests.yml
        └── docker.yml
```

## Current State (Phase 0)

Confirmed layout: the tree above is the target. Directories are created when the phase that needs them starts, not up front as empty scaffolding.

Present now:

- `src/floodguard/` (package root, `src` layout);
- `.env.example` (environment contract; local `.env` is git-ignored);
- `compose.yaml` (local PostgreSQL/PostGIS only; replaces the planned `docker-compose.yml` name);
- `pyproject.toml` (packaging, dependencies, Ruff/mypy/pytest/coverage config);
- `tests/` (`test_package.py` smoke tests);
- `scripts/verify_environment.py`, `.python-version` (3.11), local `.venv/` (git-ignored);
- `data/{raw/{jps,metmalaysia,gis},interim,processed,external}/` with `data/README.md`;
- `docs/decisions/` (ADR-0001 to ADR-0010, index in `README.md`), `docs/templates/`;
- `.claude/`, `.gitignore`, `.claudeignore`, `.graphifyignore`.

Deferred until justified by evidence: `src/floodguard/streaming/` (Kafka/MQTT, Phase 10 decision), `infrastructure/kubernetes/`, `models/lstm.py` (only if sequence volume and validation justify it).

## Structure Rules

- notebooks explore; production code lives in `src/`;
- raw data is immutable;
- Streamlit uses shared services;
- React uses API contracts;
- model artifacts are versioned outside normal source code;
- tests mirror critical production modules.
