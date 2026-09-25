# Phase 5 — Baselines and ML: Completion Report

Status: **SOFTWARE/METHODOLOGY COMPLETE** (2026-09-25).
**Real predictive validation: NOT POSSIBLE** with current local data.

```text
NO REAL FLOOD CLASSIFICATION MODEL IS EMPIRICALLY VALIDATED YET.
```

---

## 1. Authoritative Task Status (TASKS.md Phase 5, in order)

| Task | Status | Implementation & Test Artifacts |
|---|---|---|
| **Persistence/rule baseline** | `DONE` (implementation + synthetic verification; real evaluation blocked — zero positives) | `src/floodguard/modeling/baselines.py`, `scripts/train_baseline.py`, `tests/test_modeling_baselines.py` |
| **Logistic Regression** | `DONE` (implementation + synthetic verification; real training infeasible — zero positives) | `src/floodguard/modeling/logistic.py`, `scripts/train_model.py --model logistic`, `tests/test_modeling_learners.py` |
| **Random Forest** | `DONE` (implementation + synthetic verification; real training infeasible) | `src/floodguard/modeling/forest.py`, `scripts/train_model.py --model forest`, `tests/test_modeling_learners.py` |
| **XGBoost/LightGBM** | `DONE` as **XGBoost** CPU (LightGBM intentionally not added; synthetic verification; real training infeasible) | `src/floodguard/modeling/gradient_boosting.py` (xgboost 3.2.0, `device="cpu"`), `pyproject.toml` `ml` extra, `tests/test_modeling_learners.py` |
| **Chronological validation** | `DONE` (centralized splitter + embargo + boundary tests) | `src/floodguard/modeling/splits.py`, `tests/test_modeling_splits.py`, `tests/test_modeling_leakage.py` |
| **Walk-forward validation where practical** | `DONE` (expanding folds with embargo; synthetic verification) | `src/floodguard/modeling/splits.py::walk_forward_folds`, `tests/test_modeling_splits.py` |
| **Calibration analysis** | `DONE` (val-only fit, frozen apply; real calibration NOT_EVALUABLE) | `src/floodguard/modeling/calibration.py`, `src/floodguard/modeling/thresholds.py`, `tests/test_modeling_evaluation.py` |
| **SHAP analysis** | `DONE` (exact SHAP when installed + deterministic fallback; contribution framing) | `src/floodguard/modeling/shap_analysis.py`, `tests/test_modeling_evaluation.py` |
| **Select candidate production model** | `DONE` (policy + gates implemented; real result `NO_ELIGIBLE_MODEL — INSUFFICIENT_EVENT_SUPPORT`) | `src/floodguard/modeling/comparison.py`, `scripts/train_model.py`, `scripts/evaluate_model.py`, `tests/test_modeling_evaluation.py` |

Shared foundation: `modeling/{features,preprocessing,labels,feasibility,metrics,
artifacts,synthetic}.py`; leakage gates: `tests/test_modeling_leakage.py`;
reviewer regressions: `tests/test_modeling_reviewer_regressions.py`.
Full contract: `docs/PHASE5_MODELING.md`.

Each task is **software/methodology complete** (works, tested, reviewed) and
**synthetically verified**. None is empirically validated on real FloodGuard
data — correctly so, given zero positive events. Implementation DONE does not
mean real evaluation DONE.

---

## 2. Verification Results

- **Ruff lint** (`ruff check .` scope: modeling + scripts + new tests): passed.
- **Ruff format** (`ruff format --check`): passed.
- **mypy strict** (`mypy src/floodguard/modeling scripts/train_baseline.py scripts/train_model.py scripts/evaluate_model.py`): passed.
- **pytest**: **626 passed** (574 pre-existing + 52 new Phase 5), 1 pre-existing
  unrelated failure (`test_station_master.py::test_golden_output_matches_
  synthetic_expected` — Windows `core.autocrlf=true` CRLF vs writer LF; fails
  identically without Phase 5 changes; not weakened).
- **pip check** (`uv pip check`): all installed packages compatible
  (xgboost 3.2.0 + scikit-learn 1.9.1 + CPU stack).
- **Environment** (`scripts/verify_environment.py`): Python 3.11.14 venv.
- **Offline status**: new tests use `no_network` fixture; scripts perform no
  network/Docker/CUDA operations.

## 3. Real-Data Feasibility (local evidence, Phases 3–4)

| Item | Observed |
|---|---|
| Rainfall intervals (local) | 289 |
| Usable water-level intervals (local) | 154 |
| Observed threshold exceedances | 0 |
| Contiguous threshold episodes | 0 |
| Positive +30/+60/+120 flood-proxy labels | 0 |
| Independent positive episodes | 0 |
| Chronological 3-way split with event support | INFEASIBLE (`INSUFFICIENT_EVENT_SUPPORT`) |
| Real classifier training/evaluation allowed | **NO** |
| Real threshold optimization / calibration | `NOT_EVALUABLE` |
| Production champion eligible to advance | `NO_ELIGIBLE_MODEL` |

No positives were fabricated, relabeled, duplicated, SMOTE-generated, or
imported from synthetic fixtures. All-negative accuracy is not reported as
quality.

