# Phase 6 — Water-Level Forecasting Contract

Status: **IMPLEMENTED** (2026-09-25, Phase 6). Code: `src/floodguard/forecasting/`
(`dataset`, `synthetic`, `persistence`, `preprocessing`, `statistical`,
`gradient_boosting`, `sequence_gate`, `timesfm`, `evaluation`, `artifacts`);
CLIs: `scripts/train_forecast_baseline.py`, `scripts/train_forecaster.py`,
`scripts/evaluate_forecaster.py`;
Tests: `tests/test_forecasting_*.py` (6 files, 42 tests).

> **Data constraint (explicit).** Current local captures hold two
> water-level station-days (154 usable intervals) and no verified flood
> events. Tiny station windows cannot establish Penang-wide forecasting
> performance. Real results are `LOCAL_REAL_DATA_DIAGNOSTIC` at best.
>
> ```text
> NO PHASE 6 MODEL HAS BEEN VALIDATED AS A GENERALIZABLE PENANG WATER-LEVEL FORECASTER.
> ```

---

## 1. Implemented Flow

```text
Phase 2 canonical WATER_LEVEL rows (usable, m, point-in-time)
  → forecast samples (backward lookback window + exact t+h target, per station)
  → chronological origin split (Phase 5 centralized rule, +120-min embargo)
  → per-station train-only scaling (frozen for validation/test)
  → model (persistence | linear AR | XGBoost regressor — CPU only)
  → frozen validation evaluation (MAE/RMSE/bias per station × horizon)
  → test evaluation (single pass; unseen stations rejected)
  → digest-verified local artifact + lineage
```

+30/+60/+120 stay separate targets. Walk-forward available via Phase 5
`walk_forward_folds` (same embargo semantics).

## 2. Forecasting Targets and Horizons

For each valid origin `t` with usable level `WL(t)` and usable exact target
`WL(t+h)`: persistence predicts `WL(t)`; learned models predict `WL(t+h)`
(or equivalently the delta — training uses scaled levels, artifacts record
the convention). Missing targets are excluded and counted, never
interpolated; no nearest-instant substitution.

## 3. Sequence Windows (project configuration)

- Lookback choices `{60, 120, 180}` min, default `120` (`LOOKBACK_CHOICES_MINUTES`,
  `DEFAULT_LOOKBACK_MINUTES` in `forecasting/__init__.py`). Documented as
  project configuration, not hydrological law.
- Backward-looking only: inputs are `(t−L, t]` on the exact 5-min grid.
- No bridging: any gap `> max_gap_minutes` (5.0, the verified history grid)
  anywhere in `[t−L, t+h]` rejects the sample for that horizon (counters:
  `rejected_missing_input`, `rejected_gap`, `rejected_missing_target`).
- Missing level is never zero; incomplete sequences rejected, no imputation
  (no learned imputation is required by TASKS.md).
- Sample identity: sensor + site + origin + dataset version + lookback +
  horizon (`sample_id()`); never bare row position.

## 4. Models (TASKS.md order; only listed families)

| Family | Module | Fit scope | Device |
|---|---|---|---|
| Persistence `WL(t+h)=WL(t)` | `forecasting/persistence.py` | none (fixed) | CPU |
| Linear AR (OLS over exact lags 5–120m) | `forecasting/statistical.py` | train origins only | CPU |
| XGBoost regressor (lags + backward deltas) | `forecasting/gradient_boosting.py` | train origins only | CPU only (non-CPU rejected) |
| LSTM/GRU | `forecasting/sequence_gate.py` | **NOT_JUSTIFIED** — no torch added, nothing trained | — |
| TimesFM benchmark | `forecasting/timesfm.py` | harness only; blocked without local setup | — |

Lag semantics are origin-exclusive (`lag_h = level(t−h)`) defined once in the
library builders and called by both training and evaluation scripts (review
M1). Lag/delta feature names are deterministic lineage
(`lag_feature_names`, `lag_delta_feature_names`).

## 5. Splits

Reused centralized Phase 5 `partition_rows`/`chronological_split` over sample
origins (review M2): `train ≤ train_end − 120m`, validation in
`(train_end, val_end − 120m]`, test after `val_end`. Training scripts assert
reported counts equal trained counts. A validation sample's lookback
reaching into the training period is legitimate observable history, not
leakage; training targets can never reach into validation (embargo).

## 6. Scaling and Stations

- Per-station mean/std fit on **training origins only**; frozen transform
  elsewhere. The scaler fits origin levels (documented distribution choice).
- No global scaler (datums incomparable); unseen stations raise a structured
  rejection, never pooled. No full-history or test-set scaling.
- Models are per-station; per-station metrics primary. Overall summaries are
  explicitly sample-weighted means; overall RMSE is labeled "mean of station
  RMSEs (not pooled RMSE)" (review L3).

## 7. Rainfall / Weather / Threshold Inputs

Phase 6 sequence samples carry water levels only. Rainfall pairing stays
limited to verified shared sites (not wired into samples); daily
categorical forecasts are not 5-min inputs; threshold distances stay
`CURRENT_THRESHOLD_REFERENCE_ONLY` and out of training. The sample schema
provably admits none of these (leakage gate 8).

