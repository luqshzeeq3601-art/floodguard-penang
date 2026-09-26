"""Focused polling scheduler (Phase 10, Task 1).

One deterministic single-run function plus an optional loop with graceful
shutdown. No overlapping duplicate runs (non-blocking lock), explicit failure
state, bounded retries (in the HTTP layer), no busy-loop (config minimum
interval), and no background work during unit tests (loop only runs when
explicitly called).
"""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from floodguard.live.runs import RunRecord, RunStatus, new_run_id, utc_now_iso

LOG = logging.getLogger("floodguard.live.scheduler")

SingleRunFn = Callable[[], list[RunRecord]]
SleepFn = Callable[[float], None]


@dataclass(frozen=True)
class SchedulerConfig:
    poll_interval_seconds: float = 300.0


class PollScheduler:
    """Single-process scheduler with overlap protection and graceful stop."""

    def __init__(
        self,
        run_once_fn: SingleRunFn,
        config: SchedulerConfig | None = None,
    ) -> None:
        self._run_once_fn = run_once_fn
        self._config = config or SchedulerConfig()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._running = False

    @property
    def stop_requested(self) -> bool:
        return self._stop.is_set()

    def request_stop(self) -> None:
        self._stop.set()

    def run_once(self) -> list[RunRecord] | RunRecord:
        """Deterministic single iteration; also the manual-debug entry point.

        Returns a SKIPPED_OVERLAP record when another run holds the lock.
        """
        if not self._lock.acquire(blocking=False):
            LOG.info("live poll skipped: overlapping run in progress")
            now = utc_now_iso()
            return RunRecord(
                run_id=new_run_id(),
                source="SCHEDULER",
                dataset="all",
                started_at=now,
                ended_at=now,
                status=RunStatus.SKIPPED_OVERLAP,
                error_category="OVERLAPPING_RUN",
                duration_seconds=0.0,
            )
        self._running = True
        try:
            return self._run_once_fn()
        finally:
            self._running = False
            self._lock.release()

    def run_forever(
        self,
        *,
        sleep: SleepFn | None = None,  # kept for API compat; wait uses the stop event
        max_iterations: int | None = None,
    ) -> list[Any]:
        """Loop until stop is requested (SIGINT/SIGTERM) or max_iterations.

        Unit tests must call run_once(), never this loop.
        """
        _ = sleep
        try:
            signal.signal(signal.SIGINT, lambda *_: self.request_stop())
            signal.signal(signal.SIGTERM, lambda *_: self.request_stop())
        except (ValueError, OSError):
            pass  # not the main thread (tests) — stop flag still works
        outcomes: list[Any] = []
        iterations = 0
        while not self._stop.is_set():
            outcomes.append(self.run_once())
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                break
            # No busy-loop: always wait the configured interval (interruptible).
            self._stop.wait(self._config.poll_interval_seconds)
        return outcomes
