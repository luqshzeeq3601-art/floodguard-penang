"""Factual ingestion metrics (Phase 10, Task 2).

Engineering facts only: poll attempts, successes, failures, records received,
canonical inserts, duplicates, quarantined rows, durations and last successful
retrieval. No freshness "healthy" verdicts (no validated policy here) and no
high-cardinality labels (no per-station series).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from floodguard.live.runs import RunRecord, RunStatus

METRICS_SCHEMA_VERSION = "live_metrics/v1"


@dataclass
class MetricsCollector:
    """In-memory factual counters (per process; persisted via RunStore)."""

    poll_attempts: int = 0
    successful_polls: int = 0
    failed_polls: int = 0
    blocked_polls: int = 0
    records_received: int = 0
    canonical_inserted: int = 0
    duplicates: int = 0
    quarantined: int = 0
    total_duration_seconds: float = 0.0
    last_successful_retrieval: str | None = None
    _stage_seconds: dict[str, float] = field(default_factory=dict)

    def record_run(
        self,
        record: RunRecord,
        *,
        canonical_inserted: int = 0,
        stage_seconds: dict[str, float] | None = None,
    ) -> None:
        self.poll_attempts += 1
        if record.status in (RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.DUPLICATE):
            self.successful_polls += 1
            if record.ended_at is not None and (
                self.last_successful_retrieval is None
                or record.ended_at > self.last_successful_retrieval
            ):
                self.last_successful_retrieval = record.ended_at
        elif record.status is RunStatus.BLOCKED_PERMISSION:
            self.blocked_polls += 1
        elif record.status is RunStatus.SKIPPED_OVERLAP:
            pass
        else:
            self.failed_polls += 1
        self.records_received += record.records_fetched
        self.canonical_inserted += canonical_inserted
        self.duplicates += record.duplicate_count
        self.quarantined += record.quarantined_count
        if record.duration_seconds is not None:
            self.total_duration_seconds += record.duration_seconds
        for stage, seconds in (stage_seconds or {}).items():
            self._stage_seconds[stage] = self._stage_seconds.get(stage, 0.0) + seconds

    def snapshot(self) -> dict[str, Any]:
        avg = self.total_duration_seconds / self.poll_attempts if self.poll_attempts else None
        return {
            "schema_version": METRICS_SCHEMA_VERSION,
            "poll_attempts": self.poll_attempts,
            "successful_polls": self.successful_polls,
            "failed_polls": self.failed_polls,
            "blocked_polls": self.blocked_polls,
            "records_received": self.records_received,
            "canonical_records_inserted": self.canonical_inserted,
            "duplicates": self.duplicates,
            "quarantined_rows": self.quarantined,
            "total_ingestion_duration_seconds": self.total_duration_seconds,
            "mean_poll_duration_seconds": avg,
            "stage_seconds": dict(sorted(self._stage_seconds.items())),
            "last_successful_retrieval": self.last_successful_retrieval,
        }
