"""Classification and regression metrics with explicit undefined handling.

Rules:
- Accuracy is never the primary metric for flood classification.
- Undefined metrics (e.g. recall with zero positive events) stay explicitly
  undefined via ``NOT_EVALUABLE`` with a reason; they are never silently
  coerced to 0 and never treated as performance.
- Every result records TP/FP/TN/FN and an evidence level.
- Regression (MAE/RMSE) is horizon-specific and never mixed with
  classification metrics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Final

from floodguard.modeling import EVIDENCE_SYNTHETIC, NOT_EVALUABLE

METRICS_SCHEMA_VERSION: Final[str] = "metrics/v1"


@dataclass(frozen=True)
class ConfusionMatrix:
    """Binary confusion counts."""

    tp: int
    fp: int
    tn: int
    fn: int

    def to_dict(self) -> dict[str, Any]:
        return {"tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn}


@dataclass(frozen=True)
class ClassificationResult:
    """Horizon-specific classification evaluation."""

    horizon_minutes: int
    confusion: ConfusionMatrix
    recall: float | str
    precision: float | str
    f1: float | str
    false_negative_rate: float | str
    pr_auc: float | str
    accuracy: float | str
    support_positives: int
    support_negatives: int
    evidence_level: str = EVIDENCE_SYNTHETIC
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": METRICS_SCHEMA_VERSION,
            "horizon_minutes": self.horizon_minutes,
            "confusion": self.confusion.to_dict(),
            "recall": self.recall,
            "precision": self.precision,
            "f1": self.f1,
            "false_negative_rate": self.false_negative_rate,
            "pr_auc": self.pr_auc,
            "accuracy": self.accuracy,
            "support_positives": self.support_positives,
            "support_negatives": self.support_negatives,
            "evidence_level": self.evidence_level,
            "notes": list(self.notes),
        }


def confusion_matrix(y_true: list[int], y_pred: list[int]) -> ConfusionMatrix:
    """Compute TP/FP/TN/FN from aligned binary labels."""
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have equal length")
    tp = fp = tn = fn = 0
    for actual, predicted in zip(y_true, y_pred, strict=True):
        if actual == 1 and predicted == 1:
            tp += 1
        elif actual == 0 and predicted == 1:
            fp += 1
        elif actual == 0 and predicted == 0:
            tn += 1
        elif actual == 1 and predicted == 0:
            fn += 1
        else:
            raise ValueError(f"non-binary label pair: {(actual, predicted)}")
    return ConfusionMatrix(tp=tp, fp=fp, tn=tn, fn=fn)


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def average_precision_score_safe(y_true: list[int], y_score: list[float]) -> float | str:
    """PR-AUC via average precision; NOT_EVALUABLE when undefined."""
    if not y_true:
        return NOT_EVALUABLE
    positives = sum(y_true)
    if positives == 0 or positives == len(y_true):
        return NOT_EVALUABLE
    # Deterministic average-precision computation (no sklearn dependency).
    ranked = sorted(zip(y_score, y_true, strict=True), key=lambda p: -p[0])
    precision_sum = 0.0
    hits = 0
    for i, (_, label) in enumerate(ranked, start=1):
        if label == 1:
            hits += 1
            precision_sum += hits / i
    return precision_sum / positives


def classification_metrics(
    y_true: list[int],
    y_pred: list[int],
    y_score: list[float] | None,
    horizon_minutes: int,
    *,
    evidence_level: str = EVIDENCE_SYNTHETIC,
) -> ClassificationResult:
    """Evaluate one horizon; undefined metrics stay NOT_EVALUABLE."""
    if not (len(y_true) == len(y_pred) and (y_score is None or len(y_score) == len(y_true))):
        raise ValueError("y_true, y_pred and y_score must align")
    cm = confusion_matrix(y_true, y_pred)
    positives = sum(y_true)
    negatives = len(y_true) - positives

    recall = _safe_div(float(cm.tp), float(cm.tp + cm.fn))
    precision = _safe_div(float(cm.tp), float(cm.tp + cm.fp))
    fnr = _safe_div(float(cm.fn), float(cm.fn + cm.tp))
    if recall is None or precision is None:
        f1: float | str = NOT_EVALUABLE
    elif (recall + precision) == 0:
        # Defined denominators with zero overlap: real zero, not undefined.
        f1 = 0.0
    else:
        f1 = 2 * recall * precision / (recall + precision)
    pr_auc: float | str
    if y_score is not None:
        pr_auc = average_precision_score_safe(y_true, list(y_score))
    else:
        pr_auc = NOT_EVALUABLE
    accuracy: float | str = (cm.tp + cm.tn) / len(y_true) if y_true else NOT_EVALUABLE

    notes: list[str] = []
    if not y_true:
        notes.append("empty evaluation set: all metrics NOT_EVALUABLE.")
    if positives == 0:
        notes.append("zero positive events: recall/F1/PR-AUC NOT_EVALUABLE.")
    if negatives == 0:
        notes.append("zero negative events: precision NOT_EVALUABLE when no predicted positives.")

    return ClassificationResult(
        horizon_minutes=horizon_minutes,
        confusion=cm,
        recall=recall if recall is not None else NOT_EVALUABLE,
        precision=precision if precision is not None else NOT_EVALUABLE,
        f1=f1,
        false_negative_rate=fnr if fnr is not None else NOT_EVALUABLE,
        pr_auc=pr_auc,
        accuracy=accuracy,
        support_positives=positives,
        support_negatives=negatives,
        evidence_level=evidence_level,
        notes=tuple(notes),
    )


@dataclass(frozen=True)
class RegressionResult:
    """Horizon-specific water-level forecast evaluation."""

    horizon_minutes: int
    mae_m: float | str
    rmse_m: float | str
    n: int
    evidence_level: str = EVIDENCE_SYNTHETIC

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": METRICS_SCHEMA_VERSION,
            "horizon_minutes": self.horizon_minutes,
            "mae_m": self.mae_m,
            "rmse_m": self.rmse_m,
            "n": self.n,
            "evidence_level": self.evidence_level,
        }


def regression_metrics(
    y_true_m: list[float],
    y_pred_m: list[float],
    horizon_minutes: int,
    *,
    evidence_level: str = EVIDENCE_SYNTHETIC,
) -> RegressionResult:
    """MAE/RMSE for one horizon; empty inputs are NOT_EVALUABLE."""
    if len(y_true_m) != len(y_pred_m):
        raise ValueError("y_true_m and y_pred_m must have equal length")
    if not y_true_m:
        return RegressionResult(
            horizon_minutes=horizon_minutes,
            mae_m=NOT_EVALUABLE,
            rmse_m=NOT_EVALUABLE,
            n=0,
            evidence_level=evidence_level,
        )
    errors = [abs(a - b) for a, b in zip(y_true_m, y_pred_m, strict=True)]
    mae = sum(errors) / len(errors)
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    return RegressionResult(
        horizon_minutes=horizon_minutes,
        mae_m=mae,
        rmse_m=rmse,
        n=len(y_true_m),
        evidence_level=evidence_level,
    )
