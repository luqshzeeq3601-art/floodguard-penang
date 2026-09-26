"""Streaming decision tests (Phase 10, Task 5; offline)."""

from __future__ import annotations

import pytest

from floodguard.live import streaming

pytestmark = pytest.mark.usefixtures("no_network")


def test_streaming_not_justified_at_current_scale() -> None:
    decision = streaming.decide()
    assert decision["decision"] == "NOT_JUSTIFIED"
    assert decision["requests_per_poll"] == 2
    assert decision["requests_per_day_at_5min"] == 576
    assert decision["source_cadence_minutes"] == 15
    assert len(decision["revisit_thresholds"]) >= 3


def test_no_streaming_dependencies_introduced() -> None:
    import sys

    assert "kafka" not in sys.modules
    assert "mqtt" not in sys.modules
    try:
        import importlib

        importlib.import_module("kafka")
    except ImportError:
        pass
    else:  # pragma: no cover
        raise AssertionError("kafka package must not be required for Phase 10")
