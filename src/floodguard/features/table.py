"""Feature table builder for FloodGuard Penang.

Constructs unified model-ready feature tables per valid prediction origin t:
- Combines modality features (rainfall, water level), temporal encodings, static station metadata,
  and weather forecasts.
- Separates feature computation from future target construction.
- Preserves lineage and stable row identity:
  (source, fg_sensor_id, fg_site_id, prediction_origin_utc).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any

from floodguard.features.paired import build_paired_site_features
from floodguard.features.rainfall import (
    RainfallFeatureConfig,
    extract_rainfall_features,
)
from floodguard.features.spatial import extract_station_spatial_features
from floodguard.features.temporal import compute_temporal_features
from floodguard.features.water_level import (
    WaterLevelFeatureConfig,
    extract_water_level_features,
)
from floodguard.features.weather import (
    WeatherForecastRecord,
    compute_weather_features_for_origin,
)


def build_feature_table(
    observation_rows: Iterable[Mapping[str, Any]],
    *,
    station_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    threshold_reference: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    forecast_records: Sequence[WeatherForecastRecord] | None = None,
    rainfall_config: RainfallFeatureConfig | None = None,
    water_level_config: WaterLevelFeatureConfig | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build unified feature tables for rainfall sensors, water-level sensors, and paired sites.

    Returns:
        {
            "rainfall_features": list of dicts,
            "water_level_features": list of dicts,
            "paired_site_features": list of dicts,
        }
    """
    rows_list = list(observation_rows)
    meta_map = station_metadata or {}
    fcs = list(forecast_records or [])

    # 1. Extract base modality features
    rf_features = extract_rainfall_features(rows_list, config=rainfall_config)
    wl_features = extract_water_level_features(
        rows_list, threshold_reference=threshold_reference, config=water_level_config
    )

    # 2. Enrich rainfall rows with temporal, spatial, and weather features
    enriched_rf: list[dict[str, Any]] = []
    for r in rf_features:
        row = dict(r)
        sensor_id = row["fg_sensor_id"]
        local_t = datetime.fromisoformat(row["prediction_origin_local"])
        origin_utc = datetime.fromisoformat(row["prediction_origin_utc"])

        # Spatial
        meta = meta_map.get(sensor_id, {})
        spatial = extract_station_spatial_features(meta)
        row.update(spatial)

        # Temporal
        temporal = compute_temporal_features(local_t)
        row.update(temporal)

        # Weather forecast
        weather = compute_weather_features_for_origin(origin_utc, meta.get("district"), fcs)
        row.update(weather)

        enriched_rf.append(row)

    # 3. Enrich water-level rows with temporal, spatial, and weather features
    enriched_wl: list[dict[str, Any]] = []
    for w in wl_features:
        row = dict(w)
        sensor_id = row["fg_sensor_id"]
        local_t = datetime.fromisoformat(row["prediction_origin_local"])
        origin_utc = datetime.fromisoformat(row["prediction_origin_utc"])

        # Spatial
        meta = meta_map.get(sensor_id, {})
        spatial = extract_station_spatial_features(meta)
        row.update(spatial)

        # Temporal
        temporal = compute_temporal_features(local_t)
        row.update(temporal)

        # Weather forecast
        weather = compute_weather_features_for_origin(origin_utc, meta.get("district"), fcs)
        row.update(weather)

        enriched_wl.append(row)

    # 4. Build paired site features
    paired_features = build_paired_site_features(enriched_rf, enriched_wl)

    return {
        "rainfall_features": enriched_rf,
        "water_level_features": enriched_wl,
        "paired_site_features": paired_features,
    }


def join_features_and_labels(
    features: Sequence[Mapping[str, Any]],
    label_evaluations: Sequence[Mapping[str, Any]],
    *,
    key_field: str = "fg_sensor_id",
) -> list[dict[str, Any]]:
    """Join features and multi-horizon target labels on (key_field, prediction_origin_utc).

    LEAKAGE GUARD: Target fields are appended as targets only; feature columns are untouched.
    """
    labels_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for ev in label_evaluations:
        k = (ev[key_field], ev["origin_utc"])
        if k not in labels_by_key:
            labels_by_key[k] = {}
        h = ev["target_horizon_minutes"]
        h_prefix = f"target_plus_{h}m"
        labels_by_key[k][f"{h_prefix}_status"] = ev["target_status"]
        labels_by_key[k][f"{h_prefix}_future_level_m"] = ev.get("future_water_level_m")
        labels_by_key[k][f"{h_prefix}_delta_level_m"] = ev.get("delta_water_level_m")
        labels_by_key[k][f"{h_prefix}_rate_m_per_h"] = ev.get("rate_to_horizon_m_per_h")

        thresh_labels = ev.get("threshold_labels", {})
        for t_key, t_info in thresh_labels.items():
            labels_by_key[k][f"{h_prefix}_exceed_{t_key}"] = (
                1
                if t_info.get("is_exceedance")
                else (0 if t_info.get("is_exceedance") is False else None)
            )
            labels_by_key[k][f"{h_prefix}_escalate_{t_key}"] = (
                1
                if t_info.get("is_escalation")
                else (0 if t_info.get("is_escalation") is False else None)
            )

    joined: list[dict[str, Any]] = []
    for f in features:
        row = dict(f)
        k = (f[key_field], f["prediction_origin_utc"])
        target_info = labels_by_key.get(k, {})
        row.update(target_info)
        joined.append(row)

    return joined
