"""Ingestion latency/metrics tests (Phase 10, Task 2; offline, synthetic)."""

from __future__ import annotations

import pytest

from floodguard.live.metrics import MetricsCollector
from floodguard.live.runs import RunRecord, RunStatus, new_run_id, utc_now_iso

pytestmark = pytest.mark.usefixtures("no_network")


def _record(
    status: RunStatus,
    *,
    records_fetched: int = 0,
    records_accepted: int = 0,
    quarantined_count: int = 0,
    duplicate_count: int = 0,
    ended_at: str | None = None,
) -> RunRecord:
    now = utc_now_iso()
    return RunRecord(
        run_id=new_run_id(),
        source="SYN",
        dataset="syn",
        started_at=now,
        ended_at=ended_at if ended_at is not None else now,
        status=status,
        records_fetched=records_fetched,
        records_accepted=records_accepted,
        quarantined_count=quarantined_count,
        duplicate_count=duplicate_count,
        duration_seconds=1.0,
    )


def test_metrics_counts_and_latency_are_factual() -> None:
    metrics = MetricsCollector()
    metrics.record_run(
        _record(
            RunStatus.SUCCEEDED,
            records_fetched=10,
            records_accepted=8,
            quarantined_count=2,
            ended_at="2030-01-01T01:00:00+00:00",
        ),
        canonical_inserted=8,
        stage_seconds={"fetch": 0.5, "db_write": 0.3},
    )
    metrics.record_run(
        _record(RunStatus.FAILED, ended_at="2030-01-01T02:00:00+00:00"),
        stage_seconds={"fetch": 1.0},
    )
    metrics.record_run(_record(RunStatus.BLOCKED_PERMISSION))
    snap = metrics.snapshot()
    assert snap["poll_attempts"] == 3
    assert snap["successful_polls"] == 1
    assert snap["failed_polls"] == 1
    assert snap["blocked_polls"] == 1
    assert snap["records_received"] == 10
    assert snap["canonical_records_inserted"] == 8
    assert snap["quarantined_rows"] == 2
    assert snap["total_ingestion_duration_seconds"] == pytest.approx(3.0)
    assert snap["mean_poll_duration_seconds"] == pytest.approx(1.0)
    assert snap["stage_seconds"] == {"db_write": 0.3, "fetch": 1.5}
    # Last successful retrieval is a fact, never a health verdict.
    assert snap["last_successful_retrieval"] == "2030-01-01T01:00:00+00:00"
    assert "healthy" not in str(snap).lower()


def test_empty_metrics_snapshot_has_no_verdict() -> None:
    snap = MetricsCollector().snapshot()
    assert snap["poll_attempts"] == 0
    assert snap["mean_poll_duration_seconds"] is None
    assert snap["last_successful_retrieval"] is None
