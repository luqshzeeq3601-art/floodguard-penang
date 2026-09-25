# Phase 5 — Modeling Contract: Baselines and ML

Status: **IMPLEMENTED** (2026-09-25, Phase 5). Code: `src/floodguard/modeling/`
(`splits`, `features`, `preprocessing`, `labels`, `feasibility`, `metrics`,
`baselines`, `logistic`, `forest`, `gradient_boosting`, `thresholds`,
`calibration`, `comparison`, `artifacts`, `shap_analysis`, `synthetic`);
CLIs: `scripts/train_baseline.py`, `scripts/train_model.py`, `scripts/evaluate_model.py`;
Tests: `tests/test_modeling_*.py` (7 files, 52 tests).

> **Data constraint (explicit).** The current local real captures contain
> 289 rainfall intervals, 154 usable water-level intervals, **zero** observed
> threshold exceedances, **zero** contiguous episodes and **zero** positive
> +30/+60/+120 flood-proxy labels. Every real-data claim below is therefore
> `INSUFFICIENT_EVENT_SUPPORT` / `NOT_EVALUABLE` / `NO_ELIGIBLE_MODEL`.
> **NO REAL FLOOD CLASSIFICATION MODEL IS EMPIRICALLY VALIDATED YET.**
> Targets (recall ≥ 90%, F1 ≥ 0.85) remain future objectives, not results.

---

## 1. Implemented Flow

```text
Phase 2 canonical data
  → Phase 4 features (registry: 102 definitions incl. 3 CURRENT_THRESHOLD_REFERENCE_ONLY)
  → Phase 3 horizon labels (+30/+60/+120, MISSING_FUTURE_TARGET never imputed)
  → feasibility gate (per-horizon minima; INSUFFICIENT_EVENT_SUPPORT on real data)
  → chronological split (train < validation < test, +120-min purge/embargo)
  → training-only preprocessing (medians/means/stds/vocabs/class weights)
  → baseline/model (persistence, rule, logistic, forest, xgboost — CPU only)
  → validation (frozen decision configuration: threshold + calibration on val only)
  → test evaluation (single pass, NOT_EVALUABLE where undefined)
  → model artifact + lineage metadata (digest-verified local joblib)
```

Walk-forward expanding folds (`walk_forward_folds`) use identical embargo
semantics. Model comparison requires identical dataset/feature/label/horizon/
split/period; otherwise `NO_ELIGIBLE_MODEL`.

---

## 2. Baselines

- **Persistence regression:** `predicted WL(t+h) = WL(t)` per horizon
  (+30/+60/+120 independent). Origin must be usable; missing futures excluded.
- **Rule classifier:** fires when backward rise rate **or** trailing rainfall
  exceeds a frozen threshold, from origin-`t` features only. Never reads
  `WL(t+h)`. Threshold distances usable only with explicit
  `allow_threshold_reference=True` (`CURRENT_THRESHOLD_REFERENCE_ONLY`).

## 3. Learned Models (simple → complex, TASKS.md order)

| Family | Module | Determinism | Device |
|---|---|---|---|
| Logistic Regression | `modeling/logistic.py` | `random_state=42`, lbfgs | CPU |
| Random Forest | `modeling/forest.py` | `random_state=42`, `n_jobs=1` | CPU |
| XGBoost (the `XGBoost/LightGBM` representative; LightGBM intentionally not added) | `modeling/gradient_boosting.py` | seed-fixed, `tree_method="hist"` | CPU only (non-CPU rejected) |

Single-class training partitions return structured infeasibility
(`INFEASIBLE_SINGLE_CLASS`) instead of a meaningless fit. Class weights come
from training data only. No LSTM/GRU/Transformer/TimesFM/PyTorch/TensorFlow
(Phase 6 scope; RTX 3070 present but unused — data, not compute, is the
bottleneck).

## 4. Temporal Splitting

- Exact timestamps order partitions; no shuffling anywhere.
- `train ≤ train_end − 120m`; `validation ∈ (train_end, val_end − 120m]`;
  `test > val_end`. Origins whose +120-minute target window crosses a boundary
  are purged and counted.
- Centralized in `modeling/splits.py`; training scripts reuse the same rule
  (index-keyed, multi-station safe) and assert reported counts match trained
  counts (review H1).
- Boundary-tested at exact/±1-interval/±120-minute offsets.
- Walk-forward folds share the embargo (first-fold embargo zone purged, M2).

## 5. Feature Eligibility

Authoritative Phase 4 registry drives selection (`modeling/features.py`).
Excluded by default: identifiers, JPS/raw IDs, hashes, provenance columns,
paired-site IDs, station district/basin/type **and coordinates** (M4),
`CURRENT_THRESHOLD_REFERENCE_ONLY` distances (explicit opt-in only),
all `target_plus_*`/label/future columns, and any non-registry column.
Regression-tested against silent threshold/identifier entry.

## 6. Preprocessing / Missing Values / Imbalance

