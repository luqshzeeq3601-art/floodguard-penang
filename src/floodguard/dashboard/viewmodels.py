"""Pure page view-models: backend results in, render-ready structs out (no Streamlit).

Every builder returns a :class:`PageView` with an explicit state:

- ``ok``: content ready;
- ``empty``: valid response, zero items;
- ``unavailable``: backend unreachable/timed out;
- ``error``: malformed/validation/server failure;
- ``stale``: content loaded but flagged outdated by the caller (reserved).

Chart series carry ``None`` for missing slots so renderers break lines at
gaps (never connect across missing water levels); zeros stay ``0.0``.
Threshold tables carry provenance and the
``CURRENT_THRESHOLD_REFERENCE_ONLY`` marker; NORMAL never appears.
Model/forecast states surface ``NO_ELIGIBLE_MODEL`` /
``NO_ELIGIBLE_FORECAST_MODEL`` verbatim with evidence labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from floodguard.dashboard import NO_FORECAST_MODEL, NO_MODEL
from floodguard.dashboard.client import (
    RESULT_EMPTY,
    RESULT_OK,
    RESULT_UNAVAILABLE,
    ApiResult,
)
from floodguard.dashboard.formatting import evidence_label

STATE_OK: Final[str] = "ok"
STATE_EMPTY: Final[str] = "empty"
STATE_UNAVAILABLE: Final[str] = "unavailable"
STATE_ERROR: Final[str] = "error"
STATE_STALE: Final[str] = "stale"


@dataclass(frozen=True)
class PageView:
    """Render-ready page state (framework-free)."""

    title: str
    state: str
    summary: dict[str, Any] = field(default_factory=dict)
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    series: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    notices: tuple[str, ...] = ()


def _pass_through(result: ApiResult, title: str) -> PageView | None:
    """Map non-ok backend states to page states (None means proceed)."""
    if result.state == RESULT_OK:
        return None
    if result.state == RESULT_EMPTY:
        return PageView(title=title, state=STATE_EMPTY, notices=("No records returned.",))
    if result.state == RESULT_UNAVAILABLE:
        return PageView(
            title=title,
            state=STATE_UNAVAILABLE,
            notices=("Backend unavailable. Check the API service and retry.",),
        )
    return PageView(
        title=title,
        state=STATE_ERROR,
        notices=(f"Backend request failed ({result.state}): {result.message}",),
    )


def _parse_instant(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    # Naive strings are unresolvable (never silently assumed); callers treat
    # None as unknown.
    return moment if moment.tzinfo is not None else None


def overview_vm(
    health: ApiResult,
    ready: ApiResult,
    stations: ApiResult,
    model: ApiResult,
    *,
    now_utc: datetime | None = None,
) -> PageView:
    """Operational summary: backend status, coverage, model eligibility."""
    _ = now_utc
    for result in (health, ready, stations, model):
        mapped = _pass_through(result, "Overview")
        if mapped is not None and mapped.state in (STATE_UNAVAILABLE, STATE_ERROR):
            return mapped
    backend_ok = health.state == RESULT_OK and ready.state == RESULT_OK
    ready_data = ready.data if isinstance(ready.data, dict) else {}
    sites = stations.data if isinstance(stations.data, list) else []
    sensors = sum(len(site.get("sensors", [])) for site in sites if isinstance(site, dict))
    model_data = model.data if isinstance(model.data, dict) else {}
    model_status = str(model_data.get("status", NO_MODEL))
    summary = {
        "backend": "ok" if backend_ok else "degraded",
        "database": str(ready_data.get("checks", {}).get("database", "unknown")),
        "postgis": str(ready_data.get("checks", {}).get("postgis", "unknown")),
        "sites": len(sites),
        "sensors": sensors,
        "model_status": model_status,
        "forecast_model_status": NO_FORECAST_MODEL,
    }
    notices = (
        "Model status NO_ELIGIBLE_MODEL: no production flood model exists.",
        "Forecast status NO_ELIGIBLE_FORECAST_MODEL: no validated forecaster exists.",
    )
    state = STATE_OK if sites else STATE_EMPTY
    return PageView(title="Overview", state=state, summary=summary, notices=notices)


def monitoring_vm(
    stations: ApiResult,
    latest_by_sensor: dict[str, dict[str, Any]],
    *,
    now_utc: datetime,
) -> PageView:
    """Latest observation per sensor with factual data age (no verdicts).

    Data age is reported in minutes as a fact. No FRESH/STALE/DELAYED labels
    are produced: no validated production freshness policy exists.
    """
    mapped = _pass_through(stations, "Live Monitoring")
    if mapped is not None:
        return mapped
    rows: list[dict[str, Any]] = []
    sites = stations.data if isinstance(stations.data, list) else []
    for site in sites:
        if not isinstance(site, dict):
            continue
        for sensor in site.get("sensors", []):
            sensor_id = str(sensor.get("fg_sensor_id", ""))
            latest = latest_by_sensor.get(sensor_id, {})
            observed_raw = latest.get("observation_time_utc")
            moment = _parse_instant(observed_raw)
            age_minutes: float | None = None
            if moment is not None:
                age_minutes = (now_utc - moment).total_seconds() / 60.0
            rows.append(
                {
                    "site": str(site.get("fg_site_id", "")),
                    "sensor": sensor_id,
                    "type": str(sensor.get("sensor_type", "")),
                    "unit": str(sensor.get("unit", "")),
                    "value": latest.get("value"),
                    "usable": latest.get("usable"),
                    "observation_time_utc": observed_raw,
                    "age_minutes": age_minutes,
                }
            )
    rows.sort(key=lambda row: (row["site"], row["sensor"]))
    if not rows:
        return PageView(title="Live Monitoring", state=STATE_EMPTY)
    return PageView(
        title="Live Monitoring",
        state=STATE_OK,
        tables={"latest": rows},
        notices=("Ages are facts in minutes; no production freshness verdict exists.",),
    )


def prediction_vm(predictions: ApiResult, model: ApiResult) -> PageView:
    """Stored forecasts with evidence; empty when none are stored."""
    for result in (predictions, model):
        mapped = _pass_through(result, "Flood Prediction")
        if mapped is not None and mapped.state in (STATE_UNAVAILABLE, STATE_ERROR):
            return mapped
    model_data = model.data if isinstance(model.data, dict) else {}
    rows = predictions.data if isinstance(predictions.data, list) else []
    table = [
        {
            "origin_utc": row.get("prediction_origin_utc"),
            "target_utc": row.get("target_time_utc"),
            "horizon_minutes": row.get("horizon_minutes"),
            "predicted_value_m": row.get("predicted_value"),
            "predicted_label": row.get("predicted_label"),
            "model_family": row.get("model_family"),
            "run_id": row.get("run_id"),
            "evidence": evidence_label(str(row.get("evidence_level", ""))),
        }
        for row in rows
        if isinstance(row, dict)
    ]
    notices = (
        f"Model registry: {model_data.get('status', NO_MODEL)}.",
        "Stored rows are baselines/candidates, never production predictions.",
    )
    if not table:
        return PageView(title="Flood Prediction", state=STATE_EMPTY, notices=notices)
    return PageView(
        title="Flood Prediction", state=STATE_OK, tables={"predictions": table}, notices=notices
    )


def station_vm(site: ApiResult) -> PageView:
    """One site: info, map point, reference thresholds, usable series."""
    mapped = _pass_through(site, "Station Analysis")
    if mapped is not None:
        return mapped
    data = site.data if isinstance(site.data, dict) else {}
    thresholds = [
        {
            "type": row.get("threshold_type"),
            "value_m": row.get("value_m"),
            "source": row.get("threshold_source"),
            "captured_at": row.get("captured_at"),
            "validity": row.get("temporal_validity", "CURRENT_THRESHOLD_REFERENCE_ONLY"),
            "label_eligible": row.get("fg_label_eligible"),
        }
        for row in (data.get("thresholds") or [])
        if isinstance(row, dict) and row.get("threshold_type") != "NORMAL"
    ]
    latitude = data.get("latitude")
    longitude = data.get("longitude")
    map_point = (
        [{"lat": float(latitude), "lon": float(longitude)}]
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float))
        else []
    )
    summary = {
        "site": str(data.get("fg_site_id", "")),
        "name": data.get("site_name"),
        "district": data.get("district"),
        "basin": data.get("main_basin"),
        "crs": data.get("crs"),
        "sensors": len(data.get("sensors", [])),
    }
    notices = (
        "Thresholds are CURRENT_THRESHOLD_REFERENCE_ONLY site-level references, "
        "not per-sensor flood states; NORMAL is never a flood target.",
        "Coordinates: WGS84 (EPSG:4326, inferred).",
    )
    tables = {"thresholds": thresholds}
    series = {"map_point": map_point}
    return PageView(
        title="Station Analysis",
        state=STATE_OK,
        summary=summary,
        tables=tables,
        series=series,
        notices=notices,
    )


def observation_series_vm(observations: ApiResult, *, measurement_type: str, unit: str) -> PageView:
    """Chronological series with None gaps (renderers must break lines)."""
    mapped = _pass_through(observations, "Series")
    if mapped is not None:
        return mapped
    data = observations.data if isinstance(observations.data, dict) else {}
    items = [row for row in data.get("items", []) if isinstance(row, dict)]
    points = [{"time": row.get("observation_time_utc"), "value": row.get("value")} for row in items]
    missing = sum(1 for row in items if row.get("value") is None)
    zeros = sum(1 for row in items if row.get("value") == 0 or row.get("value") == 0.0)
    summary = {
        "measurement_type": measurement_type,
        "unit": unit,
        "points": len(points),
        "missing_points": missing,
        "zero_points": zeros,
    }
    if not points:
        return PageView(title="Series", state=STATE_EMPTY, summary=summary)
    return PageView(title="Series", state=STATE_OK, summary=summary, series={"values": points})


def performance_vm(model: ApiResult) -> PageView:
    """Model status, goals (as goals), and real-evaluation state."""
    mapped = _pass_through(model, "Model Performance")
    if mapped is not None:
        return mapped
    data = model.data if isinstance(model.data, dict) else {}
    summary = {
        "status": str(data.get("status", NO_MODEL)),
        "production_model": data.get("production_model"),
        "families_seen": list(data.get("registry_models", [])),
        "recall_target": "≥ 90% (goal, not achieved)",
        "f1_target": "≥ 0.85 (goal, not achieved)",
    }
    notices = (
        "Targets are engineering goals, not measured results.",
        "No synthetic metric may be presented as production performance.",
    )
    return PageView(title="Model Performance", state=STATE_OK, summary=summary, notices=notices)


def shap_vm() -> PageView:
    """SHAP has no eligible real model: supported empty state only."""
    return PageView(
        title="SHAP Explainability",
        state=STATE_EMPTY,
        notices=(
            "No eligible model exists, so no SHAP explanations are available.",
            "SHAP contributions describe model behavior, never causality.",
        ),
    )


def quality_vm(observations: ApiResult, summary: dict[str, Any]) -> PageView:
    """Data-quality aggregates reusing the established flag vocabulary."""
    mapped = _pass_through(observations, "Data Quality")
    if mapped is not None:
        return mapped
    notices = (
        "Source markers (-9999/ERROR/Tiada Data) are source states, not hardware diagnoses.",
        f"Evidence: {evidence_label(str(summary.get('evidence', '')))}.",
    )
    if summary.get("total", 0) == 0:
        return PageView(title="Data Quality", state=STATE_EMPTY, notices=notices)
    return PageView(title="Data Quality", state=STATE_OK, summary=summary, notices=notices)


def drift_vm(volume_by_day: list[dict[str, Any]]) -> PageView:
    """Drift prerequisites unmet: volume context only, never drift claims."""
    notices = (
        "Drift monitoring needs a production model plus a frozen reference window: neither exists.",
        "Below is observation volume context only, not a drift verdict.",
    )
    if not volume_by_day:
        return PageView(title="Model Drift", state=STATE_EMPTY, notices=notices)
    return PageView(
        title="Model Drift", state=STATE_OK, tables={"volume": volume_by_day}, notices=notices
    )


__all__ = [
    "PageView",
    "drift_vm",
    "monitoring_vm",
    "observation_series_vm",
    "overview_vm",
    "performance_vm",
    "prediction_vm",
    "quality_vm",
    "shap_vm",
    "station_vm",
]