## 4. Synthetic Validation (software correctness, clearly labeled)

- Persistence identity (`WL(t+h)=WL(t)`), missing-target exclusion, per-horizon
  independence, rule origin-only behavior + threshold opt-in.
- Chronological ordering, exact-boundary rules, 120-minute purge/embargo,
  walk-forward expansion, `INSUFFICIENT_EVENT_SUPPORT` structure.
- Train-only preprocessing (medians/vocabs/weights), unseen-category buckets,
  determinism across repeats, single-class refusal for all three families.
- Threshold/calibration val-only fit + frozen test apply; comparison
  comparability + `NO_ELIGIBLE_MODEL`; artifact lineage round-trip + tamper
  rejection; SHAP fallback determinism.
- Adversarial audits: future-mutation invariance, validation-label-mutation
  independence, appended-data invariance, threshold-reference exclusion,
  future-target absence from features.
- All synthetic metrics carry `SYNTHETIC_SOFTWARE_VALIDATION` and must never
  be framed as FloodGuard predictive performance.

## 5. Temporal and Leakage Audit

- No random shuffle; exact-timestamp ordering with loud invariant.
- Horizon-aware embargo centralized and reused by training scripts (H1 fixed;
  index-keyed, count-asserted).
- Train-only fitting for scalers/encoders/imputers/weights/thresholds/
  calibration; test never refits (L1 fixed).
- Feature/target separation preserved; `MISSING_FUTURE_TARGET` excluded.
- Threshold-reference and station identifiers excluded by default (M4 fixed).
- Per-horizon synthetic tails (6/12/24) exercise truncation faithfully (L8).
- Final adversarial modeling audit ( Sec. 7) passes.

## 6. Class Imbalance and Event Support

Observation-level and event-level support reported separately everywhere.
Per-horizon minima enforced (M1): weakest of +30/+60/+120 must satisfy
≥ 10 episodes / ≥ 30 positives / ≥ 30 negatives. Current real support is
0/0/0 per horizon — gate fails honestly.

## 7. Final Adversarial Modeling Audit (10-step, synthetic)

1. Deterministic synthetic chronological dataset constructed. ✓
2. Features and targets built independently. ✓
3. Split chronologically with embargo. ✓
4. Preprocessing + model fit on training only. ✓
5. Training preprocessing/model outputs saved. ✓
6. Every validation/test observation and label radically modified. ✓
7. Training re-run. ✓
8. Training preprocessing, parameters and predictions unchanged. ✓
   (`test_validation_label_mutation_leaves_training_unchanged`)
9. Test data never affects threshold/calibration selection. ✓
   (`test_test_data_never_fits_threshold_or_calibration`)
10. Post-origin observation changes never alter earlier feature vectors. ✓
    (`test_future_mutation_leaves_earlier_training_rows_identical`)

**Audit: PASS.**

## 8. Reviewer Findings

Independent audit (temporal-leakage/methodology): **1 HIGH, 5 MEDIUM,
10 LOW** — all fixed with regression tests
(`tests/test_modeling_reviewer_regressions.py`):

- H1 training-script embargo bypass + timestamp-key collapse → partitions
  reuse the split rule, index-keyed, count-asserted.
- M1 triple-counted event support → per-horizon minima.
- M2 fold-0 embargo validation → embargo zone purged, never validated.
- M3 in-sample baselines → partitioned evaluation, frozen config.
- M4 lat/lon eligible → excluded from standard training.
- M5 relaxed real gate → documented standard gate for `--input` runs.
- L1–L10 material items fixed (train-only type inference, single scaler,
  calibration seed, F1-zero/empty-accuracy semantics, evidence threading,
  horizon match + threshold provenance, model digest verification,
  per-horizon synthetic tails, dead options removed, unevaluable counts).

## 9. Licensing / External Blockers

- **JPS bulk historical retrieval: PERMISSION REQUIRED** (unchanged). No
  additional history used; real artifacts gitignored; public tests synthetic.
- **Docker runtime: BLOCKED** (Windows WSL/Virtual Machine Platform).
- **Real-data blocker:** permitted multi-year history with sufficient
  independent flood episodes required before any empirical validation.

## 10. Limitations

Production-quality flood prediction claims require permitted multi-year
historical data containing sufficient independent flood events. Current
implementation is methodology-complete and honestly gated; predictive
performance is unmeasured and unclaimed.

## 11. Phase 6 Handoff (first task read exactly from TASKS.md)

First Phase 6 task: **`Persistence baseline.`** (water-level forecasting
persistence, distinct from the Phase 5 classification/regression baselines).

- Consumable Phase 5 artifacts: `modeling/splits.py` (chronological +
  embargo partitions), `modeling/metrics.py` (horizon-specific MAE/RMSE with
  `NOT_EVALUABLE`), `modeling/baselines.py::persistence_forecast_for_row`,
  `scripts/train_baseline.py` (partitioned persistence diagnostics).
- Real trained model eligible to advance: **none** (`NO_ELIGIBLE_MODEL`).
- Blocked evaluations: all real flood-classification training, threshold
  optimization, calibration, and champion selection (zero positives).

**DO NOT START PHASE 6.**
