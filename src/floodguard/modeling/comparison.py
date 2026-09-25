"""Model comparison eligibility and champion selection (Phase 5 task 9).

Rules:
- Compare runs only when dataset version, feature schema, label version,
  horizon, chronological split, and evaluation period all match.
- A model is selection-eligible only when minimum real event/data
  requirements hold. Otherwise return NO_ELIGIBLE_MODEL.
- Never select a "best model" merely because code produced a numeric score.
- With current real data (zero positives), the correct real result is
  NO_ELIGIBLE_MODEL — INSUFFICIENT_EVENT_SUPPORT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from floodguard.modeling import NO_ELIGIBLE_MODEL

COMPARISON_SCHEMA_VERSION: Final[str] = "comparison/v1"


@dataclass(frozen=True)
class RunIdentity:
    """Exact comparability key for one evaluated run."""

    dataset_version: str
    feature_schema_version: str
    label_version: str
    horizon_minutes: int
    split_definition: str
    evaluation_period: str
    model_family: str
    run_id: str

    def comparability_key(self) -> tuple[str, ...]:
        return (
            self.dataset_version,
            self.feature_schema_version,
            self.label_version,
            str(self.horizon_minutes),
            self.split_definition,
            self.evaluation_period,
        )


@dataclass(frozen=True)
class ScoredRun:
    """One evaluated run with its primary selection metric."""

    identity: RunIdentity
    recall: float | str
    pr_auc: float | str
    f1: float | str
    false_negative_rate: float | str
    n_positives_eval: int
    eligible: bool
    ineligibility_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.identity.dataset_version,
            "feature_schema_version": self.identity.feature_schema_version,
            "label_version": self.identity.label_version,
            "horizon_minutes": self.identity.horizon_minutes,
            "split_definition": self.identity.split_definition,
            "evaluation_period": self.identity.evaluation_period,
            "model_family": self.identity.model_family,
            "run_id": self.identity.run_id,
            "recall": self.recall,
            "pr_auc": self.pr_auc,
            "f1": self.f1,
            "false_negative_rate": self.false_negative_rate,
            "n_positives_eval": self.n_positives_eval,
            "eligible": self.eligible,
            "ineligibility_reason": self.ineligibility_reason,
        }


def check_comparable(runs: list[ScoredRun]) -> tuple[bool, str]:
    """Verify all runs share one comparability key."""
    if not runs:
        return False, "no runs to compare."
    keys = {r.identity.comparability_key() for r in runs}
    if len(keys) != 1:
        return False, f"runs span {len(keys)} distinct evaluation contexts; not comparable."
    return True, "runs share dataset/feature/label/horizon/split/period."


def select_champion(
    runs: list[ScoredRun],
    *,
    min_positives_eval: int = 10,
) -> dict[str, Any]:
    """Select a champion only among eligible runs; else NO_ELIGIBLE_MODEL."""
    comparable, reason = check_comparable(runs)
    if not comparable:
        return {
            "status": NO_ELIGIBLE_MODEL,
            "reason": reason,
            "schema_version": COMPARISON_SCHEMA_VERSION,
        }
    eligible = [r for r in runs if r.eligible and r.n_positives_eval >= min_positives_eval]
    if not eligible:
        return {
            "status": NO_ELIGIBLE_MODEL,
            "reason": (
                "no candidate satisfies minimum real event/data requirements "
                f"(need >= {min_positives_eval} positives in evaluation); "
                "NO REAL FLOOD CLASSIFICATION MODEL IS EMPIRICALLY VALIDATED YET."
            ),
            "schema_version": COMPARISON_SCHEMA_VERSION,
            "n_runs": len(runs),
        }

    def rank_key(run: ScoredRun) -> tuple[float, float, str]:
        recall = run.recall if isinstance(run.recall, float) else -1.0
        pr_auc = run.pr_auc if isinstance(run.pr_auc, float) else -1.0
        return (recall, pr_auc, run.identity.run_id)

    champion = max(eligible, key=rank_key)
    return {
        "status": "CHAMPION_SELECTED",
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "champion": champion.to_dict(),
        "n_runs": len(runs),
        "n_eligible": len(eligible),
    }
