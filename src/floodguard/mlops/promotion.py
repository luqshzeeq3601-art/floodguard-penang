"""Promotion gate (Phase 7 task 7: Promotion gate).

A candidate advances to production only when ALL of the following hold:

1. automated acceptance checks pass on the artifact;
2. a baseline comparison record exists and favors the candidate (or ties
   with a documented operational justification - never accuracy-only for
   classification: recall, false-negative rate and PR-AUC must be reviewed);
3. the Phase 5/6 eligibility gate passes for the candidate's evidence
   (``NO_ELIGIBLE_MODEL`` / ``NO_ELIGIBLE_FORECAST_MODEL`` blocks);
4. evidence is ``REAL_PREDICTIVE_EVALUATION`` (synthetic/local stays in
   staging at best);
5. a leakage-audit attestation is recorded (tests + reviewer refs);
6. a model card is recorded.

Anything else returns ``BLOCK`` with explicit reasons. Synthetic validation
can never promote: the gate preserves ``NO_ELIGIBLE_MODEL`` until real
evidence supports otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from floodguard.mlops import EVIDENCE_REAL, GATE_BLOCK, GATE_PROMOTE

PROMOTION_SCHEMA_VERSION: Final[str] = "mlops_promotion/v1"

CLASSIFICATION_REQUIRED_METRICS: Final[tuple[str, ...]] = (
    "recall",
    "false_negative_rate",
    "pr_auc",
)
FORECASTING_REQUIRED_METRICS: Final[tuple[str, ...]] = ("mae_m", "rmse_m")


@dataclass(frozen=True)
class PromotionInput:
    """Evidence bundle for one promotion decision."""

    run_id: str
    model_family: str
    task: str = "forecasting"  # "classification" | "forecasting"
    evidence_level: str = ""
    acceptance_passed: bool = False
    acceptance_detail: str = ""
    baseline_comparison: str = (
        "absent"  # "favors_candidate" | "tie_justified" | "favors_baseline" | "absent"
    )
    baseline_metrics_reviewed: tuple[str, ...] = ()
    eligibility_status: str = (
        "unknown"  # "ELIGIBLE" | "NO_ELIGIBLE_MODEL" | "NO_ELIGIBLE_FORECAST_MODEL" | ...
    )
    leakage_audit_ref: str = ""
    model_card_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "model_family": self.model_family,
            "task": self.task,
            "evidence_level": self.evidence_level,
            "acceptance_passed": self.acceptance_passed,
            "acceptance_detail": self.acceptance_detail,
            "baseline_comparison": self.baseline_comparison,
            "baseline_metrics_reviewed": list(self.baseline_metrics_reviewed),
            "eligibility_status": self.eligibility_status,
            "leakage_audit_ref": self.leakage_audit_ref,
            "model_card_ref": self.model_card_ref,
        }


@dataclass(frozen=True)
class PromotionVerdict:
    """Structured PROMOTE/BLOCK decision with reasons."""

    verdict: str
    reasons: tuple[str, ...]
    run_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROMOTION_SCHEMA_VERSION,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "run_id": self.run_id,
        }


def decide_promotion(candidate: PromotionInput) -> PromotionVerdict:
    """Evaluate the promotion bundle; BLOCK unless everything holds."""
    blockers: list[str] = []

    if candidate.task not in ("classification", "forecasting"):
        blockers.append(f"unknown task {candidate.task!r}; cannot determine required metrics")
    if not candidate.acceptance_passed:
        blockers.append(f"acceptance checks failed: {candidate.acceptance_detail or 'see report'}")
    if candidate.baseline_comparison not in ("favors_candidate", "tie_justified"):
        blockers.append(
            "no favorable baseline comparison recorded "
            f"(status: {candidate.baseline_comparison}); accuracy-only promotion is forbidden"
        )
    else:
        reviewed = {m.strip().lower() for m in candidate.baseline_metrics_reviewed}
        required = (
            CLASSIFICATION_REQUIRED_METRICS
            if candidate.task == "classification"
            else FORECASTING_REQUIRED_METRICS
        )
        missing = [m for m in required if m not in reviewed]
        if missing:
            blockers.append(
                f"baseline review misses required {candidate.task} metrics: {missing}; "
                "accuracy-only promotion is forbidden"
            )
    if candidate.eligibility_status != "ELIGIBLE":
        blockers.append(
            f"eligibility gate does not pass (status: {candidate.eligibility_status}); "
            "NO_ELIGIBLE_MODEL is preserved"
        )
    if candidate.evidence_level != EVIDENCE_REAL:
        blockers.append(
            f"evidence is {candidate.evidence_level}, not REAL_PREDICTIVE_EVALUATION; "
            "synthetic/local runs stay in staging at best"
        )
    if not candidate.leakage_audit_ref:
        blockers.append("no leakage-audit attestation recorded")
    if not candidate.model_card_ref:
        blockers.append("no model card recorded")

    if blockers:
        return PromotionVerdict(
            verdict=GATE_BLOCK, reasons=tuple(blockers), run_id=candidate.run_id
        )
    return PromotionVerdict(
        verdict=GATE_PROMOTE,
        reasons=("all promotion criteria satisfied",),
        run_id=candidate.run_id,
    )
