# Phase 6 — Water-Level Forecasting: Completion Report

Status: **SOFTWARE/METHODOLOGY COMPLETE** (2026-09-25).
**Real forecasting validation: NOT POSSIBLE** with current local data.

```text
NO PHASE 6 MODEL HAS BEEN VALIDATED AS A GENERALIZABLE PENANG WATER-LEVEL FORECASTER.
```

---

## 1. Authoritative Task Status (TASKS.md Phase 6, in order)

| Task | Status | Implementation & Test Artifacts |
|---|---|---|
| **Persistence baseline** | `DONE` (implementation + synthetic verification; per-station + partitioned scoring; real diagnostics blocked — no local dataset in checkout) | `src/floodguard/forecasting/dataset.py`, `persistence.py`, `scripts/train_forecast_baseline.py`, `tests/test_forecasting_dataset.py`, `test_forecasting_baselines.py` |
| **Statistical baseline** | `DONE` (per-station linear AR, OLS, train-only, CPU; synthetic verification) | `src/floodguard/forecasting/statistical.py`, `scripts/train_forecaster.py --model statistical`, `tests/test_forecasting_baselines.py` |
| **Gradient boosting with lag features** | `DONE` (per-station XGB regressor, lags+deltas, CPU-only; synthetic verification) | `src/floodguard/forecasting/gradient_boosting.py`, `scripts/train_forecaster.py --model xgboost`, `tests/test_forecasting_baselines.py` |
| **LSTM/GRU only if justified** | `DONE` as justification assessment: `NOT_JUSTIFIED` on current data (no torch, no GPU, nothing trained; training blocked on data) | `src/floodguard/forecasting/sequence_gate.py`, `scripts/train_forecaster.py --lstm-gru`, `tests/test_forecasting_gates.py` |
| **Optional TimesFM benchmark** | `DONE` as protocol + harness (availability check + injectable zero-shot runner; no dep, no checkpoint, no downloads; execution blocked) | `src/floodguard/forecasting/timesfm.py`, `scripts/train_forecaster.py --timesfm`, `tests/test_forecasting_gates.py` |
| **Horizon-specific MAE/RMSE** | `DONE` (per station × horizon MAE/RMSE/bias + skill + eligibility gate; synthetic verification) | `src/floodguard/forecasting/evaluation.py`, `scripts/evaluate_forecaster.py`, `tests/test_forecasting_baselines.py`, `test_forecasting_gates.py` |

Shared: `forecasting/{preprocessing,artifacts,synthetic}.py`; leakage gates:
`tests/test_forecasting_leakage.py`; artifacts: `tests/test_forecasting_artifacts.py`.
Full contract: `docs/PHASE6_FORECASTING.md`.

Each task is **software/methodology complete** and **synthetically verified**.
None is empirically validated on real FloodGuard data. Implementation DONE
does not mean real evaluation DONE. Phase 5's conclusion (no real
classification model eligible) is preserved and untouched.

---

## 2. Verification Results

- **Ruff lint** (`ruff check .`): passed.
- **Ruff format** (`ruff format --check .`): passed.
- **mypy strict** (`mypy src scripts tests`): passed.
- **pytest**: **669 passed, 0 failed** (627 pre-Phase-6 items incl. the CRLF failure,
  now fixed, + 42 new forecasting tests) — the pre-existing
  `test_station_master.py` CRLF failure is FIXED (see §8).
- **pip check** (`uv pip check`): all packages compatible (no new dependencies;
  sklearn + xgboost + numpy only).
- **Environment** (`scripts/verify_environment.py`): Python 3.11.14 venv.
- **Offline status**: new tests use `no_network`; scripts do no network/Docker/
  CUDA work and never download models.
- **CUDA smoke**: N/A — no CUDA framework installed (torch absent); `nvidia-smi`
  reports the RTX 3070 (8 GB) but no Phase 6 code path touches it. CPU fallback
  is the only path and is fully exercised.

## 3. Real-Data Forecast Diagnostics

No local dataset exists in this checkout (`data/processed/` holds only
`.gitkeep`; `data/local/` absent), so **no real metrics were computed** —
correctly, rather than inventing them. From Phase 3 evidence, the only
forecastable windows are two station-days (27608: 119 usable; 26460: 35
usable), far below the selection minima (≥ 30 targets, ≥ 2 covered stations).
Any future local run reports per station × horizon with sample counts under
`LOCAL_REAL_DATA_DIAGNOSTIC`, never as Penang performance.

## 4. Synthetic Validation (software correctness, clearly labeled)

- Exact-horizon target matching per +30/+60/+120; missing/grid/gap rejection
  with counters; stable sample IDs; station isolation across datums.
- Persistence exactness on constant series; OLS ≈ exact on linear rise with
  skill ≈ 1.0; GBM determinism; scaler train-only + unseen-station refusal.
- Embargo partitions with reported==trained asserts; walk-forward reuse.
- Gates: `NOT_JUSTIFIED`, TimesFM blocked states, `NO_ELIGIBLE_FORECAST_MODEL`,
  coverage enforcement, context comparability.
