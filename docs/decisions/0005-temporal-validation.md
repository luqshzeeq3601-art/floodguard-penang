# ADR-0005: Temporal Validation Instead of Random Splitting

## Status

Accepted

## Context

Flood risk is predicted from time series. Neighbouring rows are strongly correlated, and events span many consecutive rows. A random split puts near-identical rows from the same event in both train and test, so reported performance can look far better than live performance.

## Decision

- Split data chronologically: earlier period for training, later periods for validation and final test. Use walk-forward validation where data volume allows.
- Fit scalers, imputers, encoders and other learned preprocessing on the training window only.
- Rolling and lag features use only data at or before the prediction time.
- Tune hyperparameters on validation windows, never on the final test period.
- Report results per validation period and analyze events, not only rows.

Details: `docs/05_METHODOLOGY.md` §4, `.claude/rules/temporal-data.md`, `AGENTS.md` §9.

## Alternatives

- **Random shuffled split:** uses all periods evenly; leaks future information and overstates performance.
- **Generic k-fold cross-validation:** lower variance estimates; shuffled folds leak the same way. Time-ordered folds are the accepted variant (walk-forward).

## Consequences

Positive:

- evaluation matches how the model is used: trained on the past, predicting the future;
- reported metrics are defensible.

Trade-off:

- fewer events in each evaluation window, so metrics are noisier;
- seasonal or climate drift between periods can lower scores compared with a random split.

## Validation

Leakage tests are required for feature and split code (Phase 4 "Leakage tests"). The ML reviewer checks split boundaries and preprocessing fit scope before any model is promoted.

## Date

2026-09-24
