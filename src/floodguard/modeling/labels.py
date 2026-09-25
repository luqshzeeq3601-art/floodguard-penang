"""Supervised label extraction per horizon with missing-target safety.

Rules:
- Features and targets are constructed independently; this module only reads
  already-joined rows and never mutates feature columns.
- +30, +60, +120 minutes stay separate prediction problems.
- ``MISSING_FUTURE_TARGET`` rows are excluded from supervised loss/evaluation;
  they are never converted to negatives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from floodguard.modeling import HORIZONS_MINUTES, TARGET_EVALUATED

LABELS_SCHEMA_VERSION: Final[str] = "model_labels/v1"


@dataclass(frozen=True)
class HorizonLabels:
    """Supervised labels for one horizon."""

    horizon_minutes: int
    y: tuple[int, ...]
    row_indices: tuple[int, ...]
    positive_count: int
    negative_count: int
    missing_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LABELS_SCHEMA_VERSION,
            "horizon_minutes": self.horizon_minutes,
            "n": len(self.y),
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "missing_count": self.missing_count,
        }


def _label_column(horizon_minutes: int, task: str) -> str:
    return f"target_plus_{horizon_minutes}m_{task}"


def extract_horizon_labels(
    joined_rows: list[dict[str, Any]],
    horizon_minutes: int,
    *,
    task: str = "exceed_waspada",
) -> HorizonLabels:
    """Extract 0/1 labels for one horizon; missing targets excluded.

    The default task reads the Waspada exceedance label produced by
    ``join_features_and_labels``. Callers may pass e.g. ``escalate_waspada``
    or another threshold suffix; unknown columns count as missing.
    """
    if horizon_minutes not in HORIZONS_MINUTES:
        raise ValueError(f"unsupported horizon: {horizon_minutes}")
    status_col = f"target_plus_{horizon_minutes}m_status"
    label_col = _label_column(horizon_minutes, task)
    y: list[int] = []
    indices: list[int] = []
    missing = 0
    for i, row in enumerate(joined_rows):
        status = row.get(status_col)
        value = row.get(label_col)
        if status != TARGET_EVALUATED or value is None:
            # Covers MISSING_FUTURE_TARGET and any unevaluable origin.
            missing += 1
            continue
        y.append(1 if int(value) == 1 else 0)
        indices.append(i)
    positives = sum(y)
    return HorizonLabels(
        horizon_minutes=horizon_minutes,
        y=tuple(y),
        row_indices=tuple(indices),
        positive_count=positives,
        negative_count=len(y) - positives,
        missing_count=missing,
    )


def extract_regression_targets(
    joined_rows: list[dict[str, Any]],
    horizon_minutes: int,
) -> tuple[tuple[float, ...], tuple[int, ...], int]:
    """Extract future water-level deltas for one horizon (regression).

    Returns (targets, row_indices, missing_count). Missing targets excluded.
    """
    if horizon_minutes not in HORIZONS_MINUTES:
        raise ValueError(f"unsupported horizon: {horizon_minutes}")
    status_col = f"target_plus_{horizon_minutes}m_status"
    delta_col = f"target_plus_{horizon_minutes}m_delta_level_m"
    targets: list[float] = []
    indices: list[int] = []
    missing = 0
    for i, row in enumerate(joined_rows):
        if row.get(status_col) != TARGET_EVALUATED or row.get(delta_col) is None:
            missing += 1
            continue
        targets.append(float(str(row[delta_col])))
        indices.append(i)
    return tuple(targets), tuple(indices), missing
