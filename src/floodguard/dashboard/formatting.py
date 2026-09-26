"""Deterministic formatting helpers: units, timezones, evidence, status (pure).

- Units always explicit (mm rainfall, m water level, °C temperature).
- Timestamps shown in Asia/Kuala_Lumpur with the UTC instant alongside;
  naive inputs are never silently assumed — callers pass aware instants.
- Evidence levels render as fixed human labels; synthetic never reads as real.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final
from zoneinfo import ZoneInfo

from floodguard.dashboard import (
    EVIDENCE_LOCAL_DIAGNOSTIC,
    EVIDENCE_REAL,
    EVIDENCE_SYNTHETIC,
    LOCAL_TIMEZONE,
    NO_FORECAST_MODEL,
    NO_MODEL,
)


def _local_zone() -> ZoneInfo:
    """Display zone, reused from the canonical normalisation registry.

    The single zone-construction site stays ``preprocessing/timestamps.py``
    (guarded by ``test_policy_registry_is_the_single_zone_source``); display
    reuses the same assumed-zone object instead of constructing another.
    """
    from floodguard.preprocessing.timestamps import SOURCE_TIMEZONE_POLICY

    for policy in SOURCE_TIMEZONE_POLICY.values():
        if str(policy.assumed_zone) == LOCAL_TIMEZONE:
            return policy.assumed_zone
    raise ValueError(f"no canonical policy zone for {LOCAL_TIMEZONE}")


UNIT_LABELS: Final[dict[str, str]] = {
    "mm": "mm",
    "m": "m",
    "C": "°C",
    "m/h": "m/h",
}

EVIDENCE_LABELS: Final[dict[str, str]] = {
    EVIDENCE_SYNTHETIC: "synthetic validation (not real performance)",
    EVIDENCE_LOCAL_DIAGNOSTIC: "local diagnostic (not Penang-wide performance)",
    EVIDENCE_REAL: "real predictive evaluation",
}

MODEL_STATUS_LABELS: Final[dict[str, str]] = {
    NO_MODEL: "no eligible flood-classification model",
    NO_FORECAST_MODEL: "no eligible water-level forecasting model",
}


def format_value(value: float | int | None, unit: str) -> str:
    """Render a measurement with its explicit unit (``—`` when missing)."""
    if value is None:
        return "—"
    label = UNIT_LABELS.get(unit, unit)
    if isinstance(value, float):
        return f"{value:.2f} {label}"
    return f"{value} {label}"


def format_timestamp(moment: datetime) -> str:
    """Render an aware instant as ``Asia/Kuala_Lumpur`` plus UTC.

    Raises ``ValueError`` on naive input rather than assuming a zone.
    """
    if moment.tzinfo is None:
        raise ValueError("naive datetime has no timezone to display")
    local = moment.astimezone(_local_zone())
    return f"{local.strftime('%Y-%m-%d %H:%M %Z')} ({moment.strftime('%Y-%m-%d %H:%M UTC')})"


def format_age_minutes(minutes: float | None) -> str:
    """Render a data-age fact (minutes); never a freshness verdict."""
    if minutes is None:
        return "unknown"
    if minutes < 0:
        return "unknown"
    if minutes < 1:
        return "<1 min"
    if minutes < 60:
        return f"{minutes:.0f} min"
    return f"{minutes / 60:.1f} h"


def evidence_label(evidence: str) -> str:
    """Human label for an evidence level (unknown stays unknown)."""
    return EVIDENCE_LABELS.get(evidence, f"unknown evidence: {evidence}")


def model_status_label(status: str) -> str:
    """Human label for a model eligibility status."""
    return MODEL_STATUS_LABELS.get(status, status)


def quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate observation rows into flag/usable counts (no new taxonomy).

    Reuses the established quality vocabulary: ``usable`` booleans and the
    ``quality_flags`` lists produced upstream. ``ERROR``/``-9999`` markers
    are counted as source states, never described as hardware failure.
    """
    usable = sum(1 for row in rows if row.get("usable") is True)
    missing = sum(1 for row in rows if row.get("usable") is not True)
    flag_counts: dict[str, int] = {}
    for row in rows:
        flags = row.get("quality_flags") or []
        for flag in flags:
            flag_counts[str(flag)] = flag_counts.get(str(flag), 0) + 1
    values: list[float] = []
    for row in rows:
        raw = row.get("value")
        if isinstance(raw, bool):
            continue
        if isinstance(raw, (int, float)):
            values.append(float(raw))
    zeros = sum(1 for value in values if value == 0.0)
    return {
        "total": len(rows),
        "usable": usable,
        "missing_or_unusable": missing,
        "zero_values": zeros,
        "flag_counts": dict(sorted(flag_counts.items())),
    }
