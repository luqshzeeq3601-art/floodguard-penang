"""Class imbalance and event-count viability analysis for flood/threshold prediction labels.

Design: docs/CLASS_IMBALANCE.md.

Input is the Phase 2 canonical table (``processed/observations/v1/<dataset_version>/``). Only rows
with ``measurement_type = WATER_LEVEL`` and unit ``m`` enter.

Analyzes class imbalance across prediction horizons (+30, +60, +120 minutes) and reference
thresholds (Waspada, Amaran, Bahaya):
- Distinguishes row-level exceedances from distinct contiguous event episodes.
- Calculates positive counts, negative counts, positive prevalence (%), and class imbalance ratios
  (negative:positive).
- Checks whether available history provides enough independent episodes and positive labels for
  viable chronological train/validation/test splits.
- Documents empirical feasibility: if zero or few positive examples exist in the local captures,
  feasibility is marked INSUFFICIENT.

Pure and deterministic.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final

from floodguard.analysis.dataset import (
    AnalysisContractError,
    select_measurement,
    write_once_json,
)
from floodguard.analysis.events import (
    EventIdentificationConfig,
    analyze_sensor_threshold,
)
from floodguard.analysis.labels import (
    DEFAULT_HORIZONS_MINUTES,
    LabelDefinitionConfig,
    construct_labels_for_sensor,
)
from floodguard.preprocessing.units import MeasurementType
from floodguard.station_master import SensorType, ThresholdType
from floodguard.validation.observations import SCHEMA_VERSION as OBSERVATION_SCHEMA

SCHEMA_VERSION = "class_imbalance/v1"
MEASUREMENT = MeasurementType.WATER_LEVEL
UNIT = "m"
DECIMALS = 6
OUTPUT_FILE = "class_imbalance.json"

ELIGIBLE_THRESHOLD_TYPES: Final = (
    ThresholdType.WASPADA,
    ThresholdType.AMARAN,
    ThresholdType.BAHAYA,
)

CURRENT_THRESHOLD_REFERENCE_ONLY = "CURRENT_THRESHOLD_REFERENCE_ONLY"
NOT_ESTABLISHED = "NOT_ESTABLISHED"


@dataclass(frozen=True)
class ClassImbalanceConfig:
    """Configurable parameters and guards for class imbalance analysis."""

    horizons_minutes: tuple[int, ...] = DEFAULT_HORIZONS_MINUTES
    max_gap_minutes: float = 5.0
    max_window_gap_minutes: float = 1440.0
    continuity_breaking_flags: tuple[str, ...] = ("SOURCE_SEVERITY_ERROR",)
    min_usable_origins: int = 30
    min_episodes_for_split: int = 10  # minimum independent episodes for 3-way chronological split
    min_positives_for_split: int = 30  # minimum positive instances across dataset

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
        if self.min_episodes_for_split < 1:
            raise ValueError("min_episodes_for_split must be >= 1")
        if self.min_positives_for_split < 1:
            raise ValueError("min_positives_for_split must be >= 1")


def _r(x: float) -> float:
    return round(float(x), DECIMALS) + 0.0


def _pct(part: int, whole: int) -> float | None:
    return _r(100 * part / whole) if whole else None


def analyze_sensor_imbalance(
    rows: Sequence[Mapping[str, Any]],
    thresholds: Sequence[Mapping[str, Any]],
    config: ClassImbalanceConfig,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze class imbalance and episodes for one sensor across all thresholds/horizons."""
    sensor_id = rows[0]["fg_sensor_id"]
    site_id = rows[0]["fg_site_id"]

    # Filter eligible thresholds (WASPADA, AMARAN, BAHAYA)
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

    ev_cfg = EventIdentificationConfig(
        max_gap_minutes=config.max_gap_minutes,
        max_window_gap_minutes=config.max_window_gap_minutes,
        continuity_breaking_flags=config.continuity_breaking_flags,
    )
    lbl_cfg = LabelDefinitionConfig(
        horizons_minutes=config.horizons_minutes,
        max_gap_minutes=config.max_gap_minutes,
        max_window_gap_minutes=config.max_window_gap_minutes,
        continuity_breaking_flags=config.continuity_breaking_flags,
    )

    # 1. Event / episode analysis per threshold
    event_evals = [analyze_sensor_threshold(rows, t, ev_cfg) for t in eligible_thresh]

    # 2. Multi-horizon label analysis
    label_eval = construct_labels_for_sensor(rows, eligible_thresh, lbl_cfg, metadata=metadata)

    threshold_imbalances: dict[str, Any] = {}
    for ev in event_evals:
        tt = ev["threshold_type"]
        tsrc = ev.get("threshold_source")
        key = f"{tt}_{tsrc}" if tsrc else tt

        episodes = ev["contiguous_exceedance_episodes"]
        exceed_obs = ev["exceedance_observations"]
        usable_obs = ev["usable_observations"]

        # Compute imbalance by horizon
        horizon_imbalances: dict[str, Any] = {}
        for h in config.horizons_minutes:
            h_key = f"plus_{h}m"
            h_data = label_eval["horizons"][h_key]
            evaluable = h_data["evaluable_origins"]
            prev_data = h_data["threshold_prevalence"].get(key, {})

            pos_exceed = prev_data.get("exceedance_positive_count", 0)
            neg_exceed = evaluable - pos_exceed
            pos_rate = prev_data.get("exceedance_positive_rate")
            ratio = _r(neg_exceed / pos_exceed) if pos_exceed > 0 else None

            pos_escalate = prev_data.get("escalation_positive_count", 0)
            neg_escalate = evaluable - pos_escalate
            escalate_rate = prev_data.get("escalation_positive_rate")
            escalate_ratio = _r(neg_escalate / pos_escalate) if pos_escalate > 0 else None

            horizon_imbalances[h_key] = {
                "horizon_minutes": h,
                "evaluable_origins": evaluable,
                "exceedance": {
                    "positive_count": pos_exceed,
                    "negative_count": neg_exceed,
                    "positive_prevalence_percent": pos_rate,
                    "imbalance_ratio_negative_to_positive": ratio,
                },
                "escalation": {
                    "positive_count": pos_escalate,
                    "negative_count": neg_escalate,
                    "positive_prevalence_percent": escalate_rate,
                    "imbalance_ratio_negative_to_positive": escalate_ratio,
                },
            }

        threshold_imbalances[key] = {
            "threshold_type": tt,
            "threshold_value_m": ev["threshold_value_m"],
            "threshold_source": tsrc,
            "usable_observations": usable_obs,
            "observation_level_exceedances": exceed_obs,
            "contiguous_exceedance_episodes": episodes,
            "observation_level_exceedance_percent": ev["exceedance_percentage"],
            "horizons": horizon_imbalances,
        }

    return {
        "fg_sensor_id": sensor_id,
        "fg_site_id": site_id,
        "station": dict(metadata or {}),
        "usable_origins_count": label_eval["usable_origins_count"],
        "thresholds": threshold_imbalances,
    }


