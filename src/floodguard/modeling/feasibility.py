"""Real-data feasibility gate and independent episode support.

Centralizes event-support feasibility for Phase 5. Before fitting any real
flood classifier, callers must pass this gate. With the current local
captures (zero positive flood-proxy events) the gate fails with a structured
reason; that failure is an expected result, not an error.

Episode counting treats contiguous positive origins (adjacent 5-minute
origins) as one episode; many rows from one flood episode are not many
independent events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from typing import Any, Final

from floodguard.modeling import HORIZONS_MINUTES, INSUFFICIENT_EVENT_SUPPORT

FEASIBILITY_SCHEMA_VERSION: Final[str] = "feasibility/v1"


@dataclass(frozen=True)
class FeasibilityConfig:
    """Minimum real-data requirements for classifier training/evaluation.

    Minima apply per horizon (the minimum across +30/+60/+120 must satisfy
    them), so support cannot be triple-counted by summing horizons (review M1).
    """

    min_positive_episodes: int = 10
    min_positives: int = 30
    min_negatives: int = 30
    cadence_minutes: int = 5

    def __post_init__(self) -> None:
        if self.min_positive_episodes < 1:
            raise ValueError("min_positive_episodes must be >= 1")
        if self.min_positives < 1:
            raise ValueError("min_positives must be >= 1")


@dataclass(frozen=True)
class HorizonSupport:
    """Event support for one horizon."""

    horizon_minutes: int
    positives: int
    negatives: int
    episodes: int
    has_both_classes: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "horizon_minutes": self.horizon_minutes,
            "positives": self.positives,
            "negatives": self.negatives,
            "episodes": self.episodes,
            "has_both_classes": self.has_both_classes,
        }


@dataclass(frozen=True)
class FeasibilityResult:
    """Structured feasibility verdict."""

    feasible: bool
    status: str
    reason: str
    horizons: tuple[HorizonSupport, ...]
    total_positives: int
    total_negatives: int
    total_episodes: int
    evidence_level: str = "LOCAL_REAL_DATA_DIAGNOSTIC"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": FEASIBILITY_SCHEMA_VERSION,
            "feasible": self.feasible,
            "status": self.status,
            "reason": self.reason,
            "horizons": [h.to_dict() for h in self.horizons],
            "total_positives": self.total_positives,
            "total_negatives": self.total_negatives,
            "total_episodes": self.total_episodes,
            "evidence_level": self.evidence_level,
        }


def _count_episodes(sorted_times: list[datetime], cadence_minutes: int) -> int:
    if not sorted_times:
        return 0
    episodes = 1
    for prev, current in pairwise(sorted_times):
        gap = (current - prev).total_seconds() / 60.0
        # Contiguous 5-minute origins belong to one episode; a larger gap or
        # any interruption starts a new episode.
        if gap > cadence_minutes * 1.5:
            episodes += 1
    return episodes


def assess_feasibility(
    joined_rows: list[dict[str, Any]],
    config: FeasibilityConfig | None = None,
    *,
    task: str = "exceed_waspada",
    time_field: str = "prediction_origin_utc",
) -> FeasibilityResult:
    """Assess whether real classifier training/evaluation is allowed."""
    cfg = config or FeasibilityConfig()
    supports: list[HorizonSupport] = []
    for horizon in HORIZONS_MINUTES:
        status_col = f"target_plus_{horizon}m_status"
        label_col = f"target_plus_{horizon}m_{task}"
        positives = 0
        negatives = 0
        positive_times: list[datetime] = []
        for row in joined_rows:
            if row.get(status_col) != "TARGET_EVALUATED":
                continue
            value = row.get(label_col)
            if value is None:
                continue
            if int(value) == 1:
                positives += 1
                positive_times.append(datetime.fromisoformat(str(row[time_field])))
            else:
                negatives += 1
        episodes = _count_episodes(sorted(positive_times), cfg.cadence_minutes)
        supports.append(
            HorizonSupport(
                horizon_minutes=horizon,
                positives=positives,
                negatives=negatives,
                episodes=episodes,
                has_both_classes=positives > 0 and negatives > 0,
            )
        )

    min_positives = min(s.positives for s in supports)
    min_negatives = min(s.negatives for s in supports)
    min_episodes = min(s.episodes for s in supports)
    total_positives = sum(s.positives for s in supports)
    total_negatives = sum(s.negatives for s in supports)
    total_episodes = sum(s.episodes for s in supports)

    if min_positives < cfg.min_positives:
        return FeasibilityResult(
            feasible=False,
            status=INSUFFICIENT_EVENT_SUPPORT,
            reason=(
                f"weakest horizon has only {min_positives} positive labels "
                f"(need >= {cfg.min_positives} per horizon); "
                "NO REAL FLOOD CLASSIFICATION MODEL IS EMPIRICALLY VALIDATED YET."
            ),
            horizons=tuple(supports),
            total_positives=total_positives,
            total_negatives=total_negatives,
            total_episodes=total_episodes,
        )
    if min_episodes < cfg.min_positive_episodes:
        return FeasibilityResult(
            feasible=False,
            status=INSUFFICIENT_EVENT_SUPPORT,
            reason=(
                f"weakest horizon has only {min_episodes} independent positive episodes "
                f"(need >= {cfg.min_positive_episodes} per horizon); rows from one "
                "episode are not independent events."
            ),
            horizons=tuple(supports),
            total_positives=total_positives,
            total_negatives=total_negatives,
            total_episodes=total_episodes,
        )
    if min_negatives < cfg.min_negatives:
        return FeasibilityResult(
            feasible=False,
            status=INSUFFICIENT_EVENT_SUPPORT,
            reason=(
                f"weakest horizon has only {min_negatives} negatives "
                f"(need >= {cfg.min_negatives} per horizon)."
            ),
            horizons=tuple(supports),
            total_positives=total_positives,
            total_negatives=total_negatives,
            total_episodes=total_episodes,
        )
    return FeasibilityResult(
        feasible=True,
        status="FEASIBLE",
        reason="minimum event support satisfied.",
        horizons=tuple(supports),
        total_positives=total_positives,
        total_negatives=total_negatives,
        total_episodes=total_episodes,
    )
