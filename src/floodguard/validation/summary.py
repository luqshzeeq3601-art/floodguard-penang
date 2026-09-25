"""Factual data-quality summary of the validated and canonical layers (docs/HISTORICAL_PIPELINE.md).

Measured before anything is dropped: the validated section counts every quality row, including
quarantined and unusable ones. Gap analysis uses the nominal 5-minute JPS history cadence and only
history rows (listings are irregular snapshots); an absent slot is a grid time between a series'
first and last history row with no row at all. Nothing is filled or interpolated. Pure and
deterministic.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any

from floodguard.validation.observations import exclusion
from floodguard.validation.quality_flags import QualityFlag

SCHEMA_VERSION = "quality_summary/v1"
HISTORY_CADENCE = timedelta(minutes=5)  # data/metadata/jps/HISTORICAL_AVAILABILITY.md
MISSING_VALUE_FLAGS = frozenset(
    {
        QualityFlag.VALUE_MISSING_SENTINEL,
        QualityFlag.VALUE_SOURCE_ERROR,
        QualityFlag.VALUE_NO_DATA_MARKER,
        QualityFlag.VALUE_EMPTY,
        QualityFlag.VALUE_NON_NUMERIC,
    }
)


def _count(values: Iterable[Any]) -> dict[str, int]:
    return dict(sorted(Counter(str(v) for v in values).items()))


def _by(rows: Sequence[Mapping[str, Any]], key: str, field: str) -> dict[str, dict[str, int]]:
    groups: dict[str, list[Any]] = defaultdict(list)
    for r in rows:
        groups[str(r[key])].append(r[field])
    return {k: _count(v) for k, v in sorted(groups.items())}


def _missing_value_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return _count(f for r in rows for f in r["quality_flags"] if f in MISSING_VALUE_FLAGS)


def _cadence(history: Sequence[Mapping[str, Any]], step: timedelta) -> dict[str, Any]:
    """``history``: validated (quality) history rows with a UTC instant, eligible or not, so a
    row that exists but was excluded from the canonical table is present, not absent."""
    times = sorted({datetime.fromisoformat(r["observation_time_utc"]) for r in history})
    on_grid = [t for t in times if (t.minute * 60 + t.second) % step.total_seconds() == 0]
    if not on_grid:
        return {"history_rows": len(history), "on_grid_slots_present": 0}
    first, last = on_grid[0], on_grid[-1]
    expected = int((last - first) / step) + 1
    gaps = [(b - a) for a, b in pairwise(on_grid)]
    return {
        "history_rows": len(history),
        "history_rows_not_in_canonical": sum(exclusion(r) is not None for r in history),
        "history_start_utc": first.isoformat(),
        "history_end_utc": last.isoformat(),
        "expected_slots": expected,
        "on_grid_slots_present": len(on_grid),
        "absent_slots": expected - len(on_grid),
        "off_grid_rows": len(times) - len(on_grid),
        "largest_gap_minutes": int(max(gaps, default=step).total_seconds() // 60),
    }


def _series(
    obs: Sequence[Mapping[str, Any]], history: Sequence[Mapping[str, Any]], step: timedelta
) -> dict[str, Any]:
    days: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for o in obs:
        days[o["observation_time_local"][:10]].append(o)
    out: dict[str, Any] = {
        "fg_site_id": obs[0]["fg_site_id"],
        "sensor_type": obs[0]["sensor_type"],
        "first_observation_utc": obs[0]["observation_time_utc"],
        "last_observation_utc": obs[-1]["observation_time_utc"],
        "rows": len(obs),
        "usable": sum(o["usable"] for o in obs),
        "missing_value_flags": _missing_value_counts(obs),
        "duplicate_status": _count(o["duplicate_status"] for o in obs),
        "datasets": _count(d for o in obs for d in o["datasets"]),
        "per_local_date": {
            day: {
                "rows": len(rows),
                "usable": sum(o["usable"] for o in rows),
                "missing_value_rows": sum(
                    any(f in MISSING_VALUE_FLAGS for f in o["quality_flags"]) for o in rows
                ),
            }
            for day, rows in sorted(days.items())
        },
    }
    if history:  # series with history rows (listings are not gap-checked)
        out["history_cadence"] = _cadence(history, step)
    return out


def quality_summary(
    quality_rows: Sequence[Mapping[str, Any]],
    observations: Sequence[Mapping[str, Any]],
    excluded: Mapping[str, Mapping[str, int]],
    *,
    step: timedelta = HISTORY_CADENCE,
) -> dict[str, Any]:
    series: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    history: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for o in observations:  # already sorted by sensor, measurement type, time
        series[(o["fg_sensor_id"], o["measurement_type"])].append(o)
    for q in quality_rows:
        if q["dataset"].endswith("_history") and q["observation_time_utc"] and q["fg_sensor_id"]:
            history[(q["fg_sensor_id"], q["measurement_type"])].append(q)
    return {
        "summary_schema_version": SCHEMA_VERSION,
        "validated": {
            "rows": len(quality_rows),
            "usable": sum(r["usable"] for r in quality_rows),
            "rows_by_dataset": _count(r["dataset"] for r in quality_rows),
            "usable_by_dataset": _count(r["dataset"] for r in quality_rows if r["usable"]),
            "raw_file": _count(r["raw_file"] for r in quality_rows),
            "quality_flags": _count(f for r in quality_rows for f in r["quality_flags"]),
            "quality_flags_by_dataset": {
                ds: _count(
                    f for r in quality_rows if r["dataset"] == ds for f in r["quality_flags"]
                )
                for ds in sorted({r["dataset"] for r in quality_rows})
            },
            "timestamp_quality_flag": _by(quality_rows, "dataset", "timestamp_quality_flag"),
            "station_id_mapping_status": _by(quality_rows, "dataset", "station_id_mapping_status"),
            "unit_validation_status": _by(quality_rows, "dataset", "unit_validation_status"),
            "value_parse_status": _by(quality_rows, "dataset", "value_parse_status"),
        },
        "canonical": {
            "rows": len(observations),
            "usable": sum(o["usable"] for o in observations),
            "rows_by_measurement_type": _count(o["measurement_type"] for o in observations),
            "usable_by_measurement_type": _count(
                o["measurement_type"] for o in observations if o["usable"]
            ),
            "distinct_sensors_by_measurement_type": {
                mt: len({s for s, m in series if m == mt}) for mt in sorted({m for _, m in series})
            },
            "distinct_sites": len({o["fg_site_id"] for o in observations}),
            "duplicate_status": _count(o["duplicate_status"] for o in observations),
            "source_rows_collapsed": sum(o["duplicate_count"] - 1 for o in observations),
            "conflict_reason": _count(
                o["conflict_reason"] for o in observations if o["conflict_reason"]
            ),
            "missing_value_flags": _missing_value_counts(observations),
            "excluded_quality_rows": {k: dict(v) for k, v in excluded.items()},
            "observation_time_utc_range": (
                [
                    min(o["observation_time_utc"] for o in observations),
                    max(o["observation_time_utc"] for o in observations),
                ]
                if observations
                else None
            ),
        },
        "series": {
            f"{key[0]}/{key[1]}": _series(rows, history[key], step) for key, rows in series.items()
        },
    }
