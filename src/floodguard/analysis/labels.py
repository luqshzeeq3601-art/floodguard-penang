"""Prediction target and label construction (+30, +60, +120 min) for canonical water level.

Design: docs/LABEL_DEFINITION.md.

Input is the Phase 2 canonical table (``processed/observations/v1/<dataset_version>/``). Only rows
with ``measurement_type = WATER_LEVEL`` and unit ``m`` enter.

Target construction is strictly separated from feature engineering:
- At prediction origin time ``t``, a row may only use information available at or before ``t``.
- Target at ``t + h`` (where h in {30, 60, 120} minutes) evaluates the future water-level outcome
  relative to the origin ``t``.
- If the future observation at ``t + h`` is missing, not usable, or beyond the window boundary,
  the target status is ``MISSING_FUTURE_TARGET``; it is NEVER imputed or assumed to be non-flood.

Labels are evaluated against current reference thresholds (Waspada, Amaran, Bahaya; NORMAL
excluded) as operational proxy targets (``CURRENT_THRESHOLD_REFERENCE_ONLY``). They do NOT
represent verified official flood ground truth.

Pure and deterministic.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

from floodguard.analysis.dataset import (
    AnalysisContractError,
    select_measurement,
    write_once_json,
)
from floodguard.preprocessing.units import MeasurementType
from floodguard.station_master import SensorType, ThresholdType
from floodguard.validation.observations import SCHEMA_VERSION as OBSERVATION_SCHEMA

SCHEMA_VERSION = "labels/v1"
MEASUREMENT = MeasurementType.WATER_LEVEL
UNIT = "m"
DECIMALS = 6
OUTPUT_FILE = "labels.json"

DEFAULT_HORIZONS_MINUTES: Final[tuple[int, ...]] = (30, 60, 120)
ELIGIBLE_THRESHOLD_TYPES: Final = (
    ThresholdType.WASPADA,
    ThresholdType.AMARAN,
    ThresholdType.BAHAYA,
)

# Target evaluation statuses
TARGET_EVALUATED = "TARGET_EVALUATED"
MISSING_FUTURE_TARGET = "MISSING_FUTURE_TARGET"
ORIGIN_NOT_USABLE = "ORIGIN_NOT_USABLE"
BEYOND_WINDOW_BOUNDARY = "BEYOND_WINDOW_BOUNDARY"

# Label types
PROXY_THRESHOLD_EXCEEDANCE = "PROXY_THRESHOLD_EXCEEDANCE"
PROXY_THRESHOLD_ESCALATION = "PROXY_THRESHOLD_ESCALATION"
FUTURE_WATER_LEVEL_REGRESSION = "FUTURE_WATER_LEVEL_REGRESSION"

CURRENT_THRESHOLD_REFERENCE_ONLY = "CURRENT_THRESHOLD_REFERENCE_ONLY"
NOT_ESTABLISHED = "NOT_ESTABLISHED"


@dataclass(frozen=True)
class LabelDefinitionConfig:
    """Configurable horizons and guards for label definition."""

    horizons_minutes: tuple[int, ...] = DEFAULT_HORIZONS_MINUTES
    max_gap_minutes: float = 5.0
    max_window_gap_minutes: float = 1440.0
    continuity_breaking_flags: tuple[str, ...] = ("SOURCE_SEVERITY_ERROR",)
    min_usable_origins: int = 30

    def __post_init__(self) -> None:
        hs = self.horizons_minutes
        if not hs or list(hs) != sorted(set(hs)) or not all(h > 0 for h in hs):
            raise ValueError("horizons_minutes must be unique, ascending positive integers")
        if not (math.isfinite(self.max_gap_minutes) and self.max_gap_minutes > 0):
            raise ValueError("max_gap_minutes must be finite and > 0")
        if not (math.isfinite(self.max_window_gap_minutes) and self.max_window_gap_minutes > 0):
            raise ValueError("max_window_gap_minutes must be finite and > 0")
        if self.min_usable_origins < 1:
            raise ValueError("min_usable_origins must be >= 1")


def _r(x: float) -> float:
    return round(float(x), DECIMALS) + 0.0


def _pct(part: int, whole: int) -> float | None:
    return _r(100 * part / whole) if whole else None


def _t(row: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(row["observation_time_utc"])


def is_usable_origin(row: Mapping[str, Any], config: LabelDefinitionConfig) -> bool:
    return bool(row["usable"]) and not set(row["quality_flags"]) & set(
        config.continuity_breaking_flags
    )


def construct_labels_for_sensor(
    rows: Sequence[Mapping[str, Any]],
    thresholds: Sequence[Mapping[str, Any]],
    config: LabelDefinitionConfig,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct multi-horizon target labels for one water-level sensor."""
    ordered = sorted(rows, key=_t)
    sensor_id = ordered[0]["fg_sensor_id"]
    site_id = ordered[0]["fg_site_id"]

    # Index rows by UTC timestamp
    by_time = {_t(r): r for r in ordered}
    usable_rows = [r for r in ordered if is_usable_origin(r, config)]

    # Filter eligible thresholds
    eligible_thresh = [
        t for t in thresholds if t.get("threshold_type") in set(ELIGIBLE_THRESHOLD_TYPES)
    ]
    eligible_thresh.sort(
        key=lambda t: (
            ELIGIBLE_THRESHOLD_TYPES.index(t["threshold_type"]),
            t.get("threshold_source", ""),
            t.get("captured_at", ""),
        )
    )

    horizon_summaries: dict[str, Any] = {}

    for h in config.horizons_minutes:
        h_key = f"plus_{h}m"
        delta = timedelta(minutes=h)
        evaluations: list[dict[str, Any]] = []

        total_origins = len(usable_rows)
        evaluable_origins = 0
        missing_future_origins = 0

        # Positive counts per threshold
        exceed_counts: Counter[str] = Counter()
        escalate_counts: Counter[str] = Counter()

        deltas: list[float] = []

        for r in usable_rows:
            origin_t = _t(r)
            origin_val = float(r["value"])
            target_t = origin_t + delta

            target_row = by_time.get(target_t)
            if target_row is None or not is_usable_origin(target_row, config):
                missing_future_origins += 1
                evaluations.append(
                    {
                        "origin_utc": r["observation_time_utc"],
                        "target_horizon_minutes": h,
                        "target_utc": target_t.isoformat(),
                        "target_status": MISSING_FUTURE_TARGET,
                        "origin_water_level_m": _r(origin_val),
                        "future_water_level_m": None,
                        "delta_water_level_m": None,
                        "threshold_labels": {},
                    }
                )
                continue

            evaluable_origins += 1
            target_val = float(target_row["value"])
            delta_val = target_val - origin_val
            deltas.append(delta_val)

            thresh_labels: dict[str, Any] = {}
            for t in eligible_thresh:
                tt = str(t["threshold_type"])
                t_val = float(t["value_m"])
                t_src = t.get("threshold_source")

                is_exceed = target_val >= t_val
                is_escalate = (origin_val < t_val) and (target_val >= t_val)

                label_key = f"{tt}_{t_src}" if t_src else tt
                if is_exceed:
                    exceed_counts[label_key] += 1
                if is_escalate:
                    escalate_counts[label_key] += 1

                thresh_labels[label_key] = {
                    "threshold_type": tt,
                    "threshold_value_m": _r(t_val),
                    "threshold_source": t_src,
                    "is_exceedance": is_exceed,
                    "is_escalation": is_escalate,
                    "temporal_validity": CURRENT_THRESHOLD_REFERENCE_ONLY,
                }

            evaluations.append(
                {
                    "origin_utc": r["observation_time_utc"],
                    "target_horizon_minutes": h,
                    "target_utc": target_t.isoformat(),
                    "target_status": TARGET_EVALUATED,
                    "origin_water_level_m": _r(origin_val),
                    "future_water_level_m": _r(target_val),
                    "delta_water_level_m": _r(delta_val),
                    "rate_to_horizon_m_per_h": _r(delta_val / (h / 60)),
                    "threshold_labels": thresh_labels,
                }
            )

        # Build summary for horizon h
        horizon_summaries[h_key] = {
            "horizon_minutes": h,
            "total_origins": total_origins,
            "evaluable_origins": evaluable_origins,
            "missing_future_origins": missing_future_origins,
            "evaluable_percent": _pct(evaluable_origins, total_origins),
            "threshold_prevalence": {
                k: {
                    "exceedance_positive_count": exceed_counts[k],
                    "exceedance_positive_rate": _pct(exceed_counts[k], evaluable_origins),
                    "escalation_positive_count": escalate_counts[k],
                    "escalation_positive_rate": _pct(escalate_counts[k], evaluable_origins),
                }
                for k in sorted({*exceed_counts.keys(), *escalate_counts.keys()})
            },
            "regression_target_summary": {
                "count": len(deltas),
                "min_delta_m": _r(min(deltas)) if deltas else None,
                "max_delta_m": _r(max(deltas)) if deltas else None,
                "mean_delta_m": _r(sum(deltas) / len(deltas)) if deltas else None,
            },
            "evaluations_sample_size": len(evaluations),
        }

    return {
        "fg_sensor_id": sensor_id,
        "fg_site_id": site_id,
        "station": dict(metadata or {}),
        "usable_origins_count": len(usable_rows),
        "reference_thresholds_count": len(eligible_thresh),
        "horizons": horizon_summaries,
    }


