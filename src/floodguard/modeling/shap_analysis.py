"""SHAP-compatible contribution analysis (Phase 5 task 8).

Scope: global contribution summary, per-event contribution, and
station-level aggregation for tabular classifiers. Contributions are framed
as "recent rainfall accumulation and rapid water-level rise contributed
strongly to the prediction" — never as causal proof.

Implementation policy (keeps normal tests offline/deterministic/CPU):
- When the optional ``shap`` package is installed, tree/linear explainers
  provide exact SHAP values for compatible models.
- Otherwise a deterministic permutation-contribution fallback (model-agnostic,
  seed-fixed) verifies the analysis plumbing without the heavy dependency.
- ``shap`` is therefore optional; normal ``pytest`` never requires it.
- Results carry an explicit ``method`` field (``shap_exact`` vs
  ``permutation_fallback``) and a SYNTHETIC evidence level in tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

SHAP_SCHEMA_VERSION: Final[str] = "shap/v1"


@dataclass(frozen=True)
class ContributionResult:
    """Feature contribution summary for one evaluated set."""

    method: str
    feature_names: tuple[str, ...]
    mean_abs_contribution: tuple[float, ...]
    rank: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SHAP_SCHEMA_VERSION,
            "method": self.method,
            "feature_names": list(self.feature_names),
            "mean_abs_contribution": list(self.mean_abs_contribution),
            "rank": list(self.rank),
        }


def _rank(names: list[str], scores: list[float]) -> list[str]:
    return [n for _, n in sorted(zip(scores, names, strict=True), key=lambda p: -p[0])]


def permutation_contributions(
    predict_proba_fn: Any,
    x_rows: list[list[float]],
    feature_names: list[str],
    *,
    seed: int = 42,
    n_repeats: int = 5,
) -> ContributionResult:
    """Deterministic permutation contribution fallback (no shap dependency)."""
    import random

    if not x_rows:
        raise ValueError("x_rows must be non-empty")
    rng = random.Random(seed)
    base = [float(p[1]) for p in predict_proba_fn(x_rows)]
    n_cols = len(feature_names)
    drops: list[float] = []
    for col in range(n_cols):
        col_values = [row[col] for row in x_rows]
        repeat_drops: list[float] = []
        for _ in range(n_repeats):
            shuffled = list(col_values)
            rng.shuffle(shuffled)
            perturbed = [list(r) for r in x_rows]
            for r, value in zip(perturbed, shuffled, strict=True):
                r[col] = value
            moved = [
                abs(b - float(p[1])) for b, p in zip(base, predict_proba_fn(perturbed), strict=True)
            ]
            repeat_drops.append(sum(moved) / len(moved))
        drops.append(sum(repeat_drops) / len(repeat_drops))
    return ContributionResult(
        method="permutation_fallback",
        feature_names=tuple(feature_names),
        mean_abs_contribution=tuple(drops),
        rank=tuple(_rank(list(feature_names), drops)),
    )


def shap_contributions(
    estimator: Any,
    x_rows: list[list[float]],
    feature_names: list[str],
) -> ContributionResult | dict[str, Any]:
    """Exact SHAP values when the optional ``shap`` package is available."""
    try:
        import shap  # type: ignore[import-not-found]
    except ImportError:
        return {
            "status": "SHAP_UNAVAILABLE",
            "reason": "optional 'shap' package is not installed; use permutation fallback.",
        }
    explainer = shap.Explainer(estimator, x_rows)
    values = explainer(x_rows)
    import numpy as np

    matrix = np.asarray(values.values)
    if matrix.ndim == 3:
        matrix = matrix[:, :, 1]
    mean_abs = [float(abs(matrix[:, i]).mean()) for i in range(len(feature_names))]
    _ = shap  # reference to satisfy linters about import usage depth
    return ContributionResult(
        method="shap_exact",
        feature_names=tuple(feature_names),
        mean_abs_contribution=tuple(mean_abs),
        rank=tuple(_rank(list(feature_names), mean_abs)),
    )