## 8. Metrics, Skill, Selection

- Per station × horizon: MAE, RMSE, bias, n. No MAPE (levels can be ≈0 or
  negative). Empty evaluations → `NOT_EVALUABLE`.
- Persistence skill `1 − model_MAE/persistence_MAE` iff denominator positive,
  else `NOT_EVALUABLE` (never divide by zero).
- Selection requires identical dataset/sequence-config/target/horizon/split/
  period plus ≥ 30 targets, ≥ 2 stations with covered days; otherwise
  `NO_ELIGIBLE_FORECAST_MODEL`. Current verdict on real data:
  `NO_ELIGIBLE_FORECAST_MODEL` (correct).

## 9. Artifacts and Serialization

Layout: `artifacts/forecasting/<dataset_version>/plus_<h>m/<family>/`
(gitignored). Lineage: dataset/observations hash (real sha256 of input rows,
review L5), feature/sequence schema, target definition, station scope,
lookback, preprocessing + scaler lineage, architecture (lags), seed, device,
libraries, partitions, evidence level, metrics eligibility. `model_sha256`
verified at load; missing digests raise (review L1). Trusted-local joblib
only. Neural path policy documented (state_dict + config) for when sequence
training is ever justified.

## 10. Scripts (one-shot, offline, CPU)

- `scripts/train_forecast_baseline.py` — sample building + persistence scoring
  overall and per embargo partition.
- `scripts/train_forecaster.py` — gate → samples → embargo partitions →
  train-only scaling → per-station fit → frozen validation eval → artifact.
  `--lstm-gru` runs the justification gate; `--timesfm` checks availability.
- `scripts/evaluate_forecaster.py` — frozen-scaler single-pass test eval with
  skill vs persistence; horizon mismatch rejected; caller owns holdout
  (synthetic mode uses a different segment than training, review M3).

## 11. Synthetic Validation Policy

`SYNTHETIC_TEST_ONLY` fixtures (`forecasting/synthetic.py`): constant, rise,
fall, periodic, two-datum stations, missing slot/run, disconnected windows,
boundary truncation. Never in real paths; never performance claims; always
`SYNTHETIC_SOFTWARE_VALIDATION`.

## 12. LSTM/GRU and TimesFM Positions

- **LSTM/GRU: NOT_JUSTIFIED.** Gate requires ≥ 1000 training samples and
  ≥ 2 stations with ≥ 30 covered days each (configurable guidelines).
  Current data fails every criterion. No PyTorch added, no GPU introduced.
  Assessment is the task outcome; training stays blocked on permitted
  multi-year history.
- **TimesFM: protocol-complete, execution blocked.** Optional benchmark;
  harness checks package + local checkpoint (both absent); zero-shot runner
  accepts injected predictors so tests stay offline. No dependency, no
  downloads, no superiority assumption.

## 13. Hardware / Device Policy

CPU default everywhere (persistence, OLS, XGBoost CPU). No CUDA framework is
installed; `nvidia-smi` shows the RTX 3070 (8 GB) but no framework touches
it. No GPU benchmarking (no justified neural workload), no speedup claims.
`pytest` is offline, deterministic, CPU-only, GPU-independent. If sequence
training is ever justified: conservative batches, clean OOM handling, CPU
fallback, CPU/GPU equivalence check within tolerance (protocol documented,
not yet implemented — no model to check).

## 14. Licensing / Portfolio Guard

JPS bulk history remains `PERMISSION REQUIRED`; real sequences, artifacts,
predictions and tables stay local/gitignored; public tests synthetic-only.
Gates plus evidence levels block "validated forecaster / production-ready /
Penang-wide accuracy" claims. Docker remains BLOCKED (Windows WSL/VMP).

## 15. Reviewer Findings (independent audits)

4 MEDIUM + 5 LOW, all fixed with regression coverage (see §1–§11 for the
resulting design):

- M1 lag off-by-one + dead builders → single origin-exclusive lag definition
  in library builders, called by both scripts.
- M2 reimplemented splits + inflated counts → centralized `partition_rows`
  (new Phase 5 helper) with reported==trained count asserts.
- M3 evaluator scoring training data → distinct synthetic segment + holdout
  ownership documented.
- M4 tautological leakage tests → production-code append/schema guards.
- L1 missing-digest bypass → missing digests raise (both Phase 5 and 6).
- L2 unenforced coverage criterion → `stations_meeting_coverage` enforced.
- L3 mean-of-RMSEs → explicitly labeled.
- L4 evaluator guard/version gaps → lag guard mirrored, version passthrough.
- L5 weak assertion + hash tag → feature-name lineage checks, real row hash.

A final independent audit re-verified all 9 fixes (no active leakage) and
raised 1 MEDIUM + 2 LOW, also fixed: N1 (direct lag-builder regression
tests), N2 (`metadata.sha256` verified on load), N3 (missing lags REJECTED,
feature counts asserted vs `n_features_in_`).
