# Phase 8 — Backend & Database Contract: PostgreSQL/PostGIS + FastAPI

Status: **IMPLEMENTED** (2026-09-25, Phase 8). Code: `src/floodguard/backend/`
(`types`, `config`, `models`, `repositories`, `health`, `schemas`, `api`);
migrations: `migrations/` (Alembic, `0001_initial`); CLI: `scripts/migrate_db.py`;
tests: `tests/test_backend_*.py` + `tests/backend_helpers.py` (53 tests).

> Live PostgreSQL/PostGIS runtime verification is **BLOCKED** (Docker/WSL).
> Everything below the runtime line is statically verified (PG-dialect DDL
> assertions) and behaviorally verified on SQLite (same models, FK pragma
> on). No live-runtime claim is made.

---

## 1. Schema (Existing Identities Only)

| Table | Identity | Source contract |
|---|---|---|
| `sites` | `fg_site_id` PK (UUIDv5) | Station master §1a |
| `sensors` | `fg_sensor_id` PK; unique `(fg_site_id, sensor_type)` | Station master §1a (never names) |
| `sensor_thresholds` | `fg_threshold_id` PK (capture-versioned) | Station master §1a |
| `observations` | PK `(source, fg_sensor_id, measurement_type, observation_time_utc)` | Data dictionary §1g |
| `predictions` | `prediction_id` PK; unique `(sensor, horizon, origin, family, run)` | Phase 5/6 lineage |
| `alerts` | `alert_id` PK (schema only; delivery is Phase 11) | TASKS.md Phase 8/11 |
| `ingest_batches` | `batch_id` PK | Raw-ingestion manifest |

CHECK value sets are composed from `station_master.SensorType/ThresholdType`
at import time — SQL cannot drift from Python (tested).

## 2. Hard Rules Preserved

- **Thresholds:** `NORMAL + eligible` rejected; Waspada/Amaran/Bahaya require
  `fg_label_eligible = TRUE`; thresholds stored with capture provenance and
  served as `CURRENT_THRESHOLD_REFERENCE_ONLY`; no SQL joins history to
  current thresholds as valid.
- **Time:** `observation_time_raw` / `_local` / `_utc` / `first_retrieved_at`
  are distinct `TIMESTAMPTZ` columns; `UNSPECIFIED_ASSUMED` default keeps the
  `Asia/Kuala_Lumpur` assumption explicit; observation time is never the
  retrieval time; API rejects naive inputs and emits tz-aware outputs.
- **Missing data:** NULL values + quality flags (never zero); conflicts raise
  `ConflictError` (raw text, tz status and schema version participate in
  identity; earliest retrieval wins by design).
- **Idempotency:** identical replays are no-ops for sites/sensors/thresholds/
  observations; concurrent races surface retryable `RepositoryError`.
- **Predictions:** `run_id` NOT NULL (`persistence`/`rule` are explicit
  states); site must match the sensor's site; `predicted_label` is
  binary-or-NULL; `/api/v1/model` always answers `NO_ELIGIBLE_MODEL`
  (a stored `model_family="production"` label can never flip it).

## 3. PostGIS

Coordinates stored as lon/lat numerics (verbatim decimals) plus a
`geometry(POINT,4326)` column on PostgreSQL (WKT text on other dialects via
`Wgs84Point`; SRID 4326 inferred, documented everywhere). Binds carry
EWKT `SRID=4326` so SRID 0 can never land in the typmod column; reads parse
2D WKB/EWKB back to WKT. GIST index on `geom` (plain index elsewhere).
Bounding-box reads use degree predicates (no metric math in degrees); no
nearest-station hydrology invented.

## 4. Migrations

Alembic, fixed IDs (`0001_initial`, linear chain tested). `upgrade` creates
the PostGIS extension on PostgreSQL only, then all tables; `downgrade` drops
them (explicitly destructive). `0001` asserts `SCHEMA_VERSION ==
backend_schema/v1` at runtime so model drift forces a new revision instead
of falsifying history. `scripts/migrate_db.py` (`upgrade`/`downgrade`/
`current`) refuses downgrade in production and without
`--confirm-destructive`, never prints secrets, and disposes engines.

## 5. Repository / API Layout

`backend/config.py` (env-only credentials, redaction, startup validation) →
`models.py` → `repositories.py` (parameter-bound ORM only) → `api.py`
(explicit Pydantic models, structured errors, generic storage detail).
`/health` is DB-free liveness; `/ready` checks connectivity (+ PostGIS on
PostgreSQL). No SQL string concatenation (heuristic test enforced).

## 6. ORM Lesson (UOW Flush Ordering)

Every FK now has a covering `relationship()`: without one, SQLAlchemy may
emit child INSERTs before parents and trip FK enforcement (found via
deterministic SQLite failures; PostgreSQL enforces always). Pinned by
`test_single_flush_orders_parents_before_children` (+ all-child-tables
variant). Savepoints are deliberately not used for insert recovery
(`begin_nested()` flushes pending state on entry; objects added inside can
escape outer rollback) — races surface retryable errors instead.

## 7. Testing

SQLite (FK pragma on, shared-cache for TestClient threads) for behavior;
PostgreSQL-dialect DDL assertions for PostGIS specifics; marked integration
tests (extension, SRID, GIST bbox, migration round-trip) skip without a
reachable test database. Synthetic fixtures only; no JPS data in fixtures.

## 8. Reviewer Findings (Independent Audits)

First audit: **2 HIGH + 8 MEDIUM + 8 LOW** — all fixed: `/api/v1/model`
cannot be flipped by stored labels; EWKT SRID binds + WKB reads; conflict
identity extended (raw/tz/schema); `Prediction.site`/`Sensor.alerts`
relationships + cross-site guard; generic storage errors; frozen `0001`
via schema pin; downgrade confirmation + production refusal; naive-datetime
rejection + tz-aware outputs; true upserts; loopback-only test fixture;
W/A/B eligibility, label domain, coordinate ranges; race retry semantics;
injection-heuristic hardening; error sanitization + engine disposal;
measurement-translation documentation.
