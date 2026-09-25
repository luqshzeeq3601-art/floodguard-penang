"""Model feature eligibility from the authoritative Phase 4 registry.

Rules:
- Use the registry; never select every numeric field automatically.
- Explicitly exclude identifiers, raw source IDs, dataset hashes, provenance
  columns, label columns, future target columns, and anything unsafe.
- ``CURRENT_THRESHOLD_REFERENCE_ONLY`` features are excluded from standard
  historical training by default; an explicit opt-in experiment may enable
  them with documentation.
- Station/site identifiers stay identifiers; UUIDs/JPS IDs never become
  numeric predictive features.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from floodguard.features import paired as _paired  # noqa: F401
from floodguard.features import rainfall as _rainfall  # noqa: F401
from floodguard.features import spatial as _spatial  # noqa: F401
from floodguard.features import temporal as _temporal  # noqa: F401
from floodguard.features import water_level as _water_level  # noqa: F401
from floodguard.features import weather as _weather  # noqa: F401
from floodguard.features.registry import REGISTRY, FeatureFamily, LeakageClassification

ELIGIBILITY_SCHEMA_VERSION: Final[str] = "feature_eligibility/v1"

# Column names that may appear in joined feature/label rows but must never
# become model inputs.
ALWAYS_EXCLUDED_COLUMNS: Final[tuple[str, ...]] = (
    "source",
    "fg_sensor_id",
    "fg_site_id",
    "prediction_origin_utc",
    "prediction_origin_local",
    "observation_time_utc",
    "observation_time_local",
    "origin_utc",
    "target_utc",
    "dataset_version",
    "dataset_hash",
    "observations_sha256",
    "observations_hash",
    "station_master_sha256",
    "threshold_reference_sha256",
    "jps_internal_id",
    "jps_display_station_id",
    "paired_rainfall_sensor_id",
    "paired_water_level_sensor_id",
    "station_district",
    "station_main_basin",
    "station_sensor_type",
    # Static per-station coordinates memorize stations instead of learning
    # transferable hydrology; excluded from standard training (review M4).
    "station_latitude",
    "station_longitude",
)

TARGET_PREFIX: Final[str] = "target_plus_"
LABEL_COLUMN_MARKERS: Final[tuple[str, ...]] = (
    "target_",
    "label_",
    "is_exceedance",
    "is_escalation",
    "future_water_level",
    "delta_water_level",
)


@dataclass(frozen=True)
class EligibilityPolicy:
    """Policy for selecting model-eligible features."""

    include_threshold_reference: bool = False
    experiment_note: str = "standard historical training"


@dataclass(frozen=True)
class EligibilityResult:
    """Eligible feature names with exclusion accounting."""

    eligible_features: tuple[str, ...]
    excluded_threshold_reference: tuple[str, ...]
    excluded_identifiers: tuple[str, ...]
    excluded_targets: tuple[str, ...]
    schema_version: str = ELIGIBILITY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "eligible_features": list(self.eligible_features),
            "excluded_threshold_reference": list(self.excluded_threshold_reference),
            "excluded_identifiers": list(self.excluded_identifiers),
            "excluded_targets": list(self.excluded_targets),
        }


def _is_target_column(name: str) -> bool:
    lowered = name.lower()
    return name.startswith(TARGET_PREFIX) or any(m in lowered for m in LABEL_COLUMN_MARKERS)


def select_eligible_features(
    candidate_columns: list[str],
    policy: EligibilityPolicy | None = None,
) -> EligibilityResult:
    """Select eligible features for standard historical training."""
    pol = policy or EligibilityPolicy()
    eligible: list[str] = []
    excluded_thresh: list[str] = []
    excluded_ids: list[str] = []
    excluded_targets: list[str] = []

    for name in candidate_columns:
        if _is_target_column(name):
            excluded_targets.append(name)
            continue
        if name in ALWAYS_EXCLUDED_COLUMNS:
            excluded_ids.append(name)
            continue
        if REGISTRY.contains(name):
            definition = REGISTRY.get(name)
            if (
                definition.leakage_classification
                == LeakageClassification.CURRENT_THRESHOLD_REFERENCE_ONLY
                and not pol.include_threshold_reference
            ):
                excluded_thresh.append(name)
                continue
            if definition.family == FeatureFamily.PAIRED_SITE:
                excluded_ids.append(name)
                continue
            if definition.family == FeatureFamily.STATION_BASIN and name in {
                "station_district",
                "station_main_basin",
                "station_sensor_type",
            }:
                excluded_ids.append(name)
                continue
            eligible.append(name)
            continue
        # Unknown non-registry columns: treat conservatively.
        # Numeric-looking engineered columns not in the registry are excluded
        # to prevent accidental identifier/provenance leakage.
        excluded_ids.append(name)

    return EligibilityResult(
        eligible_features=tuple(sorted(eligible)),
        excluded_threshold_reference=tuple(sorted(excluded_thresh)),
        excluded_identifiers=tuple(sorted(excluded_ids)),
        excluded_targets=tuple(sorted(excluded_targets)),
    )


def eligible_numeric_matrix(
    rows: list[dict[str, Any]],
    eligible_features: list[str],
) -> tuple[list[list[float | None]], list[str]]:
    """Build a numeric matrix (None = missing) for eligible features only."""
    matrix: list[list[float | None]] = []
    for row in rows:
        values: list[float | None] = []
        for name in eligible_features:
            raw = row.get(name)
            if raw is None:
                values.append(None)
            elif isinstance(raw, bool):
                values.append(1.0 if raw else 0.0)
            elif isinstance(raw, (int, float)):
                values.append(float(raw))
            else:
                # Categorical/text feature: not numeric; mark missing here.
                # Categorical encoding is handled by preprocessing.
                values.append(None)
        matrix.append(values)
    return matrix, list(eligible_features)
