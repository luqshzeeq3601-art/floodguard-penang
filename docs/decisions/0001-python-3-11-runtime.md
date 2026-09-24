# ADR-0001: Python 3.11 as the Project Runtime

## Status

Accepted

## Context

The development machine has Python 3.10, 3.11 and 3.14 installed. FloodGuard's planned stack (pandas, scikit-learn, XGBoost/LightGBM, SHAP, MLflow, GeoPandas, FastAPI, Streamlit) is compiled-extension heavy, and wheel availability lags on the newest Python releases.

## Decision

- Supported runtime: Python `>=3.11` (`requires-python` in `pyproject.toml`).
- Development runtime pinned to 3.11 via `.python-version`; the local `.venv` runs 3.11.9.
- `scripts/verify_environment.py` fails fast on Python < 3.11 or outside a virtual environment.
- Raising the pinned version requires installing and testing the actual dependency stack on the new version first.

## Alternatives

- **Python 3.12/3.13/3.14:** newer language features and performance; wheel coverage for the planned ML/GIS stack is less certain, especially on 3.14.
- **Unpinned runtime:** less setup friction; results and dependency resolution can differ between machines.

## Consequences

Positive:

- broadest mature wheel support for the planned ML/data/GIS libraries;
- reproducible local environment.

Trade-off:

- misses newer language features and interpreter speedups;
- the pin needs periodic review as 3.11 approaches end of life.

## Validation

`scripts/verify_environment.py` passes in `.venv` (3.11.9) and fails on system 3.14 (no venv) and 3.10. Revisit when a phase adds dependencies that support a newer Python, or before 3.11 end of life.

## Date

2026-09-24
