"""LSTM/GRU justification gate (Phase 6 task 4: LSTM/GRU only if justified).

Neural sequence models are justified only when sequence data volume and
validation support them. The gate below encodes the minimum as configurable
project guidelines (not universal law):

- at least ``min_train_samples`` training origins with complete lookback and
  exact-horizon targets;
- at least ``min_stations`` stations each covering ``min_covered_days`` days
  (a covered day = local date with >= 80% of 288 five-minute slots usable).

Current local evidence (two station-days, ~154 usable intervals) fails every
criterion, so the verdict is ``NOT_JUSTIFIED``: no PyTorch dependency is
added, no GPU execution is introduced, and no LSTM/GRU is trained. Training
remains genuinely blocked on multi-year permitted history, not on compute.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from floodguard.forecasting import NOT_JUSTIFIED

GATE_SCHEMA_VERSION: Final[str] = "sequence_gate/v1"


@dataclass(frozen=True)
class SequenceGateConfig:
    """Minimum data volume for neural sequence training."""

    min_train_samples: int = 1000
    min_stations: int = 2
    min_covered_days_per_station: int = 30

    def __post_init__(self) -> None:
        if self.min_train_samples < 1:
            raise ValueError("min_train_samples must be >= 1")
        if self.min_stations < 1:
            raise ValueError("min_stations must be >= 1")
        if self.min_covered_days_per_station < 1:
            raise ValueError("min_covered_days_per_station must be >= 1")


@dataclass(frozen=True)
class SequenceGateResult:
    """Structured justification verdict."""

    justified: bool
    status: str
    reason: str
    train_samples: int
    stations_meeting_coverage: int
    stations_required: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": GATE_SCHEMA_VERSION,
            "justified": self.justified,
            "status": self.status,
            "reason": self.reason,
            "train_samples": self.train_samples,
            "stations_meeting_coverage": self.stations_meeting_coverage,
            "stations_required": self.stations_required,
        }


def assess_sequence_justification(
    *,
    train_samples: int,
    stations_meeting_coverage: int,
    config: SequenceGateConfig | None = None,
) -> SequenceGateResult:
    """Decide whether LSTM/GRU training is justified by data volume."""
    cfg = config or SequenceGateConfig()
    if train_samples < cfg.min_train_samples:
        return SequenceGateResult(
            justified=False,
            status=NOT_JUSTIFIED,
            reason=(
                f"only {train_samples} training samples "
                f"(need >= {cfg.min_train_samples}); LSTM/GRU training is not "
                "justified and no neural dependency is added."
            ),
            train_samples=train_samples,
            stations_meeting_coverage=stations_meeting_coverage,
            stations_required=cfg.min_stations,
        )
    if stations_meeting_coverage < cfg.min_stations:
        return SequenceGateResult(
            justified=False,
            status=NOT_JUSTIFIED,
            reason=(
                f"only {stations_meeting_coverage} stations meet coverage "
                f"(need >= {cfg.min_stations} with >= {cfg.min_covered_days_per_station} "
                "covered days each)."
            ),
            train_samples=train_samples,
            stations_meeting_coverage=stations_meeting_coverage,
            stations_required=cfg.min_stations,
        )
    return SequenceGateResult(
        justified=True,
        status="JUSTIFIED",
        reason="minimum sequence-data volume satisfied.",
        train_samples=train_samples,
        stations_meeting_coverage=stations_meeting_coverage,
        stations_required=cfg.min_stations,
    )
