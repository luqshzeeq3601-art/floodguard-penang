"""Feature registry and schema definitions for FloodGuard Penang (Phase 4).

Every model feature must be registered with complete metadata:
- Name, family, description, measurement type, unit
- Lookback window duration and minimum coverage requirement
- Explicit null semantics and point-in-time temporal boundaries
- Leakage classification

Ensures zero undocumented magic column names and enables automated feature dictionary generation.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Final

SCHEMA_VERSION: Final[str] = "features/v1"


class FeatureFamily(StrEnum):
    RAINFALL_ROLLING = "RAINFALL_ROLLING"
    ANTECEDENT_RAINFALL = "ANTECEDENT_RAINFALL"
    WATER_LEVEL_DELTA = "WATER_LEVEL_DELTA"
    WATER_LEVEL_RATE = "WATER_LEVEL_RATE"
    WATER_LEVEL_WINDOW = "WATER_LEVEL_WINDOW"
    THRESHOLD_REFERENCE = "THRESHOLD_REFERENCE"
    WEATHER_FORECAST = "WEATHER_FORECAST"
    TEMPORAL = "TEMPORAL"
    STATION_BASIN = "STATION_BASIN"
    PAIRED_SITE = "PAIRED_SITE"


class LeakageClassification(StrEnum):
    STRICT_POINT_IN_TIME = "STRICT_POINT_IN_TIME"
    STATIC_PROVENANCE_ASSUMED = "STATIC_PROVENANCE_ASSUMED"
    CURRENT_THRESHOLD_REFERENCE_ONLY = "CURRENT_THRESHOLD_REFERENCE_ONLY"


@dataclass(frozen=True)
class FeatureDefinition:
    """Complete specification of a single feature."""

    name: str
    family: FeatureFamily
    description: str
    measurement_type: str
    unit: str
    lookback_minutes: int
    min_coverage_ratio: float
    null_semantics: str
    point_in_time_semantics: str
    leakage_classification: LeakageClassification

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["family"] = self.family.value
        d["leakage_classification"] = self.leakage_classification.value
        return d


class FeatureRegistry:
    """Registry maintaining all valid feature specifications."""

    def __init__(self) -> None:
        self._features: dict[str, FeatureDefinition] = {}

    def register(self, feature: FeatureDefinition) -> FeatureDefinition:
        if feature.name in self._features:
            raise ValueError(f"Feature {feature.name!r} already registered")
        self._features[feature.name] = feature
        return feature

    def register_many(self, features: Iterable[FeatureDefinition]) -> None:
        for f in features:
            self.register(f)

    def get(self, name: str) -> FeatureDefinition:
        if name not in self._features:
            raise KeyError(f"Feature {name!r} is not registered")
        return self._features[name]

    def contains(self, name: str) -> bool:
        return name in self._features

    def list_features(self) -> list[FeatureDefinition]:
        return sorted(self._features.values(), key=lambda f: (f.family.value, f.name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "feature_count": len(self._features),
            "features": [f.to_dict() for f in self.list_features()],
        }

    def filter_by_family(self, family: FeatureFamily) -> list[FeatureDefinition]:
        return [f for f in self.list_features() if f.family == family]


# Global registry instance
REGISTRY: FeatureRegistry = FeatureRegistry()
