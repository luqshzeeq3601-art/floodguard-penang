"""Provisional threshold exceedance and episode identification for canonical water-level data.

Design: docs/EVENT_IDENTIFICATION.md.

Input is the Phase 2 canonical table (``processed/observations/v1/<dataset_version>/``). Only rows
with ``measurement_type = WATER_LEVEL`` and unit ``m`` enter.

Thresholds are captured from current JPS feeds (``thresholds.csv``). They are
``CURRENT_THRESHOLD_REFERENCE_ONLY`` and are NOT proven to have applied at historical observation
timestamps (``valid_at_observation_times: NOT_ESTABLISHED``). NORMAL is excluded and never a flood
threshold.

Three concepts are strictly separated:
1. Observed threshold exceedance: an individual usable water-level observation with
   ``value >= threshold_value``.
2. Contiguous exceedance episode: a maximal run of consecutive threshold exceedance observations
   with uninterrupted valid cadence (gap <= max_gap_minutes, no not-usable rows or missing slots).
3. Verified historical flood event: does NOT exist in the current dataset (count = 0) because no
   official event-dated flood dataset overlapping JPS 2024+ has been verified.

Pure and deterministic.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
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

SCHEMA_VERSION = "threshold_events/v1"
MEASUREMENT = MeasurementType.WATER_LEVEL
UNIT = "m"
DECIMALS = 6
OUTPUT_FILE = "threshold_events.json"

# Threshold types eligible for exceedance analysis (NORMAL is never eligible)
ELIGIBLE_THRESHOLD_TYPES: Final = (
    ThresholdType.WASPADA,
    ThresholdType.AMARAN,
    ThresholdType.BAHAYA,
)

# Status constants
OK = "OK"
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
SUFFICIENT, INSUFFICIENT = "SUFFICIENT", "INSUFFICIENT"
IMPLEMENTATION_VERIFICATION = "IMPLEMENTATION_VERIFICATION"
PROVISIONAL_EXCEEDANCE_DESCRIPTIVE = "PROVISIONAL_EXCEEDANCE_DESCRIPTIVE"
HISTORICAL_GROUND_TRUTH = "HISTORICAL_GROUND_TRUTH"

# Termination reasons
ENDED_BELOW_THRESHOLD = "ENDED_BELOW_THRESHOLD"
INTERRUPTED_BY_MISSING_DATA = "INTERRUPTED_BY_MISSING_DATA"
WINDOW_EDGE = "WINDOW_EDGE"

# Metadata flags
CURRENT_THRESHOLD_REFERENCE_ONLY = "CURRENT_THRESHOLD_REFERENCE_ONLY"
NOT_ESTABLISHED = "NOT_ESTABLISHED"
PROVISIONAL_EXCEEDANCE_ONLY = "PROVISIONAL_EXCEEDANCE_ONLY"
NO_OFFICIAL_GROUND_TRUTH = "NO_OFFICIAL_GROUND_TRUTH"


@dataclass(frozen=True)
class EventIdentificationConfig:
    """Configurable guards for provisional threshold exceedance segmentation."""

    # Maximum gap between consecutive observations in an episode (minutes)
    max_gap_minutes: float = 5.0
    # Canonical rows further apart than this belong to different observation windows
    max_window_gap_minutes: float = 1440.0
    continuity_breaking_flags: tuple[str, ...] = ("SOURCE_SEVERITY_ERROR",)
    min_usable_for_analysis: int = 30
    min_episodes_for_statistics: int = 5

    def __post_init__(self) -> None:
        if not (math.isfinite(self.max_gap_minutes) and self.max_gap_minutes > 0):
            raise ValueError("max_gap_minutes must be finite and > 0")
        if not (math.isfinite(self.max_window_gap_minutes) and self.max_window_gap_minutes > 0):
            raise ValueError("max_window_gap_minutes must be finite and > 0")
        if self.max_gap_minutes > self.max_window_gap_minutes:
            raise ValueError("max_gap_minutes must be <= max_window_gap_minutes")
        if self.min_usable_for_analysis < 1:
            raise ValueError("min_usable_for_analysis must be >= 1")
        if self.min_episodes_for_statistics < 1:
            raise ValueError("min_episodes_for_statistics must be >= 1")


def _r(x: float) -> float:
    return round(float(x), DECIMALS) + 0.0


def _pct(part: int, whole: int) -> float | None:
    return _r(100 * part / whole) if whole else None


def _t(row: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(row["observation_time_utc"])


def _minutes(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 60


def is_usable_observation(row: Mapping[str, Any], config: EventIdentificationConfig) -> bool:
    """True if row is usable and free from continuity-breaking flags."""
    return bool(row["usable"]) and not set(row["quality_flags"]) & set(
        config.continuity_breaking_flags
    )


def observation_windows(
    rows: Sequence[Mapping[str, Any]], config: EventIdentificationConfig
) -> list[list[Mapping[str, Any]]]:
    """Split rows into observation windows if gap > max_window_gap_minutes."""
    windows: list[list[Mapping[str, Any]]] = []
    for r in sorted(rows, key=_t):
        if windows and _minutes(_t(windows[-1][-1]), _t(r)) <= config.max_window_gap_minutes:
            windows[-1].append(r)
        else:
            windows.append([r])
    return windows


def segment_threshold_episodes(
    window_rows: Sequence[Mapping[str, Any]],
    threshold_info: Mapping[str, Any],
    config: EventIdentificationConfig,
    *,
    episode_index_start: int = 1,
) -> tuple[list[dict[str, Any]], int]:
    """Segment contiguous exceedance episodes for one threshold within one window.

    Returns (episodes, next_episode_index).
    """
    threshold_val = float(threshold_info["value_m"])
    threshold_type = str(threshold_info["threshold_type"])
    threshold_source = threshold_info.get("threshold_source")
    threshold_captured_at = threshold_info.get("captured_at")
    sensor_id = window_rows[0]["fg_sensor_id"]
    site_id = window_rows[0]["fg_site_id"]

    episodes: list[dict[str, Any]] = []
    current_obs: list[Mapping[str, Any]] = []
    ep_idx = episode_index_start

    ordered = sorted(window_rows, key=_t)
    n_rows = len(ordered)

    for i, r in enumerate(ordered):
        usable = is_usable_observation(r, config)
        val = float(r["value"]) if usable else None
        exceeds = usable and val is not None and val >= threshold_val

        if exceeds:
            if not current_obs:
                # Start new episode
                current_obs.append(r)
            else:
                # Check continuity with previous observation
                prev = current_obs[-1]
                gap = _minutes(_t(prev), _t(r))
                if gap <= config.max_gap_minutes:
                    current_obs.append(r)
                else:
                    # Interrupted by time gap before this row
                    # Close previous episode with INTERRUPTED_BY_MISSING_DATA
                    episodes.append(
                        _build_episode_record(
                            current_obs,
                            sensor_id=sensor_id,
                            site_id=site_id,
                            episode_index=ep_idx,
                            threshold_type=threshold_type,
                            threshold_val=threshold_val,
                            threshold_source=threshold_source,
                            threshold_captured_at=threshold_captured_at,
                            termination_reason=INTERRUPTED_BY_MISSING_DATA,
                        )
                    )
                    ep_idx += 1
                    current_obs = [r]
        else:
            # Current row does not exceed threshold (or is not usable)
            if current_obs:
                # Close current episode
                reason = ENDED_BELOW_THRESHOLD if usable else INTERRUPTED_BY_MISSING_DATA
                episodes.append(
                    _build_episode_record(
                        current_obs,
                        sensor_id=sensor_id,
                        site_id=site_id,
                        episode_index=ep_idx,
                        threshold_type=threshold_type,
                        threshold_val=threshold_val,
                        threshold_source=threshold_source,
                        threshold_captured_at=threshold_captured_at,
                        termination_reason=reason,
                    )
                )
                ep_idx += 1
                current_obs = []

        # If at the last row of the window and episode is still open
        if i == n_rows - 1 and current_obs:
            episodes.append(
                _build_episode_record(
                    current_obs,
                    sensor_id=sensor_id,
                    site_id=site_id,
                    episode_index=ep_idx,
                    threshold_type=threshold_type,
                    threshold_val=threshold_val,
                    threshold_source=threshold_source,
                    threshold_captured_at=threshold_captured_at,
                    termination_reason=WINDOW_EDGE,
                )
            )
            ep_idx += 1
            current_obs = []

    return episodes, ep_idx


def _build_episode_record(
    obs: Sequence[Mapping[str, Any]],
    *,
    sensor_id: str,
    site_id: str,
    episode_index: int,
    threshold_type: str,
    threshold_val: float,
    threshold_source: str | None,
    threshold_captured_at: str | None,
    termination_reason: str,
) -> dict[str, Any]:
    first, last = obs[0], obs[-1]
    values = [float(r["value"]) for r in obs]
    peak = max(values)
    dur = _minutes(_t(first), _t(last))
    return {
        "episode_id": f"EP_{sensor_id}_{threshold_type}_{episode_index:04d}",
        "fg_sensor_id": sensor_id,
        "fg_site_id": site_id,
        "threshold_type": threshold_type,
        "threshold_value_m": _r(threshold_val),
        "threshold_source": threshold_source,
        "threshold_captured_at": threshold_captured_at,
        "start_utc": first["observation_time_utc"],
        "end_utc": last["observation_time_utc"],
        "start_local": first["observation_time_local"],
        "end_local": last["observation_time_local"],
        "observations_count": len(obs),
        "duration_minutes": _r(dur),
        "peak_level_m": _r(peak),
        "max_exceedance_m": _r(peak - threshold_val),
        "termination_reason": termination_reason,
        "continuity_status": "CONTINUOUS_OBSERVED",
        "temporal_validity": CURRENT_THRESHOLD_REFERENCE_ONLY,
        "evidence_level": PROVISIONAL_EXCEEDANCE_ONLY,
    }


def analyze_sensor_threshold(
    rows: Sequence[Mapping[str, Any]],
    threshold_info: Mapping[str, Any],
    config: EventIdentificationConfig,
) -> dict[str, Any]:
    """Identify exceedances and episodes for one sensor and one threshold."""
    ordered = sorted(rows, key=_t)
    usable_rows = [r for r in ordered if is_usable_observation(r, config)]
    thresh_val = float(threshold_info["value_m"])
    thresh_type = str(threshold_info["threshold_type"])

    exceedance_rows = [r for r in usable_rows if float(r["value"]) >= thresh_val]
    windows = observation_windows(ordered, config)

    all_episodes: list[dict[str, Any]] = []
    ep_idx = 1
    for w in windows:
        eps, ep_idx = segment_threshold_episodes(
            w, threshold_info, config, episode_index_start=ep_idx
        )
        all_episodes.extend(eps)

    reasons_count = Counter(ep["termination_reason"] for ep in all_episodes)
    durations = [ep["duration_minutes"] for ep in all_episodes]
    peaks = [ep["peak_level_m"] for ep in all_episodes]

    return {
        "threshold_type": thresh_type,
        "threshold_value_m": _r(thresh_val),
        "threshold_source": threshold_info.get("threshold_source"),
        "threshold_captured_at": threshold_info.get("captured_at"),
        "temporal_validity": CURRENT_THRESHOLD_REFERENCE_ONLY,
        "valid_at_observation_times": NOT_ESTABLISHED,
        "usable_observations": len(usable_rows),
        "exceedance_observations": len(exceedance_rows),
        "exceedance_percentage": _pct(len(exceedance_rows), len(usable_rows)),
        "contiguous_exceedance_episodes": len(all_episodes),
        "total_episode_duration_minutes": _r(sum(durations)) if durations else 0.0,
        "longest_episode_duration_minutes": _r(max(durations)) if durations else None,
        "peak_level_across_episodes_m": _r(max(peaks)) if peaks else None,
        "episodes_by_termination_reason": {
            ENDED_BELOW_THRESHOLD: reasons_count.get(ENDED_BELOW_THRESHOLD, 0),
            INTERRUPTED_BY_MISSING_DATA: reasons_count.get(INTERRUPTED_BY_MISSING_DATA, 0),
            WINDOW_EDGE: reasons_count.get(WINDOW_EDGE, 0),
        },
        "verified_historical_flood_events": 0,
        "episodes": all_episodes,
    }


def summarize_sensor(
    rows: Sequence[Mapping[str, Any]],
    thresholds: Sequence[Mapping[str, Any]],
    config: EventIdentificationConfig,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize threshold exceedances for all reference thresholds of one water-level sensor."""
    ordered = sorted(rows, key=_t)
    sensor_id = ordered[0]["fg_sensor_id"]
    site_id = ordered[0]["fg_site_id"]
    usable = [r for r in ordered if is_usable_observation(r, config)]

    # Filter eligible thresholds (WASPADA, AMARAN, BAHAYA)
    eligible_thresh = [
        t for t in thresholds if t.get("threshold_type") in set(ELIGIBLE_THRESHOLD_TYPES)
    ]
    # Sort thresholds: WASPADA, AMARAN, BAHAYA, then source/captured_at
    eligible_thresh.sort(
        key=lambda t: (
            ELIGIBLE_THRESHOLD_TYPES.index(t["threshold_type"]),
            t.get("threshold_source", ""),
            t.get("captured_at", ""),
        )
    )

    threshold_results = [analyze_sensor_threshold(ordered, t, config) for t in eligible_thresh]

    return {
        "fg_sensor_id": sensor_id,
        "fg_site_id": site_id,
        "station": dict(metadata or {}),
        "canonical_rows": len(ordered),
        "usable_rows": len(usable),
        "reference_thresholds_count": len(eligible_thresh),
        "threshold_evaluations": threshold_results,
        "verified_historical_flood_events": 0,
        "note": "Provisional threshold exceedances relative to current reference thresholds. "
        "Not verified historical flood events.",
    }