def _entry(ok: bool, requirement: str, **observed: Any) -> dict[str, Any]:
    return {
        "status": "SUFFICIENT" if ok else "INSUFFICIENT",
        "requirement": requirement,
        "observed": observed,
    }


def assess_label_feasibility(
    stations: Sequence[Mapping[str, Any]],
    config: LabelDefinitionConfig,
) -> dict[str, dict[str, Any]]:
    """Assess whether label distributions are empirically viable for ML modeling."""
    c = config
    max_origins = max((s["usable_origins_count"] for s in stations), default=0)

    # Calculate total positives across all stations and horizons
    all_exceed_positives: Counter[str] = Counter()
    all_escalate_positives: Counter[str] = Counter()
    total_evaluable = 0

    for s in stations:
        for h_key, h_data in s["horizons"].items():
            total_evaluable += h_data["evaluable_origins"]
            for thresh_key, prev in h_data["threshold_prevalence"].items():
                all_exceed_positives[f"{h_key}/{thresh_key}"] += prev["exceedance_positive_count"]
                all_escalate_positives[f"{h_key}/{thresh_key}"] += prev["escalation_positive_count"]

    max_exceed_pos = max(all_exceed_positives.values(), default=0)
    max_escalate_pos = max(all_escalate_positives.values(), default=0)

    return {
        "label_construction_verification": _entry(
            True,
            "End-to-end execution of target label derivation for +30, +60, +120 min horizons",
            stations_evaluated=len(stations),
        ),
        "evaluable_origins_sufficiency": _entry(
            max_origins >= c.min_usable_origins,
            f"At least one station with >= {c.min_usable_origins} usable prediction origins",
            max_usable_origins=max_origins,
        ),
        "positive_label_feasibility": _entry(
            max_exceed_pos >= 10,
            "At least 10 positive label examples per horizon/threshold for train/test split",
            max_exceedance_positives=max_exceed_pos,
            max_escalation_positives=max_escalate_pos,
            empirical_feasibility=(
                "INSUFFICIENT (sample contains zero or too few positive examples)"
            ),
        ),
        "ground_truth_validity": _entry(
            False,
            "Official historical flood ground truth (none exists; labels are proxy threshold "
            "exceedances against unversioned reference thresholds)",
            ground_truth_status="PROVISIONAL_PROXY_ONLY",
        ),
    }


