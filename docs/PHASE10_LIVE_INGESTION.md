# Phase 10 — Live Ingestion Contract: Scheduled Polling Without Streaming

Status: **IMPLEMENTED** (2026-09-26, Phase 10). Library: `src/floodguard/live/`
(`config`, `http`, `scheduler`, `runner`, `runs`, `metrics`, `staleness`,
`idempotency`, `streaming`, `inference`, `persistence`); CLI:
`scripts/run_live_poll.py`; API: `/api/v1/monitoring/ingestion` (Phase 8
extension); tests: `tests/test_live_*.py` (8 files, 40 tests).

> JPS polling and bulk retrieval remain **PERMISSION REQUIRED**. The permission
> gate runs before any socket use; without a valid local permission record the
> run reports `BLOCKED_PERMISSION` and performs no network I/O. Committed
> tests use synthetic fixtures + mocked HTTP only; one unintended real JPS GET
> during smoke development is disclosed in `docs/PHASE10_COMPLETION.md` §3.

---

## 1. Architecture

```text
scheduler (single-run + loop, overlap lock, graceful stop)
→ source adapter (Phase 1/2 JPS parsers, reused; rainfall/water-level separate)
→ permission gate (JPS PERMISSION REQUIRED, default OFF)
→ HTTP fetch (controlled client, timeouts, bounded size, allowlisted URLs only)
→ raw immutable storage (write-once, manifest, DUPLICATE detection)
→ parse / normalize / validate (timestamps, station IDs, units, quality)
→ idempotent repository write (Phase 8, transactional)
→ run history + factual metrics/status
```

No Kafka, MQTT or distributed streaming (Task 5: `NOT_JUSTIFIED`; see §7).
No persistent distributed queue. Live and historical backfill stay separate;
history retrieval remains permission-gated and explicit.

## 2. Scheduler / Polling (Task 1)

- Configurable polling interval (`FLOODGUARD_LIVE_POLL_INTERVAL_SECONDS`,
  minimum 60 s, default 300 s); actual permitted frequency follows JPS
  authorization, not the default.
- Deterministic single-run function (`PollScheduler.run_once`, also the
  manual-debug entry point via `scripts/run_live_poll.py`); loop only in
  `run_forever` with interruptible wait (no busy-loop).
- No overlapping duplicate runs (non-blocking lock → `SKIPPED_OVERLAP`).
- Explicit failure states (`SUCCEEDED`, `PARTIAL`, `FAILED`, `DUPLICATE`,
  `BLOCKED_PERMISSION`, `SKIPPED_OVERLAP`); bounded retry in the HTTP layer;
  graceful shutdown on SIGINT/SIGTERM; no background work in unit tests.

## 3. Ingestion Data Flow (Task 1)

Every successful acquisition retains: source, dataset, retrieval timestamp,
payload hash, parser/schema version, run ID, station/source identifiers,
quality result and canonical observation identity.

- Reuses Phase 1/2 JPS adapters; no separate live parsers; excluded fields
  never promoted (via `validation.observations`).
- Raw preservation: payload hash, write-once raw storage, manifest status,
  atomic writes, duplicate detection; repeated identical payloads create no
  duplicate observations.
- Timestamp safety: raw text, normalized time, retrieval time and timezone
  evidence preserved; retrieval never substituted for observation;
  `UNSPECIFIED_ASSUMED` where the source publishes no zone.
- Station identity: `fg_site_id`/`fg_sensor_id` via `SensorMapper` only;
  no name-based joins; unknown IDs quarantined, never added to the master.
- Units/quality: existing normalization and quality logic; missing markers
  (`-9999`, `ERROR`, blank, `Tiada Data`) preserved; zero rainfall stays valid
  zero; no invented physical-range rejection.
- Database: Phase 8 repositories only, transactional batches; on DB failure
  raw is preserved, downstream failure is marked, replay is safe.
- Logging: structured with run ID/source/dataset/status/error category;
  no credentials, tokens, payloads, paths or keys. Raw payload lives in raw
  storage, not logs.
- Config: environment only; safe defaults keep JPS OFF; `.env.example` holds
  placeholders.

## 4. Latency / Metrics (Task 2)

