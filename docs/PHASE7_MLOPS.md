# Phase 7 — MLOps Contract: Experiments, Registry, Lineage, Cards, Gates

Status: **IMPLEMENTED** (2026-09-25, Phase 7). Code: `src/floodguard/mlops/`
(`experiments`, `registry`, `lineage`, `cards`, `validation`, `promotion`);
CLIs: `scripts/register_model.py`, `scripts/promote_model.py`,
`scripts/render_cards.py`;
Tests: `tests/test_mlops_*.py` (4 files, 30 tests).

> Local-first and server-free. Experiment runs, model versions, lineage
> manifests, cards, acceptance checks and promotion verdicts are
> deterministic JSON/Markdown under the gitignored store
> `artifacts/mlops/`. No MLflow server, DVC remote, network, Docker or GPU
> is required. `NO_ELIGIBLE_MODEL` / `NO_ELIGIBLE_FORECAST_MODEL` stand
> until real evidence supports otherwise.

---

## 1. Experiment Tracking (MLflow Experiments Without the Server)

`mlops/experiments.py` stores MLflow-concept-compatible run records (params,
metrics, tags, artifact refs) write-once with digest sidecars. Run IDs are
deterministic hashes of the experiment definition (no wall-clock). Params
must be JSON-native (exotic objects rejected, keeping IDs stable).
`to_mlflow_tags()` flattens lineage into the string-tag mapping a future
`mlflow.start_run` call would log. `find_runs` filters with per-file
skip-on-corruption; `audit_store` verifies the whole store explicitly.

No `mlflow` package is installed: a tracking server would add Flask/SQLAlchemy
weight for zero current benefit (no real training runs exist). Migration is
documented below.

## 2. Model Registry (Gated Stages)

`mlops/registry.py`: versions auto-increment per model name; allowed edges
`none -> staging -> production` plus `* -> archived` (terminal). Demotions,
skips and rewrites are rejected; every transition appends to
`transitions.jsonl` with reason and timestamp. Name segments are
path-validated (`..`, separators, drive syntax rejected).

- Registration records caller claims (never quality); the blessed path
  `scripts/register_model.py` verifies artifact digests first.
- `staging` accepts any evidence; `production` needs a recorded `PROMOTE`
  verdict **and** `REAL_PREDICTIVE_EVALUATION` evidence — unreachable with
  current data, which is the point.

## 3. DVC / Lineage Strategy (No DVC Installed)

`mlops/lineage.py`: deterministic content-hashed dataset manifests
(version, observation hash, source, station scope, schemas, code version)
and model records linking `run_id` to the exact dataset digest.
`verify_model_lineage` fails loudly on mismatch. These manifests are exactly
the files a future DVC setup would track.

DVC adoption plan (executed only when multi-year history lands):

```yaml
# dvc.yaml (future; not executed now)
stages:
  build_dataset:
    cmd: .venv/Scripts/python scripts/build_historical_dataset.py
    outs:
      - data/processed/observations/v1/
  train:
    cmd: .venv/Scripts/python scripts/train_forecaster.py --input ...
    outs:
      - artifacts/forecasting/
  register:
    cmd: .venv/Scripts/python scripts/register_model.py --artifact ...
    outs:
      - artifacts/mlops/
```

No `dvc` package, remote, or pipeline is created now: with only fixture-scale
local captures, DVC would add process without data to version. JPS-derived
outputs stay gitignored either way.

## 4. Model Cards and Dataset Cards

`mlops/cards.py` renders deterministic Markdown from stored records only.
Every card carries the non-official research disclaimer; non-REAL evidence
adds an explicit no-real-validation warning; dataset cards state the JPS
permission requirement. Evaluation sections record their source file as
unverified-external unless it came from the run record.

## 5. Automated Model Tests

`mlops/validation.py` runs six offline CPU checks per artifact: digest
verification, metadata schema, evidence label, load-and-predict, inference
latency vs the 0.5 s budget (upper-bound probe; tests assert measurement,
not speed, to avoid flaky CI), and known-baseline-family reference. Loaders
reject escaping `model_filename` values; acceptance reports failures instead
of crashing on corrupt payloads.

## 6. Promotion Gate

`mlops/promotion.py` PROMOTEs only when: acceptance passes; baseline
comparison favors the candidate (or justified tie) with task-appropriate
metrics reviewed (classification: recall + false-negative-rate + PR-AUC;
forecasting: MAE + RMSE — accuracy-only review BLOCKs); eligibility gate
passes; evidence is REAL; leakage attestation and model card exist.
`scripts/promote_model.py` additionally verifies referenced files exist and,
on `--apply`, binds the bundle `run_id` to the registry version before any
transition. Synthetic/local candidates BLOCK with explicit reasons.

## 7. Trust Boundaries (Known Limitations)

- Pickle (`joblib`) loading executes code: digests prove same-run integrity,
  not authenticity. CLI artifact paths are confined under an explicit root
  (`--artifact-root`, default repo root); `scripts/register_model.py`
  additionally requires `--i-attest-real-evaluation` before recording REAL
  evidence. Long-term: migrate to a non-pickle format or signed digests.
- `register()` records caller claims; enforcement lives in the gate +
  stage rules + blessed script path (documented, not silent).
- Store paths are normalized relative to the repo root where possible so no
  personal absolute paths leak into records.

## 8. Reviewer Findings (independent audit)

HIGH fixed: pickle trust boundary (root confinement + attestation flag +
documented limitation); PROMOTE binding (run_id match + ref existence +
task-appropriate metric allowlist). MEDIUM fixed: path traversal
(`validate_segment` everywhere), registry claim trust (documented + blessed
path), stage-machine edges + audit log + timestamp fix, acceptance exception
widening + always-emit latency, baseline check (known-family membership),
`find_runs` skip-and-audit, latency-gate deflake, script conversion guards +
strict names/tasks/kind-schema checks. LOW fixed where material: full
sidecar digests, relative store paths, evaluation provenance labels, strict
JSON params, `model_filename` validation.
