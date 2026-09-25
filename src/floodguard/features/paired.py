"""Paired multi-sensor site feature extraction for FloodGuard Penang.

Extracts combined rainfall and water-level feature vectors for the 13 confirmed
shared monitoring sites where rainfall and water-level gauges share a physical fg_site_id.

Safety Rules:
- Only pairs sensors that share an exact verified fg_site_id in the Station Master.
- Never pairs by approximate name matching or cross-basin nearest neighbor.
- Preserves distinct rainfall_fg_sensor_id and water_level_fg_sensor_id in lineage.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from floodguard.features.registry import (
    REGISTRY,
    FeatureDefinition,
    FeatureFamily,
    LeakageClassification,
)


def register_paired_features() -> list[FeatureDefinition]:
    """Register paired multi-sensor site features into the global registry."""
    defs: list[FeatureDefinition] = [
        FeatureDefinition(
            name="paired_rainfall_sensor_id",
            family=FeatureFamily.PAIRED_SITE,
            description="Canonical fg_sensor_id of the paired rainfall sensor at shared site",
            measurement_type="LINEAGE_IDENTIFIER",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present for paired site record",
            point_in_time_semantics="Static verified site link",
            leakage_classification=LeakageClassification.STATIC_PROVENANCE_ASSUMED,
        ),
        FeatureDefinition(
            name="paired_water_level_sensor_id",
            family=FeatureFamily.PAIRED_SITE,
            description="Canonical fg_sensor_id of the paired water-level sensor at shared site",
            measurement_type="LINEAGE_IDENTIFIER",
            unit="unitless",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present for paired site record",
            point_in_time_semantics="Static verified site link",
            leakage_classification=LeakageClassification.STATIC_PROVENANCE_ASSUMED,
        ),
    ]

    for d in defs:
        if not REGISTRY.contains(d.name):
            REGISTRY.register(d)
    return defs


# Register default definitions
register_paired_features()


def build_paired_site_features(
    rainfall_features: Sequence[Mapping[str, Any]],
    water_level_features: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Join rainfall and water-level features for sensors at shared fg_site_id at origin t."""
    # Index rainfall features by (fg_site_id, prediction_origin_utc)
    rf_by_site_and_time: dict[tuple[str, str], Mapping[str, Any]] = {
        (r["fg_site_id"], r["prediction_origin_utc"]): r for r in rainfall_features
    }

    # Index water level features by (fg_site_id, prediction_origin_utc)
    wl_by_site_and_time: dict[tuple[str, str], Mapping[str, Any]] = {
        (w["fg_site_id"], w["prediction_origin_utc"]): w for w in water_level_features
    }

    # Common keys
    common_keys = sorted(set(rf_by_site_and_time.keys()) & set(wl_by_site_and_time.keys()))

    paired_rows: list[dict[str, Any]] = []
    for site_id, origin_utc in common_keys:
        rf_row = rf_by_site_and_time[(site_id, origin_utc)]
        wl_row = wl_by_site_and_time[(site_id, origin_utc)]

        entry: dict[str, Any] = {
            "source": rf_row["source"],
            "fg_site_id": site_id,
            "paired_rainfall_sensor_id": rf_row["fg_sensor_id"],
            "paired_water_level_sensor_id": wl_row["fg_sensor_id"],
            "prediction_origin_utc": origin_utc,
            "prediction_origin_local": rf_row["prediction_origin_local"],
        }

        # Include all rainfall features
        for k, v in rf_row.items():
            if k not in (
                "source",
                "fg_sensor_id",
                "fg_site_id",
                "prediction_origin_utc",
                "prediction_origin_local",
            ):
                entry[k] = v

        # Include all water level features
        for k, v in wl_row.items():
            if k not in (
                "source",
                "fg_sensor_id",
                "fg_site_id",
                "prediction_origin_utc",
                "prediction_origin_local",
            ):
                entry[k] = v

        paired_rows.append(entry)

    return paired_rows
