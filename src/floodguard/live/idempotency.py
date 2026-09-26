"""End-to-end idempotency guarantees for live ingestion (Phase 10, Task 4).

Layers (each tested):

- Raw: ``source + dataset + partition + payload_sha256`` key in the manifest.
  A repeated identical payload appends a ``DUPLICATE`` entry and writes no
  artifact (``ingestion.pipeline``). Different bytes at an existing path raise
  ``ImmutableArtifactError``; nothing is overwritten.
- Canonical: ``(source, fg_sensor_id, measurement_type, observation_time_utc)``
  PK in the database. Identical replays are no-ops
  (``ObservationRepository.insert`` returns ``duplicate_identical``);
  materially different content raises ``ConflictError`` (never silent merge).
- Run: repeated scheduler executions against the same payload re-ensure the DB
  from stored raw artifacts (``runner.LivePollRunner``), so a DB failure after
  raw storage recovers on replay without duplicating successful rows.
- Scheduler: non-blocking lock rejects overlapping runs (``SKIPPED_OVERLAP``);
  restart recovery holds because raw hashes remain recognized and successful
  observations remain idempotent.

This module documents the contract and exposes small helpers for tests and
operations. No new ID scheme: ``fg_site_id``/``fg_sensor_id`` only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from floodguard.ingestion import manifest

IDEMPOTENCY_CONTRACT_VERSION = "live_idempotency/v1"


def is_raw_duplicate(
    raw_root: Path, source: str, dataset: str, partition: str | None, payload_sha256: str
) -> bool:
    """True when this exact payload already has a SUCCEEDED raw batch."""
    return manifest.find_succeeded(raw_root, source, dataset, partition, payload_sha256) is not None


def describe_contract() -> dict[str, Any]:
    return {
        "contract_version": IDEMPOTENCY_CONTRACT_VERSION,
        "raw_key": "source + dataset + partition + payload_sha256",
        "canonical_key": "(source, fg_sensor_id, measurement_type, observation_time_utc)",
        "conflict_policy": "fail loudly (ConflictError), never silent overwrite",
        "overlap_policy": "non-blocking scheduler lock -> SKIPPED_OVERLAP",
        "restart_policy": "raw hashes recognized; DB re-ensured idempotently",
    }