def select_water_level(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], dict[str, int]]:
    """Select canonical WATER_LEVEL rows. Contract violations raise."""
    selected, excluded = select_measurement(
        rows,
        measurement_type=MEASUREMENT,
        unit=UNIT,
        sensor_type=SensorType.WATER_LEVEL,
        value_ok=lambda v: True,
        value_rule="water level must be finite",
    )
    for i, r in enumerate(selected):
        if not isinstance(r.get("quality_flags"), list) or not isinstance(r.get("datasets"), list):
            raise AnalysisContractError(f"water-level row {i}: quality_flags/datasets not lists")
    return selected, excluded


def analyze(
    rows: Iterable[Mapping[str, Any]],
    *,
    dataset_version: str,
    observations_sha256: str | None = None,
    quality_summary: Mapping[str, Any] | None = None,
    station_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    station_master_sha256: str | None = None,
    threshold_reference: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    threshold_reference_sha256: str | None = None,
    config: LabelDefinitionConfig | None = None,
) -> dict[str, Any]:
    """Derive multi-horizon prediction targets and prevalence for one dataset version."""
    if not dataset_version:
        raise AnalysisContractError("dataset_version is required")
    cfg = config or LabelDefinitionConfig()
    selected, excluded = select_water_level(rows)

    by_sensor: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in selected:
        by_sensor[r["fg_sensor_id"]].append(r)

    meta = station_metadata or {}
    thresh_ref = threshold_reference or {}

    stations = []
    for sid in sorted(by_sensor):
        group = by_sensor[sid]
        if len({r["fg_site_id"] for r in group}) != 1:
            raise AnalysisContractError(f"sensor {sid}: rows disagree on fg_site_id")
        stations.append(
            construct_labels_for_sensor(
                group,
                thresh_ref.get(sid, []),
                cfg,
                metadata=meta.get(sid),
            )
        )

    feasibility = assess_label_feasibility(stations, cfg)
    levels = ["IMPLEMENTATION_VERIFICATION"]
    if feasibility["evaluable_origins_sufficiency"]["status"] == "SUFFICIENT":
        levels.append("STATION_WINDOW_DESCRIPTIVE")

    return {
        "analysis_schema_version": SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "input": {
            "observation_schema_version": OBSERVATION_SCHEMA,
            "observations_sha256": observations_sha256,
            "station_master_sha256": station_master_sha256,
            "threshold_reference_sha256": threshold_reference_sha256,
            "selection": {"measurement_type": str(MEASUREMENT), "unit": UNIT},
            "water_level_rows": len(selected),
            "excluded_rows_by_measurement_type": excluded,
        },
        "definitions": {
            "target_horizon": "prediction lead time (+30, +60, +120 minutes from origin t)",
            "prediction_origin": "usable canonical observation at origin instant t",
            "proxy_threshold_exceedance": "future water level at t + h >= reference threshold",
            "proxy_threshold_escalation": "water level at t < threshold AND water level at "
            "t + h >= threshold (onset transition within horizon)",
            "future_water_level_regression": "delta = level(t + h) - level(t)",
            "missing_future_target": "target at t + h is missing, unusable or beyond window edge; "
            "never imputed as non-flood",
            "temporal_validity": CURRENT_THRESHOLD_REFERENCE_ONLY,
        },
        "config": asdict(cfg),
        "network": {
            "stations_analysed": len(stations),
            "total_usable_origins": sum(s["usable_origins_count"] for s in stations),
        },
        "stations": stations,
        "feasibility": feasibility,
        "evidence_levels_supported": levels,
        "scope": "Provisional label definitions and empirical prevalence. Labels are operational "
        "proxies against current reference thresholds, not verified historical flood ground truth.",
    }


def write_summary(document: Mapping[str, Any], output_root: Path) -> tuple[Path, bool]:
    """Write-once ``<output_root>/<dataset_version>/labels.json``."""
    return write_once_json(document, output_root, OUTPUT_FILE)
