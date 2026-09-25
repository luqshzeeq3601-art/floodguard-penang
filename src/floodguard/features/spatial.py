"""Station and basin static spatial feature engineering for FloodGuard Penang.

Strict provenance metadata extraction from the Station Master (sites.csv + sensors.csv).
Covers:
- Phase 4 Task 7: Station/basin features (coordinates, district, main basin, sensor type)

Safety and Lineage Rules:
- Static metadata is sourced exclusively from the verified Station Master table.
- Coordinates are verified WGS84 degrees.
- Never fabricates unverified spatial hazard layers or distances.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from floodguard.features.registry import (
    REGISTRY,
    FeatureDefinition,
    FeatureFamily,
    LeakageClassification,
)

DECIMALS = 6


def _r(x: float | None) -> float | None:
    if x is None:
        return None
    return round(float(x), DECIMALS) + 0.0


def register_spatial_features() -> list[FeatureDefinition]:
    """Register all station/basin spatial features into the global registry."""
    defs: list[FeatureDefinition] = [
        FeatureDefinition(
            name="station_latitude",
            family=FeatureFamily.STATION_BASIN,
            description="Station latitude in WGS84 decimal degrees",
            measurement_type="STATIC_COORDINATE",
            unit="degrees",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Null if latitude not available in station master",
            point_in_time_semantics="Static verified metadata from Station Master",
            leakage_classification=LeakageClassification.STATIC_PROVENANCE_ASSUMED,
        ),
        FeatureDefinition(
            name="station_longitude",
            family=FeatureFamily.STATION_BASIN,
            description="Station longitude in WGS84 decimal degrees",
            measurement_type="STATIC_COORDINATE",
            unit="degrees",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Null if longitude not available in station master",
            point_in_time_semantics="Static verified metadata from Station Master",
            leakage_classification=LeakageClassification.STATIC_PROVENANCE_ASSUMED,
        ),
        FeatureDefinition(
            name="station_district",
            family=FeatureFamily.STATION_BASIN,
            description="Administrative district (e.g. Timur Laut, Barat Daya, SPU, SPT, SPS)",
            measurement_type="STATIC_ADMIN_METADATA",
            unit="categorical",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Null if district not available",
            point_in_time_semantics="Static verified metadata from Station Master",
            leakage_classification=LeakageClassification.STATIC_PROVENANCE_ASSUMED,
        ),
        FeatureDefinition(
            name="station_main_basin",
            family=FeatureFamily.STATION_BASIN,
            description="Main hydrological river basin (e.g. Sg. Pinang, Sg. Perai, Sg. Juru)",
            measurement_type="STATIC_HYDRO_METADATA",
            unit="categorical",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Null if main basin not available",
            point_in_time_semantics="Static verified metadata from Station Master",
            leakage_classification=LeakageClassification.STATIC_PROVENANCE_ASSUMED,
        ),
        FeatureDefinition(
            name="station_sensor_type",
            family=FeatureFamily.STATION_BASIN,
            description="Sensor measurement modality (RAINFALL or WATER_LEVEL)",
            measurement_type="STATIC_SENSOR_METADATA",
            unit="categorical",
            lookback_minutes=0,
            min_coverage_ratio=1.0,
            null_semantics="Always present",
            point_in_time_semantics="Static verified metadata from Station Master",
            leakage_classification=LeakageClassification.STATIC_PROVENANCE_ASSUMED,
        ),
    ]

    for d in defs:
        if not REGISTRY.contains(d.name):
            REGISTRY.register(d)
    return defs


# Register default definitions
register_spatial_features()


def extract_station_spatial_features(
    station_meta: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Extract static spatial/basin features for a station given its station master entry."""
    if not station_meta:
        return {
            "station_latitude": None,
            "station_longitude": None,
            "station_district": None,
            "station_main_basin": None,
            "station_sensor_type": None,
        }

    lat = station_meta.get("latitude")
    lon = station_meta.get("longitude")

    lat_f = float(lat) if lat is not None and str(lat).strip() != "" else None
    lon_f = float(lon) if lon is not None and str(lon).strip() != "" else None

    return {
        "station_latitude": _r(lat_f),
        "station_longitude": _r(lon_f),
        "station_district": station_meta.get("district"),
        "station_main_basin": station_meta.get("main_basin"),
        "station_sensor_type": station_meta.get("sensor_type"),
    }