def _entry(ok: bool, requirement: str, **observed: Any) -> dict[str, Any]:
    return {
        "status": "SUFFICIENT" if ok else "INSUFFICIENT",
        "requirement": requirement,
        "observed": observed,
    }


def assess_imbalance_feasibility(
    stations: Sequence[Mapping[str, Any]],
    config: ClassImbalanceConfig,
) -> dict[str, dict[str, Any]]:
    """Assess whether class distributions support training and validation splits."""
    c = config

    total_usable = sum(s["usable_origins_count"] for s in stations)
    total_episodes: Counter[str] = Counter()
    total_positives_by_horizon: Counter[str] = Counter()

    for s in stations:
        for thresh_key, tdata in s["thresholds"].items():
            total_episodes[thresh_key] += tdata["contiguous_exceedance_episodes"]
            for h_key, hdata in tdata["horizons"].items():
                total_positives_by_horizon[f"{thresh_key}/{h_key}"] += hdata["exceedance"][
                    "positive_count"
                ]

    max_episodes = max(total_episodes.values(), default=0)
    max_positives = max(total_positives_by_horizon.values(), default=0)
    split_ok = (
        max_episodes >= c.min_episodes_for_split and max_positives >= c.min_positives_for_split
    )

    return {
        "imbalance_analysis_verification": _entry(
            True,
            "End-to-end execution of class imbalance and episode viability analysis",
            stations_evaluated=len(stations),
            total_usable_origins=total_usable,
        ),
        "chronological_split_viability": _entry(
            split_ok,
            f"At least {c.min_episodes_for_split} distinct event episodes and "
            f"{c.min_positives_for_split} positive labels across dataset for 3-way split",
            max_distinct_episodes_any_threshold=max_episodes,
            max_positive_labels_any_horizon=max_positives,
            split_recommendation=(
                "VIABLE"
                if split_ok
                else "INSUFFICIENT_HISTORY (too few independent events for valid split)"
            ),
        ),
        "extreme_class_imbalance_risk": _entry(
            max_positives > 0,
            "Non-zero positive flood/threshold events observed in the dataset",
            observed_max_positives=max_positives,
            status_note=(
                "Sparse or zero positive examples in local dataset; models trained on this sample "
                "would suffer from complete class collapse without multi-year historical data."
            ),
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
    config: ClassImbalanceConfig | None = None,
) -> dict[str, Any]:
    """Calculate class imbalance metrics and split feasibility for one dataset version."""
    if not dataset_version:
        raise AnalysisContractError("dataset_version is required")
    cfg = config or ClassImbalanceConfig()
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
            analyze_sensor_imbalance(
                group,
                thresh_ref.get(sid, []),
                cfg,
                metadata=meta.get(sid),
            )
        )

    feasibility = assess_imbalance_feasibility(stations, cfg)
    levels = ["IMPLEMENTATION_VERIFICATION"]
    if sum(s["usable_origins_count"] for s in stations) >= cfg.min_usable_origins:
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
            "positive_prevalence": "percentage of evaluable origins where target is positive",
            "imbalance_ratio": "negative_count / positive_count (None if positive_count is 0)",
            "contiguous_exceedance_episodes": "count of distinct continuous exceedance events",
            "chronological_split_requirement": "requires >= 10 distinct episodes and >= 30 "
            "positive examples to support non-leaking train/val/test chronological partition",
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
        "scope": "Class imbalance and event-viability analysis. Distinguishes row exceedances from "
        "distinct episodes. Evaluates splitting feasibility under available historical coverage.",
    }


def write_summary(document: Mapping[str, Any], output_root: Path) -> tuple[Path, bool]:
    """Write-once ``<output_root>/<dataset_version>/class_imbalance.json``."""
    return write_once_json(document, output_root, OUTPUT_FILE)
