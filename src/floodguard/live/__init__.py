"""Phase 10 live ingestion: scheduled polling without streaming infrastructure.

Pipeline (simple, current scale)::

    scheduler
    -> source adapter (Phase 1/2 JPS parsers, reused)
    -> permission gate (JPS PERMISSION REQUIRED, default OFF)
    -> HTTP fetch (controlled client, bounded retry)
    -> raw immutable storage (write-once, manifest, duplicate detection)
    -> parse / normalize / validate (timestamps, station IDs, units, quality)
    -> idempotent repository write (Phase 8, transactional)
    -> run history + factual metrics/status

JPS network polling stays disabled unless an explicit local permission record
authorizes it. Tests use synthetic fixtures and mocked HTTP; no JPS calls.
"""

from __future__ import annotations
