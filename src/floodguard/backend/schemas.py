"""Pydantic request/response schemas for the FloodGuard API (Phase 8).

Explicit response models only; external error payloads never contain stack
traces or secrets.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ReadyResponse(BaseModel):
    status: str
    checks: dict[str, str]


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""


class SensorSummary(BaseModel):
    fg_sensor_id: str
    sensor_type: str
    measurement_type: str
    unit: str


class SiteResponse(BaseModel):
    fg_site_id: str
    site_name: str | None
    district: str | None
    latitude: float | None
    longitude: float | None
    crs: str
    main_basin: str | None
    sensors: list[SensorSummary]
    thresholds: list[ThresholdResponse] = Field(default_factory=list)


class ThresholdResponse(BaseModel):
    threshold_type: str
    value_m: float | None
    threshold_source: str
    captured_at: datetime | None
    temporal_validity: str = "CURRENT_THRESHOLD_REFERENCE_ONLY"
    fg_label_eligible: bool


class ObservationResponse(BaseModel):
    source: str
    fg_sensor_id: str
    measurement_type: str
    observation_time_utc: datetime
    value: float | None
    value_raw: str | None = None
    unit: str
    usable: bool
    quality_flags: list[str]


class ObservationPage(BaseModel):
    items: list[ObservationResponse]
    count: int


class PredictionResponse(BaseModel):
    prediction_id: str
    fg_sensor_id: str
    horizon_minutes: int
    prediction_origin_utc: datetime
    target_time_utc: datetime
    predicted_value: float | None
    predicted_label: int | None = None
    predicted_probability: float | None = None
    model_family: str
    run_id: str
    evidence_level: str
    lineage: dict[str, Any] = Field(default_factory=dict)


class ModelInfoResponse(BaseModel):
    production_model: str | None
    status: str
    detail: str
    registry_models: list[str] = Field(default_factory=list)


class AlertResponse(BaseModel):
    alert_id: str
    fg_sensor_id: str | None
    alert_type: str
    severity: str
    status: str
    message: str
    created_at: datetime


class IngestionMetricsResponse(BaseModel):
    """Factual live-ingestion engineering metrics (Phase 10, no health verdicts)."""

    schema_version: str = "live_metrics/v1"
    poll_attempts: int = 0
    successful_polls: int = 0
    failed_polls: int = 0
    blocked_polls: int = 0
    records_received: int = 0
    canonical_records_inserted: int = 0
    duplicates: int = 0
    quarantined_rows: int = 0
    total_ingestion_duration_seconds: float = 0.0
    mean_poll_duration_seconds: float | None = None
    stage_seconds: dict[str, float] = Field(default_factory=dict)
    last_successful_retrieval: str | None = None
    notice: str = "Factual engineering counters only; no freshness/health verdict is implied."
