"""Descriptive missingness of canonical observations, one sensor, measurement type and window at
a time.

Design: docs/MISSINGNESS_OUTAGE_ANALYSIS.md.

Input is the Phase 2 canonical table (``processed/observations/v1/<dataset_version>/``). Expected
5-min slots are generated only inside **cadence windows**: the time span of one JPS history
capture (the canonical rows of one ingestion batch of a ``*_history`` dataset), merged with
captures that overlap or touch it. A gap between separate captures, or a gap inside a capture
longer than ``max_absent_gap_minutes``, ends the window: its slots are never counted as missing.
Listing rows (irregular point-in-time snapshots) never get an expected cadence.

A slot is USABLE, MEASUREMENT_MISSING (a source row exists but its value is a marker such as
``-9999``, ``ERROR``, ``Tiada Data``, blank, non-numeric or a duplicate conflict) or ABSENT_SLOT
(no canonical row at that time). ``-9999`` and ``ERROR`` stay distinct, and the JPS severity
``ERROR`` field is recorded as a separate source state. No cause is attributed: a missing run is
an observed data gap, never a confirmed sensor, power or telemetry failure. Nothing is filled,
interpolated or turned into a feature. Pure and deterministic.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any, Final

import numpy as np

from floodguard.analysis.dataset import AnalysisContractError, select_measurement, write_once_json
from floodguard.preprocessing.units import MeasurementType
from floodguard.station_master import SensorType
from floodguard.validation.observations import SCHEMA_VERSION as OBSERVATION_SCHEMA
from floodguard.validation.quality_flags import INFORMATIONAL, QualityFlag
from floodguard.validation.summary import HISTORY_CADENCE
from floodguard.validation.summary import SCHEMA_VERSION as SUMMARY_SCHEMA

SCHEMA_VERSION = "missingness/v1"
OUTPUT_FILE = "missingness.json"
DECIMALS = 6
QUANTILE_METHOD: Final = "linear"  # numpy default, Hyndman & Fan (1996) type 7
CADENCE = HISTORY_CADENCE  # verified JPS history step (jps/HISTORICAL_AVAILABILITY.md)
CADENCE_MINUTES = int(CADENCE.total_seconds() // 60)
SLOTS_PER_DAY = 1440 // CADENCE_MINUTES

# (unit, sensor type, rule for a usable value) per canonical measurement type
MEASUREMENTS: Final = {
    MeasurementType.RAINFALL_INTERVAL: ("mm", SensorType.RAINFALL, "rainfall must be >= 0"),
    MeasurementType.RAINFALL_1H_TOTAL: ("mm", SensorType.RAINFALL, "rainfall must be >= 0"),
    MeasurementType.WATER_LEVEL: ("m", SensorType.WATER_LEVEL, "water level must be finite"),
}

# Slot / row states
USABLE = "USABLE"
ABSENT_SLOT = "ABSENT_SLOT"
LISTING_ONLY_SLOT = "LISTING_ONLY_SLOT"  # no history row; a listing-only canonical row exists
MISSING, OBSERVED = "MISSING", "USABLE"  # run states
# Missing types of a row that exists, in precedence order (first matching flag wins). A conflict
# row carries the union of its captures' flags, so DUPLICATE_CONFLICT must win over any marker.
MISSING_TYPES_BY_FLAG: Final = (
    (QualityFlag.DUPLICATE_CONFLICT, "DUPLICATE_CONFLICT"),
    (QualityFlag.VALUE_MISSING_SENTINEL, "SENTINEL_-9999"),
    (QualityFlag.VALUE_SOURCE_ERROR, "VALUE_ERROR"),
    (QualityFlag.VALUE_NO_DATA_MARKER, "TIADA_DATA"),
    (QualityFlag.VALUE_EMPTY, "BLANK"),
    (QualityFlag.VALUE_NON_NUMERIC, "NON_NUMERIC"),
)
OTHER_NOT_USABLE = "OTHER_NOT_USABLE"
ROW_MISSING_TYPES: Final = (*(t for _, t in MISSING_TYPES_BY_FLAG), OTHER_NOT_USABLE)
MISSING_TYPES: Final = (*ROW_MISSING_TYPES, LISTING_ONLY_SLOT, ABSENT_SLOT)
SEVERITY_FLAG = QualityFlag.SOURCE_SEVERITY_ERROR

OK = "OK"
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
SUFFICIENT, INSUFFICIENT = "SUFFICIENT", "INSUFFICIENT"
CADENCE_VERIFIED = "VERIFIED_5MIN_HISTORY_GRID"
CADENCE_OFF_GRID = "UNVERIFIED_OFF_GRID_ROWS"
POINT_IN_TIME = "POINT_IN_TIME_NO_EXPECTED_CADENCE"
SEPARATE_CAPTURES = "SEPARATE_CAPTURES"
GAP_EXCEEDS_MAX_ABSENT = "GAP_EXCEEDS_MAX_ABSENT_GAP"
BOUNDARY_EVIDENCE = "HISTORY_CAPTURE_ROWS"
ABSENT_NO_VALIDATED_ROW = "NO_VALIDATED_HISTORY_ROW_WITH_VALID_TIME"
ABSENT_UNRESOLVED = "UNRESOLVED"
IMPLEMENTATION_VERIFICATION = "IMPLEMENTATION_VERIFICATION"
WINDOW_DESCRIPTIVE = "WINDOW_DESCRIPTIVE"
NETWORK_HISTORICAL = "NETWORK_HISTORICAL"


@dataclass(frozen=True)
class MissingnessConfig:
    """Analysis guards (docs/MISSINGNESS_OUTAGE_ANALYSIS.md section 6), not physical thresholds.
    The 5-min cadence itself is not configurable: it is the verified JPS history step."""

    # Longest gap between consecutive history rows of one capture whose slots still count as
    # ABSENT_SLOT; a longer gap ends the window and its slots are left unclassified.
    max_absent_gap_minutes: float = 60.0
    quantiles: tuple[float, ...] = (0.25, 0.5, 0.75, 0.9)
    min_tail_count: int = 5  # quantile q needs >= this many runs expected on each side of it
    min_runs_mean: int = 5
    min_full_days_comparison: int = 30  # sensor / network comparison
    min_network_sensor_share: float = 0.5  # share of station-master sensors of the type
    min_full_days_per_month: int = 20
    min_years_per_calendar_month: int = 2  # seasonal / monsoon
    min_complete_years_long_term: int = 10
    monsoon_definition_source: str | None = None  # verified METMalaysia season boundaries

    def __post_init__(self) -> None:
        g = self.max_absent_gap_minutes
        if not (math.isfinite(g) and g >= CADENCE_MINUTES):
            raise ValueError(f"max_absent_gap_minutes must be finite and >= {CADENCE_MINUTES}")
        qs = self.quantiles
        if not qs or list(qs) != sorted(set(qs)) or not all(0 < q < 1 for q in qs):
            raise ValueError("quantiles must be unique, ascending and inside (0, 1)")
        if not 0 < self.min_network_sensor_share <= 1:
            raise ValueError("min_network_sensor_share must be in (0, 1]")
        for name in (
            "min_tail_count",
            "min_runs_mean",
            "min_full_days_comparison",
            "min_full_days_per_month",
            "min_years_per_calendar_month",
            "min_complete_years_long_term",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")

    def required_n(self, q: float) -> int:
        return math.ceil(round(self.min_tail_count / min(q, 1 - q), 9))


def _r(x: float) -> float:
    return round(float(x), DECIMALS) + 0.0


def _pct(part: int, whole: int) -> float | None:
    return _r(100 * part / whole) if whole else None


def _label(q: float) -> str:
    return f"p{q * 100:g}"


def _t(row: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(row["observation_time_utc"])


def _is_history(row: Mapping[str, Any]) -> bool:
    return any(p["dataset"].endswith("_history") for p in row["provenance"])


def row_state(row: Mapping[str, Any]) -> str:
    """USABLE or the missing type of a row that exists. Zero is a usable value, never missing."""
    if row["usable"]:
        return USABLE
    flags = set(row["quality_flags"])
    return next((t for f, t in MISSING_TYPES_BY_FLAG if f in flags), OTHER_NOT_USABLE)


def _check_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    for i, r in enumerate(rows):
        if not isinstance(r.get("quality_flags"), list) or not isinstance(r.get("datasets"), list):
            raise AnalysisContractError(f"row {i}: quality_flags/datasets not lists")
        prov = r.get("provenance")
        if not isinstance(prov, list) or not prov:
            raise AnalysisContractError(f"row {i}: provenance missing")
        for p in prov:
            ds = p.get("dataset") if isinstance(p, Mapping) else None
            if not isinstance(ds, str) or not p.get("ingestion_batch_id"):
                raise AnalysisContractError(f"row {i}: provenance without dataset/batch")
            if not ds.endswith(("_history", "_listing")):
                raise AnalysisContractError(f"row {i}: unknown source dataset {ds!r}")
        if r["usable"] and set(r["quality_flags"]) - INFORMATIONAL:
            raise AnalysisContractError(f"row {i}: usable row carries a blocking flag")
        if not r["usable"] and not set(r["quality_flags"]) - INFORMATIONAL:
            raise AnalysisContractError(f"row {i}: not-usable row has no blocking flag")


def select_observations(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    """Canonical rows by measurement type, each contract-checked (``select_measurement``: schema,
    unit, sensor type, identity, time zone, usable value, one row per sensor and instant)."""
    all_rows = list(rows)
    out: dict[str, list[Mapping[str, Any]]] = {}
    for mt, (unit, sensor_type, rule) in MEASUREMENTS.items():
        selected, _ = select_measurement(
            all_rows,
            measurement_type=mt,
            unit=unit,
            sensor_type=sensor_type,
            value_ok=(lambda v: v >= 0) if unit == "mm" else (lambda v: True),
            value_rule=rule,
        )
        _check_rows(selected)
        out[str(mt)] = selected
    return out


def _on_grid(t: datetime) -> bool:
    return t.timestamp() % CADENCE.total_seconds() == 0


def cadence_windows(
    history: Sequence[Mapping[str, Any]], config: MissingnessConfig
) -> tuple[list[list[Mapping[str, Any]]], list[dict[str, Any]]]:
    """(windows, boundaries) for one sensor's history rows of one measurement type.

    Each history capture (ingestion batch of a ``*_history`` dataset) spans its first to last
    row; captures that overlap or are at most one cadence step apart are merged. A window is then
    split wherever consecutive rows are more than ``max_absent_gap_minutes`` apart. ``boundaries``
    records every gap between consecutive windows and why it is not classified."""
    spans: dict[str, list[datetime]] = defaultdict(list)
    for r in history:
        for p in r["provenance"]:
            if p["dataset"].endswith("_history"):
                spans[p["ingestion_batch_id"]].append(_t(r))
    intervals = sorted((min(ts), max(ts)) for ts in spans.values())
    merged: list[list[datetime]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1] + CADENCE:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    ordered = sorted(history, key=_t)
    windows: list[list[Mapping[str, Any]]] = []
    boundaries: list[dict[str, Any]] = []
    max_gap = timedelta(minutes=config.max_absent_gap_minutes)
    k = 0
    for r in ordered:
        t = _t(r)
        while t > merged[k][1]:
            k += 1
        if windows:
            prev = _t(windows[-1][-1])
            new_capture = prev < merged[k][0]
            if new_capture or t - prev > max_gap:
                boundaries.append(
                    {
                        "after_window": len(windows) - 1,
                        "gap_from_utc": windows[-1][-1]["observation_time_utc"],
                        "gap_to_utc": r["observation_time_utc"],
                        "gap_minutes": _r((t - prev).total_seconds() / 60),
                        "reason": SEPARATE_CAPTURES if new_capture else GAP_EXCEEDS_MAX_ABSENT,
                        "slots_between_classified": False,
                    }
                )
                windows.append([r])
                continue
            windows[-1].append(r)
        else:
            windows.append([r])
    return windows, boundaries


def _run(
    state: str, slots: Sequence[tuple[datetime, str]], i: int, j: int, n: int
) -> dict[str, Any]:
    """Run over slots[i..j] inclusive of a window with ``n`` slots."""
    k = j - i + 1
    run: dict[str, Any] = {
        "state": state,
        "start_utc": slots[i][0].astimezone(UTC).isoformat(),
        "end_utc": slots[j][0].astimezone(UTC).isoformat(),
        "start_local": slots[i][0].isoformat(),
        "end_local": slots[j][0].isoformat(),
        "slots": k,
        "first_to_last_slot_minutes": (k - 1) * CADENCE_MINUTES,
        "slot_minutes": k * CADENCE_MINUTES,
        "at_window_start": i == 0,
        "at_window_end": j == n - 1,
    }
    if state == MISSING:
        run["slots_by_missing_type"] = dict(sorted(Counter(s for _, s in slots[i : j + 1]).items()))
    return run


def segment_runs(slots: Sequence[tuple[datetime, str]]) -> list[dict[str, Any]]:
    """Maximal runs of consecutive USABLE / missing slots, in time order. ``slots`` are the
    consecutive expected slots of ONE window, so a run can never cross a window boundary."""
    runs: list[dict[str, Any]] = []
    start = 0
    for i in range(1, len(slots) + 1):
        if i == len(slots) or (slots[i][1] == USABLE) != (slots[start][1] == USABLE):
            state = OBSERVED if slots[start][1] == USABLE else MISSING
            runs.append(_run(state, slots, start, i - 1, len(slots)))
            start = i
    return runs


def describe_lengths(lengths: Sequence[int], config: MissingnessConfig) -> dict[str, Any]:
    """Run-length summary (slots). Count/min/max are facts; mean and quantiles are guarded."""
    n = len(lengths)
    if n == 0:
        return {"count": 0, "status": "NO_RUNS"}
    a = np.sort(np.asarray(lengths, dtype=float))

    def guarded(value: float, required: int) -> dict[str, Any]:
        if n < required:
            return {"status": INSUFFICIENT_SAMPLE, "n": n, "required_n": required}
        return {"status": OK, "value": _r(value)}

    return {
        "count": n,
        "min_slots": int(a[0]),
        "max_slots": int(a[-1]),
        "mean_slots": guarded(float(a.mean()), config.min_runs_mean),
        "quantiles_slots": {
            _label(q): guarded(
                float(np.quantile(a, q, method=QUANTILE_METHOD)), config.required_n(q)
            )
            for q in config.quantiles
        },
    }


def _type_counts(states: Iterable[str]) -> dict[str, int]:
    c = Counter(states)
    return {t: c.get(t, 0) for t in MISSING_TYPES}


def _severity(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """JPS severity ``ERROR`` (a source QC field, meaning undocumented) by the row's state."""
    flagged = [row_state(r) for r in rows if SEVERITY_FLAG in r["quality_flags"]]
    return {
        "rows": len(flagged),
        "usable_rows": sum(s == USABLE for s in flagged),
        "measurement_missing_rows_by_type": dict(
            sorted(Counter(s for s in flagged if s != USABLE).items())
        ),
    }


