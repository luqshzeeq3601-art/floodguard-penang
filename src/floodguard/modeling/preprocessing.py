"""Train-only preprocessing: scalers, encoders, imputers, class weights.

Rules:
- Fit exclusively on training data; apply unchanged to validation/test.
- Never use validation/test data to determine preprocessing, class weights,
  feature selection, thresholds, or calibration.
- Unseen categorical values at transform time map to a dedicated unknown
  bucket (never error, never refit).
- Missing numeric values use the training median (recorded in lineage).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Final

PREPROCESSING_SCHEMA_VERSION: Final[str] = "preprocessing/v1"


@dataclass(frozen=True)
class PreprocessingConfig:
    """Configuration for train-only preprocessing."""

    numeric_features: tuple[str, ...] = ()
    categorical_features: tuple[str, ...] = ()
    scale_numeric: bool = True


@dataclass
class FittedPreprocessor:
    """Fitted-on-train preprocessing state (immutable after fit)."""

    config: PreprocessingConfig
    numeric_medians: dict[str, float]
    numeric_means: dict[str, float]
    numeric_stds: dict[str, float]
    categorical_vocabularies: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PREPROCESSING_SCHEMA_VERSION,
            "config": asdict(self.config),
            "numeric_medians": dict(self.numeric_medians),
            "numeric_means": dict(self.numeric_means),
            "numeric_stds": dict(self.numeric_stds),
            "categorical_vocabularies": {
                k: list(v) for k, v in self.categorical_vocabularies.items()
            },
        }


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def fit_preprocessor(
    train_rows: list[dict[str, Any]], config: PreprocessingConfig
) -> FittedPreprocessor:
    """Fit preprocessing on training rows only."""
    medians: dict[str, float] = {}
    means: dict[str, float] = {}
    stds: dict[str, float] = {}
    for name in config.numeric_features:
        values = [
            float(r[name])
            for r in train_rows
            if r.get(name) is not None and isinstance(r.get(name), (int, float))
        ]
        if not values:
            medians[name] = 0.0
            means[name] = 0.0
            stds[name] = 1.0
            continue
        medians[name] = _median(values)
        mean = sum(values) / len(values)
        means[name] = mean
        var = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(var) if var > 0 else 1.0
        stds[name] = std if std > 0 else 1.0

    vocabs: dict[str, tuple[str, ...]] = {}
    for name in config.categorical_features:
        seen: list[str] = []
        for row in train_rows:
            raw = row.get(name)
            if raw is None:
                continue
            text = str(raw)
            if text not in seen:
                seen.append(text)
        vocabs[name] = tuple(sorted(seen))

    return FittedPreprocessor(
        config=config,
        numeric_medians=medians,
        numeric_means=means,
        numeric_stds=stds,
        categorical_vocabularies=vocabs,
    )


def transform_rows(rows: list[dict[str, Any]], fitted: FittedPreprocessor) -> list[list[float]]:
    """Transform rows with a frozen fitted preprocessor (train/val/test)."""
    output: list[list[float]] = []
    for row in rows:
        vector: list[float] = []
        for name in fitted.config.numeric_features:
            raw = row.get(name)
            value = (
                float(raw)
                if isinstance(raw, (int, float))
                else fitted.numeric_medians.get(name, 0.0)
            )
            if fitted.config.scale_numeric:
                mean = fitted.numeric_means.get(name, 0.0)
                std = fitted.numeric_stds.get(name, 1.0)
                vector.append((value - mean) / std)
            else:
                vector.append(value)
        for name in fitted.config.categorical_features:
            vocab = fitted.categorical_vocabularies.get(name, ())
            raw = row.get(name)
            text = str(raw) if raw is not None else "__MISSING__"
            # One-hot with trailing unknown bucket.
            for token in vocab:
                vector.append(1.0 if text == token else 0.0)
            vector.append(1.0 if text not in vocab else 0.0)
        output.append(vector)
    return output


def feature_names_out(fitted: FittedPreprocessor) -> list[str]:
    """Output column names for the transformed matrix."""
    names = list(fitted.config.numeric_features)
    for cat in fitted.config.categorical_features:
        vocab = fitted.categorical_vocabularies.get(cat, ())
        names.extend(f"{cat}={token}" for token in vocab)
        names.append(f"{cat}=__UNKNOWN__")
    return names


def train_class_weights(y_train: list[int]) -> dict[int, float] | None:
    """Inverse-frequency class weights from training labels only.

    Returns None when weights are not applicable (single-class training is
    handled upstream by the structured infeasibility guard).
    """
    if not y_train:
        return None
    classes = sorted(set(y_train))
    if len(classes) != 2:
        return None
    total = len(y_train)
    weights: dict[int, float] = {}
    for cls in classes:
        count = sum(1 for v in y_train if v == cls)
        weights[cls] = total / (len(classes) * count) if count else 1.0
    return weights
