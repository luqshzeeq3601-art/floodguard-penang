"""Probability calibration on training/validation only (Phase 5 task 7).

Rules:
- Fit calibration on training/validation only; never on test.
- Preserve chronological ordering (no shuffling into the fit).
- Require enough event support; zero-positive real data is insufficient.
- Synthetic verification is allowed; synthetic calibration is never reported
  as real model performance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from floodguard.modeling import NOT_EVALUABLE

CALIBRATION_SCHEMA_VERSION: Final[str] = "calibration/v1"


@dataclass(frozen=True)
class CalibrationResult:
    """Fitted calibration with frozen method."""

    method: str
    horizon_minutes: int
    n_fit: int
    n_positives_fit: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CALIBRATION_SCHEMA_VERSION,
            "method": self.method,
            "horizon_minutes": self.horizon_minutes,
            "n_fit": self.n_fit,
            "n_positives_fit": self.n_positives_fit,
        }


def fit_calibration(
    scores_fit: list[float],
    y_fit: list[int],
    horizon_minutes: int,
    *,
    method: str = "sigmoid",
    min_positives: int = 10,
) -> tuple[Any | None, CalibrationResult | dict[str, Any]]:
    """Fit a calibration map on fit-only scores (train/val, chronological)."""
    if method not in ("sigmoid", "isotonic"):
        raise ValueError("method must be 'sigmoid' or 'isotonic'")
    if len(scores_fit) != len(y_fit) or not y_fit:
        return None, {
            "status": NOT_EVALUABLE,
            "reason": "empty or misaligned calibration fit inputs.",
            "horizon_minutes": horizon_minutes,
        }
    positives = sum(y_fit)
    if positives < min_positives or positives == len(y_fit):
        return None, {
            "status": NOT_EVALUABLE,
            "reason": (
                f"calibration needs >= {min_positives} positives and both classes; "
                f"observed {positives}/{len(y_fit)}."
            ),
            "horizon_minutes": horizon_minutes,
        }
    from sklearn.isotonic import IsotonicRegression  # type: ignore[import-untyped]
    from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]

    if method == "sigmoid":
        estimator = LogisticRegression(random_state=42)
        rows = [[s] for s in scores_fit]
        estimator.fit(rows, y_fit)
    else:
        estimator = IsotonicRegression(out_of_bounds="clip")
        estimator.fit(scores_fit, y_fit)
    result = CalibrationResult(
        method=method,
        horizon_minutes=horizon_minutes,
        n_fit=len(y_fit),
        n_positives_fit=positives,
    )
    return estimator, result


def apply_calibration(estimator: Any, method: str, scores: list[float]) -> list[float]:
    """Apply a frozen calibration map (test-time)."""
    if method == "sigmoid":
        rows = [[s] for s in scores]
        return [float(p) for p in estimator.predict_proba(rows)[:, 1]]
    return [float(p) for p in estimator.predict(scores)]