def _full_local_days(slots: Sequence[tuple[datetime, str]]) -> set[date]:
    per_day = Counter(t.date() for t, _ in slots)
    return {d for d, n in per_day.items() if n >= SLOTS_PER_DAY}


def _longest(runs: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    return max(runs, key=lambda x: x["slots"], default=None)  # ties keep the earliest


def summarize_window(
    rows: Sequence[Mapping[str, Any]],
    index: int,
    config: MissingnessConfig,
    *,
    listing_only_times: Sequence[datetime] = (),
) -> tuple[dict[str, Any], set[date]]:
    """(summary, full local days) of one cadence window's history rows (time order)."""
    first, last = _t(rows[0]), _t(rows[-1])
    tz = datetime.fromisoformat(rows[0]["observation_time_local"]).tzinfo
    batches = sorted(
        {
            p["ingestion_batch_id"]
            for r in rows
            for p in r["provenance"]
            if p["dataset"].endswith("_history")
        }
    )
    row_states = [row_state(r) for r in rows]
    base: dict[str, Any] = {
        "window_index": index,
        "boundary_evidence": BOUNDARY_EVIDENCE,
        "ingestion_batch_ids": batches,
        "datasets": sorted({d for r in rows for d in r["datasets"]}),
        "start_utc": rows[0]["observation_time_utc"],
        "end_utc": rows[-1]["observation_time_utc"],
        "start_local": rows[0]["observation_time_local"],
        "end_local": rows[-1]["observation_time_local"],
        "source_rows": len(rows),
        "source_rows_usable": sum(s == USABLE for s in row_states),
        "source_rows_measurement_missing": sum(s != USABLE for s in row_states),
        "missing_flags": dict(
            sorted(Counter(f for r in rows if not r["usable"] for f in r["quality_flags"]).items())
        ),
        "source_severity_error": _severity(rows),
        "listing_only_rows_in_window": sum(first <= t <= last for t in listing_only_times),
    }
    off_grid = sum(not _on_grid(_t(r)) for r in rows)
    if off_grid:
        base |= {
            "cadence_status": CADENCE_OFF_GRID,
            "off_grid_rows": off_grid,
            "expected_slots": None,
            "missing_by_type": _type_counts(s for s in row_states if s != USABLE),
            "note": "rows off the 5-min grid: no expected slots, runs or coverage derived",
        }
        return base, set()
    by_time = {_t(r): s for r, s in zip(rows, row_states, strict=True)}
    listing_set = set(listing_only_times)
    n = int((last - first) / CADENCE) + 1
    slots = [
        (
            (first + i * CADENCE).astimezone(tz),
            by_time.get(
                first + i * CADENCE,
                LISTING_ONLY_SLOT if first + i * CADENCE in listing_set else ABSENT_SLOT,
            ),
        )
        for i in range(n)
    ]
    runs = segment_runs(slots)
    missing_runs = [x for x in runs if x["state"] == MISSING]
    usable_runs = [x for x in runs if x["state"] == OBSERVED]
    usable = sum(s == USABLE for _, s in slots)
    missing_slots = [(t, s) for t, s in slots if s != USABLE]
    days = _full_local_days(slots)
    return base | {
        "cadence_status": CADENCE_VERIFIED,
        "off_grid_rows": 0,
        "expected_slots": n,
        "usable_slots": usable,
        "missing_slots": n - usable,
        "coverage_percent": _pct(usable, n),
        "missing_percent": _pct(n - usable, n),
        "absent_slots": sum(s == ABSENT_SLOT for _, s in slots),
        "missing_by_type": _type_counts(s for _, s in missing_slots),
        "first_missing_utc": missing_slots[0][0].astimezone(UTC).isoformat()
        if missing_slots
        else None,
        "last_missing_utc": missing_slots[-1][0].astimezone(UTC).isoformat()
        if missing_slots
        else None,
        "starts_with_missing": slots[0][1] != USABLE,
        "ends_with_missing": slots[-1][1] != USABLE,
        "full_local_days": len(days),
        "missing_runs": {
            "count": len(missing_runs),
            "touching_window_boundary": sum(
                x["at_window_start"] or x["at_window_end"] for x in missing_runs
            ),
            "longest": _longest(missing_runs),
            "length": describe_lengths([x["slots"] for x in missing_runs], config),
        },
        "usable_runs": {"count": len(usable_runs), "longest": _longest(usable_runs)},
        "runs": runs,
    }, days


def _point_in_time(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    states = [row_state(r) for r in rows]
    return {
        "cadence_status": POINT_IN_TIME,
        "outage_interpretation": "NONE (no validated live cadence or freshness policy)",
        "rows": len(rows),
        "usable_rows": sum(s == USABLE for s in states),
        "measurement_missing_by_type": dict(
            sorted(Counter(s for s in states if s != USABLE).items())
        ),
        "datasets": sorted({d for r in rows for d in r["datasets"]}),
        "first_utc": rows[0]["observation_time_utc"],
        "last_utc": rows[-1]["observation_time_utc"],
        "source_severity_error": _severity(rows),
    }


def summarize_series(
    rows: Sequence[Mapping[str, Any]],
    measurement_type: str,
    config: MissingnessConfig,
    *,
    cadence_entry: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], set[date]]:
    """(summary, full local days) of one sensor's rows of one measurement type."""
    ordered = sorted(rows, key=_t)
    history = [r for r in ordered if _is_history(r)]
    listing = [r for r in ordered if not _is_history(r)]
    windows, boundaries = cadence_windows(history, config) if history else ([], [])
    summaries, days = [], set()
    listing_times = [_t(r) for r in listing]
    for i, w in enumerate(windows):
        s, d = summarize_window(w, i, config, listing_only_times=listing_times)
        summaries.append(s)
        days |= d
    excluded = (cadence_entry or {}).get("history_rows_not_in_canonical")
    return {
        "fg_sensor_id": ordered[0]["fg_sensor_id"],
        "fg_site_id": ordered[0]["fg_site_id"],
        "measurement_type": measurement_type,
        "unit": MEASUREMENTS[MeasurementType(measurement_type)][0],
        "station": dict(metadata or {}),
        "canonical_rows": len(ordered),
        "history_rows": len(history),
        "point_in_time_rows": len(listing),
        "cadence_windows": summaries,
        "window_boundaries": boundaries,
        "absent_slot_attribution": {
            "status": ABSENT_NO_VALIDATED_ROW if excluded == 0 else ABSENT_UNRESOLVED,
            "validated_history_rows_not_in_canonical": excluded,
            "note": "0 excluded validated history rows means an absent slot had no validated "
            "history row with a valid time; otherwise an absent slot may be a source row "
            "excluded from the canonical table (e.g. structurally invalid or future-dated)",
        },
        "point_in_time": _point_in_time(listing),
    }, days


def _entry(ok: bool, requirement: str, **observed: Any) -> dict[str, Any]:
    return {
        "status": SUFFICIENT if ok else INSUFFICIENT,
        "requirement": requirement,
        "observed": observed,
    }


def _calendar(days: set[date], config: MissingnessConfig) -> tuple[int, int]:
    """(calendar months with >= min_years_per_calendar_month complete years, complete years)."""
    per_month = Counter((d.year, d.month) for d in days)
    complete = [ym for ym, n in per_month.items() if n >= config.min_full_days_per_month]
    by_cal = Counter(m for _, m in complete)
    by_year = Counter(y for y, _ in complete)
    months_met = sum(1 for n in by_cal.values() if n >= config.min_years_per_calendar_month)
    return months_met, sum(1 for n in by_year.values() if n == 12)


def assess_sufficiency(
    series: Sequence[Mapping[str, Any]],
    days: Mapping[tuple[str, str], set[date]],
    sensors_in_master: Mapping[str, int],
    config: MissingnessConfig,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Per measurement type: which missingness analyses the data can support."""
    c = config
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for mt in sorted(MEASUREMENTS):
        ss = [s for s in series if s["measurement_type"] == mt]
        verified = [
            w for s in ss for w in s["cadence_windows"] if w["cadence_status"] == CADENCE_VERIFIED
        ]
        max_runs = max((w["missing_runs"]["count"] for w in verified), default=0)
        sensor_days = {sid: d for (sid, m), d in days.items() if m == mt}
        eligible = sorted(s for s, d in sensor_days.items() if len(d) >= c.min_full_days_comparison)
        overlap = max(  # best pair: one sensor without overlap must not hide a sharing pair
            (len(sensor_days[a] & sensor_days[b]) for a, b in combinations(eligible, 2)),
            default=0,
        )
        master_n = sensors_in_master.get(mt, 0)
        share = len(eligible) / master_n if master_n else 0.0
        cal = [_calendar(d, c) for d in sensor_days.values()]
        months_met = max((m for m, _ in cal), default=0)
        years = max((y for _, y in cal), default=0)
        seasonal = months_met == 12
        season_rule = (
            f"one sensor with all 12 calendar months complete (>= {c.min_full_days_per_month} "
            f"full windowed local days) in >= {c.min_years_per_calendar_month} years"
        )
        need_median = c.required_n(0.5)
        out[mt] = {
            "window_level_missingness": _entry(
                bool(verified),
                "one cadence window on the verified 5-min history grid",
                verified_windows=len(verified),
                point_in_time_only_sensors=sum(1 for s in ss if not s["cadence_windows"]),
            ),
            "run_length_analysis": _entry(
                max_runs >= need_median,
                f"one verified window with >= {need_median} missing runs (median length); "
                "counts and longest run are reported for every window regardless",
                max_missing_runs_per_window=max_runs,
            ),
            "sensor_comparison": _entry(
                len(eligible) >= 2 and overlap >= c.min_full_days_comparison,
                f">= 2 sensors each with >= {c.min_full_days_comparison} full windowed days, "
                f"sharing >= {c.min_full_days_comparison} of them",
                sensors_with_enough_days=len(eligible),
                max_pairwise_shared_full_days=overlap,
            ),
            "network_wide_comparison": _entry(
                len(eligible) >= 2
                and share >= c.min_network_sensor_share
                and overlap >= c.min_full_days_comparison,
                f"sensor-comparison rule met by >= {c.min_network_sensor_share:.0%} of the "
                "station-master sensors of this type",
                sensors_with_enough_days=len(eligible),
                sensors_in_station_master=master_n or None,
            ),
            "seasonal_missingness": _entry(
                seasonal, season_rule, max_calendar_months_meeting_rule=months_met
            ),
            "monsoon_missingness": _entry(
                seasonal and c.monsoon_definition_source is not None,
                f"{season_rule}, and verified METMalaysia monsoon boundaries",
                max_calendar_months_meeting_rule=months_met,
                monsoon_definition_source=c.monsoon_definition_source,
            ),
            "long_term_reliability": _entry(
                years >= c.min_complete_years_long_term,
                f"one sensor with >= {c.min_complete_years_long_term} complete years; even then "
                "this analysis reports coverage, never a reliable/unreliable label",
                max_complete_years_per_sensor=years,
            ),
            "live_outage_detection": _entry(
                False,
                "a separately validated live cadence and freshness policy (not established; "
                "listing updates are heterogeneous); historical missingness is not live freshness",
                validated_live_policy=None,
            ),
        }
    return out


def _network(series: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mt in sorted(MEASUREMENTS):
        ss = [s for s in series if s["measurement_type"] == mt]
        verified = [
            w for s in ss for w in s["cadence_windows"] if w["cadence_status"] == CADENCE_VERIFIED
        ]
        expected = sum(w["expected_slots"] for w in verified)
        usable = sum(w["usable_slots"] for w in verified)
        by_type: Counter[str] = Counter()
        for w in verified:
            by_type.update(w["missing_by_type"])
        pit = [s["point_in_time"] for s in ss if s["point_in_time"]]
        out[mt] = {
            "sensors_analysed": len(ss),
            "sensors_with_verified_windows": sum(
                1
                for s in ss
                if any(w["cadence_status"] == CADENCE_VERIFIED for w in s["cadence_windows"])
            ),
            "verified_windows": len(verified),
            "expected_slots": expected,
            "usable_slots": usable,
            "missing_slots": expected - usable,
            "missing_by_type": {t: by_type.get(t, 0) for t in MISSING_TYPES},
            "slot_weighted_coverage_percent": _pct(usable, expected),
            "point_in_time_rows": sum(p["rows"] for p in pit),
            "point_in_time_usable_rows": sum(p["usable_rows"] for p in pit),
        }
    out["calculation"] = (
        "per measurement type: sum of usable slots / sum of expected slots over verified windows "
        "(slot-weighted, so longer windows weigh more); not an average of per-sensor "
        "percentages, not combined across measurement types, not a reliability score"
    )
    return out


def analyze(
    rows: Iterable[Mapping[str, Any]],
    *,
    dataset_version: str,
    observations_sha256: str | None = None,
    quality_summary: Mapping[str, Any] | None = None,
    manifest: Mapping[str, Any] | None = None,
    station_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    station_master_sha256: str | None = None,
    config: MissingnessConfig | None = None,
) -> dict[str, Any]:
    """The machine-readable missingness summary for one processed dataset version."""
    if not dataset_version:
        raise AnalysisContractError("dataset_version is required")
    cfg = config or MissingnessConfig()
    selected = select_observations(rows)
    summary_series = (quality_summary or {}).get("series", {})
    by_type = (quality_summary or {}).get("canonical", {}).get("rows_by_measurement_type")
    # The quality summary is not hashed by the manifest; it must describe these very rows.
    if by_type is not None and any(by_type.get(mt, 0) != len(g) for mt, g in selected.items()):
        raise AnalysisContractError("quality summary row counts do not match the dataset")
    meta = station_metadata or {}
    series, days = [], {}
    for mt, group in selected.items():
        by_sensor: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for r in group:
            by_sensor[r["fg_sensor_id"]].append(r)
        for sid in sorted(by_sensor):
            g = by_sensor[sid]
            if len({r["fg_site_id"] for r in g}) != 1:
                raise AnalysisContractError(f"sensor {sid}: rows disagree on fg_site_id")
            entry = summary_series.get(f"{sid}/{mt}")
            if summary_series and entry is None:
                raise AnalysisContractError(f"{sid}/{mt}: no quality-summary entry for this series")
            # The quality summary is not hashed by the manifest; it must describe these rows.
            if entry is not None and (
                entry.get("rows") != len(g) or entry.get("usable") != sum(r["usable"] for r in g)
            ):
                raise AnalysisContractError(f"{sid}/{mt}: quality summary does not match the rows")
            s, d = summarize_series(
                g,
                mt,
                cfg,
                cadence_entry=(entry or {}).get("history_cadence"),
                metadata=meta.get(sid),
            )
            series.append(s)
            days[(sid, mt)] = d
    series.sort(key=lambda s: (s["measurement_type"], s["fg_sensor_id"]))
    in_master = {
        str(mt): sum(1 for m in meta.values() if m.get("sensor_type") == sensor_type)
        for mt, (_, sensor_type, _) in MEASUREMENTS.items()
    }
    sufficiency = assess_sufficiency(series, days, in_master, cfg)
    levels = [IMPLEMENTATION_VERIFICATION]
    if any(v["window_level_missingness"]["status"] == SUFFICIENT for v in sufficiency.values()):
        levels.append(WINDOW_DESCRIPTIVE)
    if any(
        v["network_wide_comparison"]["status"] == SUFFICIENT
        and v["seasonal_missingness"]["status"] == SUFFICIENT
        for v in sufficiency.values()
    ):
        levels.append(NETWORK_HISTORICAL)
    man = manifest or {}
    return {
        "analysis_schema_version": SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "input": {
            "observation_schema_version": OBSERVATION_SCHEMA,
            "quality_summary_schema_version": SUMMARY_SCHEMA,
            "dataset_components": man.get("components"),
            "observations_sha256": observations_sha256,
            "station_master_origin": man.get("station_master_origin"),
            "station_master_sha256": station_master_sha256,
            "station_master_lineage": None
            if station_master_sha256 is None
            else "sensors.csv verified against the manifest origin; sites.csv (district, basin) "
            "hashed here but not recorded in the Phase 2 manifest, so unverified",
            "rows_by_measurement_type": {mt: len(g) for mt, g in sorted(selected.items())},
            "excluded_quality_rows": (quality_summary or {})
            .get("canonical", {})
            .get("excluded_quality_rows"),
        },
        "definitions": {
            "expected_slot": f"a {CADENCE_MINUTES}-min grid time inside a cadence window",
            "cadence_window": "time span of one JPS history capture (canonical rows of one "
            "ingestion batch of a *_history dataset), merged with captures that overlap or are "
            f"<= {CADENCE_MINUTES} min apart, split where consecutive rows are more than "
            "max_absent_gap_minutes apart; its bounds are the first and last captured rows "
            "(the requested interval is not preserved by Phase 2), so no slot outside a capture "
            "is ever generated",
            "usable_slot": "a canonical row with usable = true (zero is usable)",
            "missing_observation": "an expected slot whose measurement is unusable: a source "
            "row with a missing marker or blocking flag, or no canonical row (ABSENT_SLOT)",
            "missing_types": {
                "SENTINEL_-9999": "value -9999 (VALUE_MISSING_SENTINEL)",
                "VALUE_ERROR": "value text ERROR (VALUE_SOURCE_ERROR); meaning undocumented",
                "TIADA_DATA": "value Tiada Data (VALUE_NO_DATA_MARKER)",
                "BLANK": "empty value (VALUE_EMPTY)",
                "NON_NUMERIC": "other non-numeric text (VALUE_NON_NUMERIC)",
                "DUPLICATE_CONFLICT": "captures of one instant disagree; unresolved",
                OTHER_NOT_USABLE: "not usable for another blocking flag",
                LISTING_ONLY_SLOT: "no history row at the expected slot, but a listing-only "
                "canonical row exists there (a history slot not filled; the listing row is "
                "counted in point_in_time)",
                ABSENT_SLOT: "no canonical row at the expected slot (source row absent or "
                "excluded; see absent_slot_attribution)",
            },
            "source_severity_error": "JPS history QC field severity = ERROR, recorded as a "
            "source state beside the value; its meaning is undocumented and it is never read "
            "as a device, power or communications failure",
            "missing_run": "maximal run of consecutive missing expected slots of one window",
            "usable_run": "maximal run of consecutive usable expected slots of one window",
            "run_duration": "slots = k; first_to_last_slot_minutes = (k - 1) x cadence; "
            "slot_minutes = k x cadence",
            "outage": "used only as 'observed data outage' = missing run; no cause (sensor, "
            "power, telemetry, communications) is attributed",
            "point_in_time": "listing rows: availability counts only, no cadence, run or outage",
            "quantile_rule": "q reported only if runs >= ceil(min_tail_count / min(q, 1 - q))",
            "quantile_method": f"numpy.quantile method={QUANTILE_METHOD!r} (Hyndman-Fan type 7)",
            "full_local_day": f"local date with all {SLOTS_PER_DAY} of its slots inside one "
            "verified window",
        },
        "config": asdict(cfg) | {"cadence_minutes": CADENCE_MINUTES},
        "network": _network(series),
        "series": series,
        "sufficiency": sufficiency,
        "evidence_levels_supported": levels,
        "cause_attributed": False,
        "imputation_performed": False,
        "scope": "Descriptive missingness of the captured windows only. No cause, reliability "
        "label, freshness status, imputation, feature or label is produced.",
    }


def write_summary(document: Mapping[str, Any], output_root: Path) -> tuple[Path, bool]:
    """Write-once ``<output_root>/<dataset_version>/missingness.json``."""
    return write_once_json(document, output_root, OUTPUT_FILE)