- Medians/means/stds/vocabularies fit on **training only**; frozen transform
  elsewhere; unseen categories → unknown bucket (L1: type inference from train
  only).
- No forward/backward fill across gaps; no future imputation; learned
  parameters train-only. `MISSING_FUTURE_TARGET` excluded from loss/evaluation.
- Natural prevalence preserved in validation/test. Class weights train-only,
  both-classes-required. No SMOTE on real data (zero positives); synthetic
  fixtures only for plumbing tests.

## 7. Metrics, Thresholds, Calibration

- Classification per horizon: recall, precision, F1, PR-AUC (deterministic
  average precision), false-negative rate, confusion (TP/FP/TN/FN), accuracy
  reported but never primary. Undefined stays `NOT_EVALUABLE`; defined-zero
  F1 is `0.0` (L4); empty evaluations give `NOT_EVALUABLE` accuracy.
- Regression per horizon: MAE/RMSE (persistence at +30 uses +30 targets only).
- Decision thresholds optimized on validation (`max_f1` grid), frozen, applied
  once to test. Calibration (sigmoid/isotonic, seeded) fit on train/val only.
  Real-data threshold/calibration optimization is `NOT_EVALUABLE` without
  event support.

## 8. Eligibility, Comparison, Selection

- Feasibility minima apply **per horizon** (weakest of +30/+60/+120 must pass;
  no triple-counting, M1): ≥ 10 episodes, ≥ 30 positives, ≥ 30 negatives.
- Comparison requires full context match; champion needs `eligible` runs with
  ≥ 10 evaluation positives. Real result on current data:
  `NO_ELIGIBLE_MODEL — INSUFFICIENT_EVENT_SUPPORT` (correct, preferable to a
  misleading "best model").

## 9. Artifacts & Serialization

Layout: `artifacts/models/<dataset_version>/<label_version>/plus_<h>m/<family>/`
(gitignored). Lineage: family, run ID, horizon, dataset/observations/feature/
label versions, split, timestamp, seed, feature names, eligibility policy,
preprocessing, class weighting, hyperparameters, library versions, device,
evidence level. `metadata.sha256` + `model_sha256` digest verified at load
(L7). Trusted-local joblib only; no API loading in Phase 5.

## 10. Scripts (one-shot, offline, CPU)

- `scripts/train_baseline.py` — partitioned persistence/rule evaluation
  (train/validation/test + all), frozen rule config, unevaluable-origin counts.
- `scripts/train_model.py` — gate → embargo partitions → eligibility →
  train-only preprocessing → fit → frozen validation eval → artifact.
- `scripts/evaluate_model.py` — frozen-preprocessor test evaluation; horizon
  match enforced; threshold provenance recorded.

## 11. Synthetic Validation Policy

`SYNTHETIC_TEST_ONLY` fixtures (`modeling/synthetic.py`): chronological,
positive/negative episodes (crossing/not-crossing boundaries), per-horizon
missing tails (6/12/24 slots for +30/+60/+120, L8), balanced/imbalanced and
all-negative/all-positive edge cases. Never in real paths; never portfolio
claims. All synthetic results carry `SYNTHETIC_SOFTWARE_VALIDATION`.

## 12. SHAP Analysis

`modeling/shap_analysis.py`: exact SHAP values when optional `shap` is
installed; otherwise deterministic permutation-contribution fallback
(seed-fixed). Contributions framed as contribution, never causality.
`shap` stays optional — normal `pytest` never requires it.

## 13. Hardware / Device Policy

CPU default everywhere. XGBoost 3.2.0 CPU (`tree_method="hist"`,
`device="cpu"`, constructor rejects non-CPU). No CUDA toolkit changes, no
PyTorch/cuDNN, no GPU benchmarking (no meaningful workload exists with zero
real positives). `pytest` remains offline, deterministic, CPU-only, CUDA-
independent. No speedup claims (none benchmarked).

## 14. Licensing / Portfolio Guard

JPS bulk history remains `PERMISSION REQUIRED`; real artifacts gitignored;
public tests use synthetic/sanitized fixtures. Gates (`INSUFFICIENT_EVENT_
SUPPORT`, `NOT_EVALUABLE`, `NO_ELIGIBLE_MODEL`) plus evidence levels prevent
misleading "90% recall / F1 0.85 / best model / production-ready" claims.
Docker runtime remains BLOCKED (Windows WSL/VMP).

## 15. Reviewer Findings (independent audit)

HIGH fixed: H1 (training script embargo bypass + timestamp-key collapse).
MEDIUM fixed: M1 (per-horizon minima), M2 (fold-0 embargo), M3 (partitioned
baselines), M4 (lat/lon exclusion), M5 (standard gate for real runs).
Material LOW fixed: L1 (train-only type inference), L2 (single scaler),
L3 (calibration seed), L4 (F1-zero/empty-accuracy), L5 (evidence threading),
L6 (horizon match + threshold provenance), L7 (model digest), L8
(per-horizon tails), L9 (dead options removed), L10 (unevaluable counts).
Regression tests: `tests/test_modeling_reviewer_regressions.py`.
