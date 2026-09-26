"""Kafka/MQTT justification decision (Phase 10, Task 5).

Verdict: NOT JUSTIFIED at the current scale.

Evidence (``data/metadata/jps/LIVE_ACCESS.md``):
- One state-level request returns many stations (56 rainfall + 22 water-level
  rows in 2 requests per poll).
- Recommended poll is 2 requests per 5 min (576/day); payloads ~31 KB + ~20 KB.
- Source cadence is 15 min (F2 sync) with async non-F2 updates on 5-min grid.
- Single-process scheduler -> raw store -> database meets latency needs with
  large headroom; no multi-consumer fan-out, no sub-minute SLA, no backpressure.

Adoption thresholds (revisit only when met):
- Sustained poll volume > 10x current (e.g. per-station polling or 1-min cadence);
- Multiple independent consumers needing the same live stream;
- At-least-once delivery across processes with ordering guarantees;
- Measured single-process ingestion lag exceeding the source cadence.

No streaming code is added. This module records the decision for tests/docs.
"""

from __future__ import annotations

from typing import Any, Final

DECISION: Final[str] = "NOT_JUSTIFIED"
DECISION_VERSION: Final[str] = "streaming_decision/v1"


def decide() -> dict[str, Any]:
    return {
        "decision": DECISION,
        "version": DECISION_VERSION,
        "architecture": "scheduler -> adapter -> permission gate -> HTTP -> raw -> DB",
        "requests_per_poll": 2,
        "requests_per_day_at_5min": 576,
        "source_cadence_minutes": 15,
        "revisit_thresholds": [
            "sustained volume > 10x current",
            "multiple independent stream consumers",
            "cross-process ordering/delivery guarantees required",
            "measured lag exceeds source cadence",
        ],
    }