Factual engineering metrics only (`live.metrics`, `/api/v1/monitoring/ingestion`,
dashboard `get_ingestion_metrics`): poll attempts, successful/failed/blocked
polls, records received, canonical inserts, duplicates, quarantined rows,
total/mean duration, per-stage seconds, last successful retrieval. No
freshness "healthy" verdicts; no high-cardinality station labels.

## 5. Stale-Station Detection (Task 3)

Versioned policy `stale_policy/v1` (`live.staleness`), source/sensor-aware,
based on documented cadence (`LIVE_ACCESS.md`): F2 expected 15 min, others
unknown. Evaluable sensors use `stale_after_minutes` (default 60 = four missed
F2 batches plus lag); unknown-cadence sensors yield `UNKNOWN`, never stale.
`INVALID` for missing/future times. Boundaries tested. The dashboard keeps
reporting factual age-in-minutes only; provisional `FRESH/DELAYED/STALE`
30/180 thresholds are not revived.

## 6. Idempotency (Task 4)

- Raw key `source + dataset + partition + payload_sha256` → `DUPLICATE`, no
  artifact rewrite; different bytes at an existing path raise (never
  overwrite).
- Canonical PK `(source, sensor, type, instant)` → identical replays no-op,
  conflicts raise `ConflictError` (never silent merge). Value scale is
  quantized to `Numeric(12,4)` so replays compare equal.
- Scheduler overlap lock; restart recovery via recognized raw hashes and
  idempotent DB re-ensure (DUPLICATE re-derives from stored raw artifacts).
- Helpers in `live.idempotency`; contract version `live_idempotency/v1`.

## 7. Streaming Decision (Task 5)

**NOT_JUSTIFIED.** 2 requests per 5-min poll (576/day), ~50 KB total, 15-min
source cadence; single-process scheduler meets needs with headroom. No
multi-consumer fan-out, sub-minute SLA or backpressure. Revisit thresholds are
recorded in `live.streaming.decide()`; no streaming code or dependencies added.

## 8. Live Inference (Task 6)

MLOps status `NO_ELIGIBLE_MODEL` / `NO_ELIGIBLE_FORECAST_MODEL` is enforced.
`live.inference.run_live_inference` returns `SKIPPED_NO_ELIGIBLE_MODEL` per
+30/+60/+120 horizon with lineage; no model is invoked, no synthetic model is
substituted. Observations are stored and dashboards updated without
predictions. The call site is preserved for a future eligible registry model.

## 9. Prediction Persistence (Task 7)

`live.persistence` stores inference outputs via `PredictionRepository`
(transactional, no SQL from scheduler code): `run_id` NOT NULL, site-must-match
sensor, binary-or-NULL labels, lineage preserved, never a false production
claim (`/api/v1/model` stays `NO_ELIGIBLE_MODEL`). The live no-model path
persists zero rows; baseline/candidate rows are exercised explicitly in tests.

## 10. Security

Allowlisted source endpoints only (SSRF guard); permission checked before
sockets; timeouts and bounded response size; no arbitrary URLs; no secrets in
code, logs, runs or API responses; no unrestricted ingestion-trigger endpoint
(TASKS.md does not require one); DB writes via ORM only; parser failures are
categorized, never retried indefinitely; path traversal prevented by fixed
storage layout and validated partitions.

## 11. Testing

Offline, deterministic, CPU-only; mocked HTTP and synthetic fixtures; no
Docker/Postgres, JPS or real data. Covers: successful poll, permission
blocked, timeout, transient retry, permanent failure, malformed/empty payload,
duplicate, conflicting observation, unknown station, missing markers, zero
rainfall, timestamp normalization, DB failure after raw, replay recovery,
overlapping runs, configuration, scheduler single iteration, graceful stop and
the no-model path. No wall-clock waiting (injected timing).

## 12. Limitations

- Real JPS polling is externally blocked (permission); Phase 10 is
  software-complete, execution-blocked for live JPS.
- Live PostgreSQL/PostGIS runtime remains BLOCKED (Docker/WSL); behavioral
  verification is on SQLite plus PG-dialect checks from Phase 8.
- No validated production model or forecaster exists; live inference always
  skips.
- No alert delivery (Phase 11); ingestion only preserves records/events.
