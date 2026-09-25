# Phase 7 — MLOps: Completion Report

Status: **SOFTWARE/METHODOLOGY COMPLETE** (2026-09-25).
**No model is promotable on current evidence** (registry production
unreachable; promotion gate BLOCKs synthetic/local by construction).

---

## 1. Authoritative Task Status (TASKS.md Phase 7, in order)

| Task | Status | Implementation & Test Artifacts |
|---|---|---|
| **MLflow experiments** | `DONE` (local run store; synthetic verification) | `src/floodguard/mlops/experiments.py`, `tests/test_mlops_experiments.py` |
| **Model registry** | `DONE` (gated stages + audit log; synthetic verification) | `src/floodguard/mlops/registry.py`, `scripts/register_model.py`, `tests/test_mlops_registry.py` |
| **DVC/lineage strategy** | `DONE` (hash-linked manifests + adoption plan; no DVC installed) | `src/floodguard/mlops/lineage.py`, `tests/test_mlops_registry.py` |
| **Model card** | `DONE` (deterministic, honest framing) | `src/floodguard/mlops/cards.py`, `scripts/render_cards.py`, `tests/test_mlops_cards.py` |
| **Dataset card** | `DONE` (provenance + licensing) | `src/floodguard/mlops/cards.py`, `tests/test_mlops_cards.py` |
| **Automated model tests** | `DONE` (six offline acceptance checks) | `src/floodguard/mlops/validation.py`, `tests/test_mlops_promotion.py` |
| **Promotion gate** | `DONE` (BLOCK-by-default; synthetic verification) | `src/floodguard/mlops/promotion.py`, `scripts/promote_model.py`, `tests/test_mlops_promotion.py` |

Each task is **software/methodology complete** and **synthetically verified**.
No production promotion is possible or claimed. Implementation DONE does not
mean real validation DONE. Full contract: `docs/PHASE7_MLOPS.md`.

---

## 2. Verification Results

- **Ruff lint** (`ruff check .`): passed.
- **Ruff format** (`ruff format --check .`): passed.
- **mypy strict** (`mypy src scripts tests`): passed.
- **pytest**: **699 passed, 0 failed** (669 pre-Phase-7 + 30 new MLOps).
- **pip check** (`uv pip check`): all installed packages compatible (Phase 7
  adds zero dependencies: stdlib + lazy numpy/joblib only).
- **Environment** (`scripts/verify_environment.py`): Python 3.11.14 venv.
- **Offline status**: new tests use `no_network`; no MLflow server, DVC
  remote, network, Docker, or GPU anywhere in Phase 7 paths.

## 3. Real-Evidence Status (Unchanged by Phase 7)

Phase 7 adds process, not evidence. Classification stays
`NO_ELIGIBLE_MODEL`; forecasting stays `NO_ELIGIBLE_FORECAST_MODEL`;
LSTM/GRU stays `NOT_JUSTIFIED`; TimesFM stays blocked. The registry has no
production path for synthetic/local runs, and the gate BLOCKs them with
explicit reasons (verified live: synthetic candidate → BLOCK citing
eligibility + evidence).

## 4. Synthetic Validation (Clearly Labeled)

- Deterministic run IDs + write-once stores + digest-verified reads.
- Stage edges (demotion/skip/rewrite rejected), terminal archive, audit log.
- Lineage digest chains verify backward; conflicts rejected.
- Cards byte-identical on re-render; warnings present/absent by evidence.
- Acceptance passes on valid artifacts, fails on tampered/missing-baseline.
- Promotion PROMOTEs only the fully-evidenced bundle; BLOCKs synthetic,
  missing baseline/audit/card, ineligible status, accuracy-only review,
  unknown tasks, and unverifiable references.
- All synthetic results carry `SYNTHETIC_SOFTWARE_VALIDATION`.

## 5. Security and Trust Audit

- CLI pickle loading confined under `--artifact-root` (default repo root);
  `model_filename` separators rejected in all loaders/savers.
- Registry/lineage/card names path-validated (`..`, separators, drive
  syntax rejected); run IDs validated on read.
- Missing/mismatched digests (model + metadata) raise in both phases.
- `--i-attest-real-evaluation` required before REAL evidence is recorded.
- `--apply` binds bundle `run_id` to the registry version; refs must exist.
- No secrets, absolute personal paths, network, or GPU in new code.
- Known limitation (documented): digests prove same-run integrity, not
  authenticity against a writer-capable attacker; pickle remains the format
  (safetensors/signed-digest migration noted for later).

## 6. Reviewer Findings

Independent audit: **2 HIGH + 8 MEDIUM + 5 LOW** — all fixed with regression
tests (see `docs/PHASE7_MLOPS.md` §8). Final verification re-checked all
fixes (11/12 fully, 1 partially) plus 5 new LOWs; every item fixed:
acceptance always emits all checks, `get_run` validates IDs, registry
skips non-version files loudly, unknown tasks BLOCK, savers validate
filenames, full sidecar digests, strict JSON params.

## 7. Genuine Blockers (External, Not Implementation)

- **JPS bulk historical retrieval: PERMISSION REQUIRED** — no real training
  data, so no REAL evidence, so no production promotion. Unchanged.
- **Docker runtime: BLOCKED** (Windows WSL/Virtual Machine Platform).
- **MLflow server / DVC remote**: deliberately not adopted (no data scale to
  justify them); records are migration-ready.

## 8. Limitations

MLOps process is complete but operates on synthetic/test evidence only.
Production promotion, MLflow server adoption, and DVC remote setup all await
permitted multi-year history with sufficient independent flood events.

## 9. Phase 8 Handoff (First Task Read Exactly From TASKS.md)

First Phase 8 task: **`PostgreSQL/PostGIS.`**

- Phase 8 may consume: `mlops/` lineage manifests (dataset digests, station
  scope), station-master contracts, canonical observation schemas
  (`docs/04_DATA_DICTIONARY.md`), registry/artifact layout conventions.
- Real model eligible to advance: **none**.
- Blocked evaluations: all production promotion and real-model serving
  (insufficient history; no REAL evidence).

**DO NOT START PHASE 8.**
