# ADR-0010: MLflow for Experiment/Model Lineage, DVC Where Useful

## Status

Accepted

## Context

Every meaningful ML run must record dataset version, feature version, code commit, model, hyperparameters, seed, validation design, metrics, and artifacts (`AGENTS.md` §15). Model promotion needs a traceable registry.

## Decision

Responsibilities are split:

| Concern | Tool |
|---|---|
| Source code | Git |
| Experiments, metrics, model artifacts, registry | MLflow |
| Versioned datasets / model-ready tables | DVC, where it materially improves reproducibility |
| Raw data | Immutable files, referenced by version; never committed to Git |

MLflow and DVC are deferred to the MLOps phase (Phase 7) and are not installed yet. See `docs/07_MLOPS_PLAN.md`.

## Alternatives

- **Weights & Biases / other hosted trackers:** polished UI; external hosted dependency and account requirements.
- **Manual logging (CSV/JSON):** no infrastructure; error-prone and no registry.
- **Git LFS for data:** familiar workflow; weaker pipeline and dataset lineage than DVC.

## Consequences

Positive:

- each model version is traceable to data, features, code, and validation;
- promotion gates can compare candidates against baselines consistently.

Trade-off:

- an MLflow tracking service and artifact store to run;
- DVC adds a remote-storage setup and learning curve, so it is used only where it pays off.

## Validation

Phase 7 verifies that a run can be reproduced from its recorded dataset version, feature version, commit, and seed.

## Date

2026-09-24