def _entry(ok: bool, requirement: str, **observed: Any) -> dict[str, Any]:
    return {
        "status": SUFFICIENT if ok else INSUFFICIENT,
        "requirement": requirement,
        "observed": observed,
    }


def assess_sufficiency(
    stations: Sequence[Mapping[str, Any]],
    config: EventIdentificationConfig,
) -> dict[str, dict[str, Any]]:
    """Assess whether the dataset supports event-level statistical analyses."""
    c = config
    max_usable = max((s["usable_rows"] for s in stations), default=0)
    total_episodes = sum(
        sum(ev["contiguous_exceedance_episodes"] for ev in s["threshold_evaluations"])
        for s in stations
    )
    max_episodes_per_sensor = max(
        (
            max(
                (ev["contiguous_exceedance_episodes"] for ev in s["threshold_evaluations"]),
                default=0,
            )
            for s in stations
        ),
        default=0,
    )

    return {
        "implementation_verification": _entry(
            True,
            "End-to-end execution of provisional threshold event segmentation",
            stations_evaluated=len(stations),
        ),
        "provisional_exceedance_detection": _entry(
            max_usable >= c.min_usable_for_analysis and bool(stations),
            f"At least one water-level station with >= {c.min_usable_for_analysis} usable rows "
            "and reference thresholds",
            max_usable_rows=max_usable,
            stations_with_thresholds=sum(
                1 for s in stations if s["reference_thresholds_count"] > 0
            ),
        ),
        "episode_sample_statistics": _entry(
            max_episodes_per_sensor >= c.min_episodes_for_statistics,
            f"At least one station with >= {c.min_episodes_for_statistics} distinct contiguous "
            "episodes for statistical duration/peak analysis",
            max_episodes_per_sensor=max_episodes_per_sensor,
            total_episodes_all_stations=total_episodes,
        ),
        "historical_flood_ground_truth": _entry(
            False,
            "Official event-dated flood dataset overlapping observation period (none exists; "
            "JPS threshold metadata is unversioned current reference only)",
            verified_flood_events=0,
            status_note=NO_OFFICIAL_GROUND_TRUTH,
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
    config: EventIdentificationConfig | None = None,
) -> dict[str, Any]:
    """Identify provisional threshold exceedances and episodes for one dataset version."""
    if not dataset_version:
        raise AnalysisContractError("dataset_version is required")
    cfg = config or EventIdentificationConfig()
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
            summarize_sensor(
                group,
                thresh_ref.get(sid, []),
                cfg,
                metadata=meta.get(sid),
            )
        )

    sufficiency = assess_sufficiency(stations, cfg)
    levels = [IMPLEMENTATION_VERIFICATION]
    if sufficiency["provisional_exceedance_detection"]["status"] == SUFFICIENT:
        levels.append(PROVISIONAL_EXCEEDANCE_DESCRIPTIVE)

    # Network aggregates
    tot_obs = sum(s["usable_rows"] for s in stations)
    tot_episodes_by_type: Counter[str] = Counter()
    tot_exceed_by_type: Counter[str] = Counter()
    for s in stations:
        for ev in s["threshold_evaluations"]:
            tt = ev["threshold_type"]
            tot_episodes_by_type[tt] += ev["contiguous_exceedance_episodes"]
            tot_exceed_by_type[tt] += ev["exceedance_observations"]

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
            "threshold_exceedance_observation": "a usable canonical water-level observation with "
            "value >= threshold_value (relative to current reference threshold)",
            "contiguous_exceedance_episode": "a maximal run of consecutive threshold exceedances "
            "with gap <= max_gap_minutes and no not-usable interruptions",
            "verified_historical_flood_event": "an official dated historical flood confirmation "
            "(none exists in current dataset; count = 0)",
            "termination_reason": {
                ENDED_BELOW_THRESHOLD: "observation returned strictly below threshold",
                INTERRUPTED_BY_MISSING_DATA: "episode broken by missing slot, not-usable row or "
                "gap > max_gap_minutes",
                WINDOW_EDGE: "episode truncated at observation window boundary",
            },
            "temporal_validity": CURRENT_THRESHOLD_REFERENCE_ONLY,
            "evidence_level": PROVISIONAL_EXCEEDANCE_ONLY,
        },
        "config": asdict(cfg),
        "network": {
            "stations_analysed": len(stations),
            "stations_with_reference_thresholds": sum(
                1 for s in stations if s["reference_thresholds_count"] > 0
            ),
            "usable_observations": tot_obs,
            "total_episodes_by_threshold_type": dict(sorted(tot_episodes_by_type.items())),
            "total_exceedance_observations_by_threshold_type": dict(
                sorted(tot_exceed_by_type.items())
            ),
            "verified_historical_flood_events": 0,
        },
        "stations": stations,
        "sufficiency": sufficiency,
        "evidence_levels_supported": levels,
        "scope": "Provisional threshold exceedance analysis based on current JPS reference "
        "thresholds. Does not constitute verified historical flood ground truth.",
    }


def write_summary(document: Mapping[str, Any], output_root: Path) -> tuple[Path, bool]:
    """Write-once ``<output_root>/<dataset_version>/threshold_events.json``."""
    return write_once_json(document, output_root, OUTPUT_FILE)
