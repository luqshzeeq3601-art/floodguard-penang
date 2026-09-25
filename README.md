# FloodGuard Penang

Production-grade machine learning flood early-warning and flood-intelligence platform focused on Pulau Pinang, Malaysia.

## Project Goal

Build an end-to-end ML engineering system that combines historical and live environmental data to:

- predict flood risk 30, 60, and 120 minutes ahead;
- forecast future river/water level where data supports it;
- monitor live rainfall and water-level stations;
- explain why the model raised a warning;
- expose predictions through FastAPI;
- provide an internal Streamlit ML/analytics workspace;
- provide a polished React/TypeScript operational interface;
- monitor data quality, model drift, latency, and failures;
- demonstrate production ML, data engineering, MLOps, GIS, backend, frontend, CI/CD, and observability skills.

## Core Principle

This is not a notebook-only classifier.

The project should demonstrate the full path:

```text
Historical data
    ↓
Data validation
    ↓
Feature engineering
    ↓
Temporal ML evaluation
    ↓
Model registry
    ↓
Production serving
    ↓
Live data ingestion
    ↓
Real-time inference
    ↓
Monitoring + dashboard + alerts
```

## Primary Users

- ML engineer / data analyst using Streamlit.
- Operations or monitoring user using React.
- Developer/maintainer using FastAPI and observability tooling.
- Portfolio reviewer/recruiter evaluating ML engineering depth.

## Main Documentation

Read in this order:

1. `docs/00_PROJECT_BRIEF.md`
2. `docs/01_PROBLEM_OBJECTIVES_SCOPE.md`
3. `docs/02_ARCHITECTURE.md`
4. `docs/03_DATA_PLAN.md`
5. `docs/05_METHODOLOGY.md`
6. `docs/06_MODELING_PLAN.md`
7. `docs/07_MLOPS_PLAN.md`
8. `docs/08_STREAMLIT_PLAN.md`
9. `docs/12_ROADMAP.md`
10. `AGENTS.md`

Architecture decisions and their trade-offs: `docs/decisions/README.md`.

## Data Sources and Disclaimer

FloodGuard Penang is an independent, non-official research and portfolio project. It is not
affiliated with, endorsed by, or a service of JPS (Department of Irrigation and Drainage
Malaysia), MET Malaysia, NADMA or the Penang State Government. Its risk estimates are experimental
model outputs, not official flood forecasts or warnings. Do not use it for safety decisions.

Source terms differ: JPS Public Infobanjir content needs JPS's prior written consent for copying or
redistribution (permission not yet obtained); Penang GeoHub layers carry no licence; the
data.gov.my Weather API (MET Malaysia data) is CC BY 4.0. Third-party raw captures are therefore
kept out of the repository. Details, per-use status and attribution: `docs/DATA_LICENSING_AND_ACCESS.md`.

Weather forecast and warning data: MET Malaysia, via the data.gov.my Weather API, CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/); filtered to Pulau Pinang by FloodGuard.

## Development Setup

Requires Python 3.11+ (pinned to 3.11 in `.python-version` for ML wheel compatibility).

```bash
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/python -m pip install -e . --group dev
.venv/Scripts/python scripts/verify_environment.py
cp .env.example .env
```

`.env` is git-ignored; see `.env.example` for which variables are active now versus planned. `--group` needs pip >= 25.1. Optional extras are installed when their phase starts, e.g. `pip install -e ".[ml]"`.

Local database (PostgreSQL 17 + PostGIS 3.5, bound to `127.0.0.1`):

```bash
docker compose up -d --wait
docker compose exec db psql -U floodguard -d floodguard -c "SELECT postgis_full_version();"
docker compose stop
```

`docker compose down` removes the container but keeps the `floodguard-pgdata` volume; `down -v` deletes the data.

Checks:

```bash
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m mypy
.venv/Scripts/python -m pytest --cov
```

## Claude Code

Claude Code should start by reading:

```text
CLAUDE.md
AGENTS.md
.claude/rules/skill-routing.md
```

Then load only the task-specific rules, agents, and skills required for the current task.

## Important Metric Rule

Engineering targets are not achievements.

Example targets:

- flood-event recall >= 90%;
- F1 >= 0.85;
- API prediction latency < 500 ms;
- water-level MAE <= 0.20 m where feasible.

Never put those numbers in a resume as achieved results until a reproducible evaluation run proves them.
