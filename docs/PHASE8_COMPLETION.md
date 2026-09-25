# Phase 8 — Backend + Database: Completion Report

Status: **SOFTWARE/METHODOLOGY COMPLETE** (2026-09-25), except live
PostgreSQL/PostGIS runtime verification which is **`BLOCKED`** (Docker/WSL
unavailable, no local server). No live-runtime claim is made.

---

## 1. Authoritative Task Status (TASKS.md Phase 8, in order)

| Task | Status | Implementation & Test Artifacts |
|---|---|---|
| **PostgreSQL/PostGIS** | `DONE` (static + SQLite-behavioral verification; live runtime `BLOCKED`) | `src/floodguard/backend/types.py`, `models.py`, PG-dialect DDL tests, `tests/test_backend_integration.py` (skipped) |
| **Station schema** | `DONE` | `models.py` (sites/sensors/thresholds), `tests/test_backend_models.py` |
| **Observation schema** | `DONE` | `models.py` + `repositories.py`, `tests/test_backend_repositories.py` |
| **Prediction schema** | `DONE` | `models.py` + `repositories.py`, cross-site guard tests |
| **Alert schema** | `DONE` (storage only) | `models.py` + `repositories.py`, lifecycle + cross-site tests |
| **FastAPI `/health`** | `DONE` | `api.py` + `health.py`, `tests/test_backend_api.py` |
| **FastAPI `/ready`** | `DONE` | `api.py` + `health.py`, `tests/test_backend_api.py` |
| **Prediction endpoints** | `DONE` | `api.py` + `schemas.py` (stations, observations, predictions, model, alerts) |
| **Integration tests** | `DONE` as harness + `BLOCKED` runtime (marked `integration`, skip without a reachable test DB) | `tests/test_backend_integration.py` |

Each DONE is implementation acceptance (works, tested, reviewed). Live
runtime acceptance is separately and explicitly `BLOCKED`, not DONE.

---

## 2. Verification Results

- **Ruff lint** (`ruff check .`): passed.
- **Ruff format** (`ruff format --check .`): passed.
- **mypy strict** (`mypy src scripts tests`): passed.
- **pytest**: **751 passed, 0 failed** (699 pre-Phase-8 + 52 new backend; 2 integration skipped — no live server).
- **pip check** (`uv pip check`): all installed packages compatible (new `backend` extra: fastapi/sqlalchemy/alembic/geoalchemy2/psycopg/httpx/uvicorn).
- **Environment** (`scripts/verify_environment.py`): Python 3.11.14 venv.
- **Offline status**: unit tests use SQLite + PG-dialect compile checks (`no_network`, plus a documented `loopback_only` fixture for TestClient); no JPS/GPU/real artifacts; no server required.

## 3. Data Integrity

- Canonical identity PK enforced; identical replays no-op; conflicts raise with raw/tz/schema identity (retrieval time excluded by design).
- True upserts for master data; FK parents pre-validated; cross-site prediction/alert rows rejected; race failures are retryable, never silent.
- NORMAL-never-eligible + W/A/B-eligible CHECKs; binary-or-NULL labels; degree-range coordinates; horizon set; tz-aware storage with naive-input rejection and tz-aware outputs.
- Migration `0001_initial` pinned to `backend_schema/v1`; upgrade/downgrade round-trip tested; downgrade guarded (confirmation + production refusal).
- Every FK has a covering ORM relationship (single-flush ordering pinned).

## 4. Security Review

- Env-only credentials with startup validation; passwords redacted in repr/logs/reports; `.env.example` placeholders only.
- ORM-only parameter-bound queries (heuristic test enforced); storage internals never reach API clients; CLI artifact paths confined; registry/lineage names validated; model filenames validated.
- Digests verified on artifact loads; tampered metadata refused.

## 5. Runtime Verification (Static/Unit vs Live — Kept Separate)

- **Statically/unit verified:** PG-dialect DDL (PostGIS type, GIST, TIMESTAMPTZ, PKs), EWKT SRID binds, WKB reads, migration upgrade/downgrade on SQLite, full repository/API behavior on SQLite with FK enforcement.
- **Live PostgreSQL/PostGIS: NOT TESTED (BLOCKED).** Docker runtime unavailable (Windows WSL/Virtual Machine Platform); port 5432 closed; no PostgreSQL service installed. `tests/test_backend_integration.py` (extension, SRID, GIST bbox, migration round-trip) skips cleanly and is ready for any reachable test database via `FLOODGUARD_TEST_DATABASE_URL` (name must contain `test`; production databases never touched).
- **No Docker repair attempted** (explicitly out of scope).

## 6. Reviewer Findings

Independent audit: **2 HIGH + 8 MEDIUM + 8 LOW** — all fixed with regression
tests (see `docs/PHASE8_BACKEND.md` §8). Final re-verification confirmed
14/14 fixes (one partial: `Alert.site` edge) plus 3 new items (1 MEDIUM +
2 LOW); every item fixed: `Alert.site` relationship + cross-site guard with
null-tolerant semantics, migration-engine disposal + sanitized pre-try,
WKB hex-prefix handling without value echo.

## 7. Licensing / External Blockers

- **JPS bulk historical retrieval: PERMISSION REQUIRED** (unchanged). Test
  fixtures are synthetic (`SYNTHETIC_TEST_ONLY`); real JPS-derived DB
  contents stay local.
- **Docker runtime: BLOCKED** (Windows WSL/Virtual Machine Platform).
- **Live PG server: none available** (no install performed; not requested).

## 8. Limitations

Backend and API are implementation-complete but live-unverified against
PostgreSQL/PostGIS. SQLite behavioral parity is strong (FK enforcement on,
shared-cache threading) but not a substitute for a live PostGIS run before
any production claim. No production model exists to serve
(`NO_ELIGIBLE_MODEL` preserved end to end).

## 9. Phase 9 Handoff (First Task Read Exactly From TASKS.md)

First Phase 9 task: **`Overview.`** (Streamlit internal analytics).

- Safe Phase 8 artifacts for Phase 9: repository layer (`Site/Sensor/
  Observation/Prediction/Alert` queries), FastAPI read endpoints as the
  data contract (Streamlit must call shared services/APIs, not duplicate
  logic), migration-tested schema, seeded SQLite harness patterns.
- Real model eligible to advance: **none**.
- Blocked evaluations: live PostGIS runtime verification; any serving of
  real predictions (no REAL evidence; promotion gates closed).

**DO NOT START PHASE 9.**