- Artifacts: lineage round-trip, determinism, tamper refusal, missing-digest
  refusal.
- Adversarial audit (10 gates): future-mutation invariance, target-mutation
  independence, append invariance, test-mutation independence, target-timestamp
  exclusion, feature/target separation, threshold/weather exclusion by schema,
  fold ordering, no window bridging.
- All synthetic scores carry `SYNTHETIC_SOFTWARE_VALIDATION`.

## 5. Temporal and Leakage Audit

- Backward-only windows; exact targets; no interpolation/fill/zero-fill.
- Centralized embargo (new shared `partition_rows` helper); reported counts
  asserted equal to trained counts in the training script.
- Train-only per-station scaling; frozen reuse; unseen-station rejection.
- Single origin-exclusive lag definition shared by train and eval paths.
- No shuffle; multi-station timestamp-safe; no test tuning (no HPO/early stop).
- Search of Phase 6 code: no TODO/FIXME/shuffle/centered-windows/future-inputs/
  global-scaling/test-tuning/unseeded-randomness/pooling/gap-interpolation/
  threshold-leakage/downloads/GPU-requirements/synthetic-as-real.

## 6. Model Eligibility

`NO_ELIGIBLE_FORECAST_MODEL` on any current-scale evidence (needs ≥ 30
targets per horizon, ≥ 2 stations with ≥ 30 covered days). No forecasting
model advances to Phase 7 as a real model. Synthetic candidates select
correctly when evidence is sufficient (tested).

## 7. Final Adversarial Forecasting Audit (10-step, synthetic)

1. Synthetic chronological sequences created. ✓
2. Train/val/test origin partitions built (embargo). ✓
3. Scaler/model fit on train only. ✓
4. Training outputs saved. ✓
5. All validation/test inputs and targets mutated. ✓
6. Retrained from the unchanged training set. ✓
7. Training scaler/model state unchanged. ✓
8. Post-origin observations mutated. ✓
9. Earlier input sequences unchanged. ✓
10. Test data never used for model selection. ✓

**Audit: PASS.**

## 8. CRLF Test Status (pre-existing Phase 5 failure)

The `test_station_master.py` golden failure (Windows `core.autocrlf=true`
converting LF fixtures to CRLF while the writer contract is LF) is **FIXED**:
`.gitattributes` pins `tests/fixtures/station_master/expected/*.csv` to
`eol=lf`; working-tree bytes normalized to the LF blobs (byte-identical to
HEAD, zero content diff, verified via `git diff` + blob hashes). No station-
master semantics changed; raw-payload byte guarantees untouched (separate
tests pass). Full suite: **669 passed, 0 failed**.

## 9. Reviewer Findings

Independent audit: **4 MEDIUM + 5 LOW** — all fixed (see `docs/PHASE6_FORECASTING.md`
§15 for the itemized list and `tests/test_forecasting_leakage.py` /
`test_forecasting_gates.py` / `test_forecasting_artifacts.py` for regressions).

Final independent audit re-verified all 9 fixes in code and at runtime (no
active temporal leakage) and raised **1 MEDIUM + 2 LOW**, also fixed:

- N1 lag-builder regression class untested → `tests/test_forecasting_lag_builders.py`
  (exact past levels, incomplete-set drops, origin/future exclusion, delta count).
- N2 `metadata.sha256` written but unverified → both Phase 5 and Phase 6
  loaders verify the metadata digest and raise when missing/mismatched.
- N3 evaluator silent lag defaults → missing `model_architecture.lags` is
  REJECTED; feature counts asserted against `n_features_in_`.

## 10. Licensing / External Blockers

- **JPS bulk historical retrieval: PERMISSION REQUIRED** (unchanged). No extra
  history fetched; real artifacts gitignored; public tests synthetic-only.
- **Docker runtime: BLOCKED** (Windows WSL/Virtual Machine Platform).
- **Real-data blocker:** permitted multi-year history with ≥ 2 covered
  stations and ≥ 1000 training samples before sequence-model justification;
  ≥ 30 targets/horizon and covered stations before any selection.

## 11. Limitations

Current history (two station-days) is insufficient for generalizable Penang
forecasting claims of any family, including persistence. All Phase 6 results
are methodology-complete but predictively unvalidated.

## 12. Phase 7 Handoff (first task read exactly from TASKS.md)

First Phase 7 task: **`MLflow experiments.`**

- Consumable Phase 6 artifacts: `forecasting/` modules (dataset, baselines,
  evaluation, artifacts with full lineage), `artifacts/forecasting/` layout
  convention, per-station frozen scalers, `NO_ELIGIBLE_FORECAST_MODEL` gate.
- Real model eligible to advance: **none**.
- Blocked evaluations: all real forecasting training/selection (insufficient
  history), LSTM/GRU training (`NOT_JUSTIFIED`), TimesFM execution (no setup).

**DO NOT START PHASE 7.**
