"""Optional TimesFM benchmark harness (Phase 6 task 5).

Protocol without commitment: TimesFM is evaluated as a zero-shot benchmark
only when ALL of the following hold — the package is installed, a checkpoint
is explicitly provided on local disk, and inference fits the documented
budget. Otherwise a structured blocked result is returned.

Nothing here downloads checkpoints, installs frameworks, or requires a GPU.
Normal pytest uses a caller-supplied substitute predictor and stays offline.
No TimesFM superiority is assumed; it is one benchmark among baselines.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

TIMESFM_SCHEMA_VERSION: Final[str] = "timesfm_benchmark/v1"
STATUS_BLOCKED: Final[str] = "TIMESFM_BLOCKED"
STATUS_READY: Final[str] = "TIMESFM_READY"


@dataclass(frozen=True)
class TimesFMStatus:
    """Availability verdict for a TimesFM zero-shot benchmark run."""

    status: str
    reason: str
    package_installed: bool
    checkpoint_present: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TIMESFM_SCHEMA_VERSION,
            "status": self.status,
            "reason": self.reason,
            "package_installed": self.package_installed,
            "checkpoint_present": self.checkpoint_present,
        }


def check_timesfm_availability(checkpoint_dir: Path | None = None) -> TimesFMStatus:
    """Check whether a local zero-shot TimesFM run is possible (no downloads)."""
    try:
        import timesfm  # type: ignore[import-not-found]  # noqa: F401

        installed = True
    except ImportError:
        installed = False
    present = bool(checkpoint_dir is not None and checkpoint_dir.is_dir())
    if not installed:
        return TimesFMStatus(
            status=STATUS_BLOCKED,
            reason="timesfm package is not installed; benchmark needs explicit setup.",
            package_installed=False,
            checkpoint_present=present,
        )
    if not present:
        return TimesFMStatus(
            status=STATUS_BLOCKED,
            reason="no local checkpoint directory provided; downloads are out of scope.",
            package_installed=True,
            checkpoint_present=False,
        )
    return TimesFMStatus(
        status=STATUS_READY,
        reason="package and local checkpoint present; zero-shot run may proceed.",
        package_installed=True,
        checkpoint_present=True,
    )


def zero_shot_benchmark(
    history_levels: list[float],
    horizon_steps: int,
    predictor: Any | None = None,
) -> list[float]:
    """Run a zero-shot forecast via an injected predictor (tests stay offline).

    In production ``predictor`` would wrap a TimesFM model loaded from the
    local checkpoint; in tests it is a small deterministic substitute.
    """
    if predictor is None:
        raise ValueError("no predictor available: TimesFM checkpoint is not configured")
    if not history_levels:
        raise ValueError("history_levels must be non-empty")
    if horizon_steps < 1:
        raise ValueError("horizon_steps must be >= 1")
    result = predictor(history_levels, horizon_steps)
    values = [float(v) for v in result]
    if len(values) != horizon_steps:
        raise ValueError(f"predictor returned {len(values)} values for {horizon_steps} steps")
    return values
