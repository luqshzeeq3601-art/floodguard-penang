"""Decision-threshold selection on validation data only (frozen for test).

Rules:
- Optimize using training/validation data only; freeze the threshold; evaluate
  once on held-out test data. Never tune the threshold on the test set.
- With insufficient real event support, code is tested synthetically and real
  threshold optimization is NOT_EVALUABLE.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from floodguard.modeling import NOT_EVALUABLE

THRESHOLDS_SCHEMA_VERSION: Final[str] = "thresholds/v1"


@dataclass(frozen=True)
class ThresholdSelection:
    """Frozen operating threshold chosen on validation data."""

    threshold: float
    horizon_minutes: int
    validation_recall: float | str
    validation_precision: float | str
    validation_f1: float | str
    criterion: str = "max_f1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": THRESHOLDS_SCHEMA_VERSION,
            "threshold": self.threshold,
            "horizon_minutes": self.horizon_minutes,
            "validation_recall": self.validation_recall,
            "validation_precision": self.validation_precision,
            "validation_f1": self.validation_f1,
            "criterion": self.criterion,
        }


def _prf(y_true: list[int], y_pred: list[int]) -> tuple[float | str, float | str, float | str]:
    tp = sum(1 for a, b in zip(y_true, y_pred, strict=True) if a == 1 and b == 1)
    fp = sum(1 for a, b in zip(y_true, y_pred, strict=True) if a == 0 and b == 1)
    fn = sum(1 for a, b in zip(y_true, y_pred, strict=True) if a == 1 and b == 0)
    recall: float | str = tp / (tp + fn) if (tp + fn) else NOT_EVALUABLE
    precision: float | str = tp / (tp + fp) if (tp + fp) else NOT_EVALUABLE
    if isinstance(recall, str) or isinstance(precision, str) or (recall + precision) == 0:
        return recall, precision, NOT_EVALUABLE
    return recall, precision, 2 * recall * precision / (recall + precision)


def select_threshold_on_validation(
    y_val: list[int],
    scores_val: list[float],
    horizon_minutes: int,
    *,
    criterion: str = "max_f1",
    grid: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9),
) -> ThresholdSelection | dict[str, Any]:
    """Choose an operating threshold from validation scores only."""
    if criterion != "max_f1":
        raise ValueError("only 'max_f1' criterion is supported in Phase 5")
    if not y_val or len(y_val) != len(scores_val):
        return {
            "status": NOT_EVALUABLE,
            "reason": "empty or misaligned validation inputs.",
            "horizon_minutes": horizon_minutes,
        }
    if sum(y_val) == 0 or sum(y_val) == len(y_val):
        return {
            "status": NOT_EVALUABLE,
            "reason": "validation needs both classes for threshold selection.",
            "horizon_minutes": horizon_minutes,
        }
    best_threshold = 0.5
    best_f1 = -1.0
    best_prf: tuple[float | str, float | str, float | str] = (
        NOT_EVALUABLE,
        NOT_EVALUABLE,
        NOT_EVALUABLE,
    )
    for candidate in grid:
        preds = [1 if s >= candidate else 0 for s in scores_val]
        recall, precision, f1 = _prf(y_val, preds)
        score = f1 if isinstance(f1, float) else -1.0
        if score > best_f1:
            best_f1 = score
            best_threshold = candidate
            best_prf = (recall, precision, f1)
    recall, precision, f1 = best_prf
    return ThresholdSelection(
        threshold=best_threshold,
        horizon_minutes=horizon_minutes,
        validation_recall=recall,
        validation_precision=precision,
        validation_f1=f1,
        criterion=criterion,
    )


def apply_frozen_threshold(scores: list[float], threshold: float) -> list[int]:
    """Apply a frozen threshold (test-time, single evaluation)."""
    return [1 if s >= threshold else 0 for s in scores]
