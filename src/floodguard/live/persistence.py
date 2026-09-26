"""Prediction persistence for live outputs (Phase 10, Task 7).

Stores inference outputs via the Phase 8 ``PredictionRepository`` (no direct
SQL from scheduler code). Enforces the existing hard rules:

- ``run_id`` NOT NULL (baselines are explicit states, never NULL ambiguity);
- site must match the sensor's site;
- ``predicted_label`` binary-or-NULL;
- lineage preserved; never a false production claim (``evidence_level``
  travels with every row; ``/api/v1/model`` stays ``NO_ELIGIBLE_MODEL``).

With no eligible model the live path persists zero rows; this module is
exercised by explicitly supplied baseline/candidate rows in tests.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from floodguard.backend.models import Prediction
from floodguard.backend.repositories import PredictionRepository

PERSISTENCE_SCHEMA_VERSION = "live_prediction_persistence/v1"


def _as_utc(moment: datetime | str) -> datetime:
    dt = datetime.fromisoformat(moment) if isinstance(moment, str) else moment
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def build_prediction(
    *,
    fg_sensor_id: str,
    fg_site_id: str,
    horizon_minutes: int,
    origin_utc: datetime | str,
    target_utc: datetime | str,
    model_family: str,
    run_id: str,
    evidence_level: str,
    predicted_value: float | None = None,
    predicted_label: int | None = None,
    predicted_probability: float | None = None,
    lineage: Mapping[str, Any] | None = None,
    prediction_id: str | None = None,
) -> Prediction:
    if horizon_minutes not in (30, 60, 120):
        raise ValueError(f"horizon must be 30/60/120, got {horizon_minutes!r}")
    if predicted_label not in (None, 0, 1):
        raise ValueError("predicted_label must be binary-or-NULL")
    if not run_id:
        raise ValueError("run_id is required (never NULL)")
    now = datetime.now(UTC)
    value_q = (
        Decimal(str(predicted_value)).quantize(Decimal("0.0000"))
        if predicted_value is not None
        else None
    )
    prob_q = (
        Decimal(str(predicted_probability)).quantize(Decimal("0.000000"))
        if predicted_probability is not None
        else None
    )
    return Prediction(
        prediction_id=prediction_id or str(uuid.uuid4()),
        fg_sensor_id=fg_sensor_id,
        fg_site_id=fg_site_id,
        horizon_minutes=horizon_minutes,
        prediction_origin_utc=_as_utc(origin_utc),
        target_time_utc=_as_utc(target_utc),
        predicted_value=value_q,
        predicted_label=predicted_label,
        predicted_probability=prob_q,
        model_family=model_family,
        run_id=run_id,
        evidence_level=evidence_level,
        created_at=now,
        lineage=dict(lineage or {}),
    )


def persist_predictions(session: Session, rows: Sequence[Prediction]) -> dict[str, int]:
    """Persist inference outputs transactionally; returns outcome counts."""
    repo = PredictionRepository(session)
    inserted = 0
    try:
        for row in rows:
            repo.insert(row)
            inserted += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"inserted": inserted, "requested": len(rows)}
