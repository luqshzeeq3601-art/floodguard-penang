# ADR-0004: Historical Training with Live Inference

## Status

Accepted

## Context

Flood events are rare. A model needs years of labeled history to learn from and to be evaluated honestly, but its operational value comes from predicting on current observations.

## Decision

Use a hybrid architecture (`docs/02_ARCHITECTURE.md` §1):

```text
historical data
    ↓
training / temporal validation
    ↓
validated production model
    ↓
live observations
    ↓
online feature generation
    ↓
real-time inference
```

- Offline and online paths share the same feature code in `src/floodguard/`; notebook-only feature logic is not allowed.
- Historical replay (backtesting) should run through the online path where practical, so replayed and live predictions are produced the same way.

## Alternatives

- **Live-only training:** no dependency on historical archives; far too few flood events for training or evaluation, and no backtesting.
- **Offline-only batch predictions:** simpler serving; no early warning on current conditions, which is the project's purpose.

## Consequences

Positive:

- models are evaluated on history before serving;
- training/serving skew is reduced by sharing feature code.

Trade-off:

- two data paths (historical import and live ingestion) must stay schema-compatible;
- depends on historical data availability, which Phase 1 must verify.

## Validation

Revisit if Phase 1 finds historical depth insufficient. Later checks: online features reproduce offline features for the same timestamps (feature parity test).

## Date

2026-09-24
