# ADR-0002: `src/` Layout with `pyproject.toml` and Hatchling

## Status

Accepted

## Context

FloodGuard's production code is shared by pipelines, FastAPI, Streamlit, and tests. Code must be importable the same way in development, CI, and containers.

## Decision

- Package lives in `src/floodguard/`, marked typed with `py.typed`.
- All packaging and tool configuration (Ruff, mypy, pytest, coverage) is in `pyproject.toml`.
- Build backend: Hatchling; version read from `floodguard.__version__`.
- Development install: `pip install -e . --group dev` (PEP 735 dependency group). Optional extras (e.g. `[ml]`) are added per phase.

## Alternatives

- **Flat layout (`floodguard/` at repo root):** simpler paths; the package can be imported from the working directory without being installed, which can hide packaging mistakes.
- **setuptools:** mature and widely used; needs more configuration for the same result here.
- **Poetry:** integrated locking and environment management; adds a tool-specific workflow and its own dependency metadata format.

## Consequences

Positive:

- tests import the installed package, matching production behavior;
- one configuration file for packaging and tooling.

Trade-off:

- no lockfile yet; one is needed before CI/Docker builds are reproducible;
- `--group` requires pip >= 25.1.

## Validation

Editable install succeeds, `floodguard` imports from outside the repository and resolves to `src/`, and the smoke tests in `tests/test_package.py` pass.

## Date

2026-09-24
