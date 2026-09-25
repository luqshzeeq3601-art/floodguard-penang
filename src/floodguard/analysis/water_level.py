"""Descriptive trend analysis of canonical river water level, one station at a time.

Design: docs/WATER_LEVEL_TREND_ANALYSIS.md.

Input is the Phase 2 canonical table (``processed/observations/v1/<dataset_version>/``). Only rows
with ``measurement_type = WATER_LEVEL`` and unit ``m`` enter; they are the JPS values Phase 2
promoted (history ``final`` and the listing ``Aras Air (m)(Graf)``). History ``raw``/``ecm``/
``clean`` and thresholds are not canonical observations and cannot enter.

Every statistic is per sensor (``fg_sensor_id``): absolute levels of different gauges have
different datums and are never pooled or averaged. Changes are backward-looking differences
between consecutive trend-eligible observations of one sensor; a not-usable row (``-9999``,
``ERROR``, blank), an absent slot or a gap longer than ``max_gap_minutes`` breaks continuity.
Nothing is interpolated or filled, no window is centred and no label, feature or threshold
event is produced. Current JPS thresholds, when supplied, are reference metadata only.
Pure and deterministic.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from itertools import combinations, pairwise
from pathlib import Path
from typing import Any, Final

import numpy as np

from floodguard.analysis.dataset import (
    AnalysisContractError,
    read_station_master,
    select_measurement,
    write_once_json,
)
from floodguard.preprocessing.units import MeasurementType
from floodguard.station_master import SensorType, ThresholdType
from floodguard.validation.observations import SCHEMA_VERSION as OBSERVATION_SCHEMA

SCHEMA_VERSION = "water_level_trends/v1"
MEASUREMENT = MeasurementType.WATER_LEVEL
UNIT = "m"
DECIMALS = 6  # output rounding (m, m/h, shares); JPS publishes water level to 2 decimals
OUTPUT_FILE = "water_level_trends.json"
QUANTILE_METHOD: Final = "linear"  # numpy default, Hyndman & Fan (1996) type 7

OK = "OK"
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
SPAN_EXCEEDS_GUARD = "SPAN_EXCEEDS_GUARD"
SPANS_BREAKS = "SPANS_BREAKS"
SUFFICIENT, INSUFFICIENT = "SUFFICIENT", "INSUFFICIENT"
IMPLEMENTATION_VERIFICATION = "IMPLEMENTATION_VERIFICATION"
STATION_WINDOW_DESCRIPTIVE = "STATION_WINDOW_DESCRIPTIVE"
NETWORK_HISTORICAL = "NETWORK_HISTORICAL"
RISING, FALLING, STABLE = "RISING", "FALLING", "STABLE"
CADENCE_VERIFIED = "VERIFIED_5MIN_HISTORY_GRID"
CADENCE_UNVERIFIED = "UNVERIFIED"
GAP_EXCEEDS_MAX = "GAP_EXCEEDS_MAX"
NOT_USABLE_ROW_BETWEEN = "NOT_USABLE_ROW_BETWEEN"
CURRENT_REFERENCE_ONLY = "CURRENT_REFERENCE_ONLY"
NOT_ESTABLISHED = "NOT_ESTABLISHED"
REFERENCE_THRESHOLD_TYPES = (ThresholdType.WASPADA, ThresholdType.AMARAN, ThresholdType.BAHAYA)


@dataclass(frozen=True)
class WaterLevelAnalysisConfig:
    """Every rule is a documented, configurable parameter (docs/WATER_LEVEL_TREND_ANALYSIS.md
    section 4). Defaults are conservative analysis guards, not hydrological thresholds."""

    # Longest gap between two consecutive trend-eligible observations that still counts as
    # continuous: one verified JPS history step (5 min), so any absent slot breaks continuity.
    max_gap_minutes: float = 5.0
    stable_tolerance_m: float = 0.0  # |change| <= this is STABLE; 0 = exact equality
    continuity_breaking_flags: tuple[str, ...] = ("SOURCE_SEVERITY_ERROR",)
    quantiles: tuple[float, ...] = (0.05, 0.25, 0.5, 0.75, 0.95)
    min_tail_count: int = 5  # quantile q needs >= this many values expected on each side of it
    min_usable_descriptive: int = 30
    min_valid_pairs: int = 30  # consecutive-change / rate-of-change summaries
    # Canonical rows further apart than this belong to different observation windows (separate
    # captures); level statistics are never pooled across windows.
    max_window_gap_minutes: float = 1440.0
    max_net_change_span_minutes: float = 1440.0  # net change first -> last only within one day
    expected_interval_minutes: int = 5  # covered-day denominator (verified history cadence)
    min_day_coverage: float = 0.8  # covered day: >= this share of the day's slots usable
    min_covered_days_per_month: int = 20
    min_years_per_calendar_month: int = 2  # seasonal / monsoon analyses
    min_overlap_covered_days: int = 30  # station comparison (coverage metrics only)
    min_complete_years_long_term: int = 10
    monsoon_definition_source: str | None = None  # verified METMalaysia season boundaries

    def __post_init__(self) -> None:
        for name in ("max_gap_minutes", "max_window_gap_minutes", "max_net_change_span_minutes"):
            v = getattr(self, name)
            if not (math.isfinite(v) and v > 0):
                raise ValueError(f"{name} must be finite and > 0")
        tol = self.stable_tolerance_m
        if not (math.isfinite(tol) and tol >= 0):
            raise ValueError("stable_tolerance_m must be finite and >= 0")
        if self.max_gap_minutes > self.max_window_gap_minutes:  # no pair may join two windows
            raise ValueError("max_gap_minutes must be <= max_window_gap_minutes")
        qs = self.quantiles
        if not qs or list(qs) != sorted(set(qs)) or not all(0 < q < 1 for q in qs):
            raise ValueError("quantiles must be unique, ascending and inside (0, 1)")
        if not 0 < self.min_day_coverage <= 1:
            raise ValueError("min_day_coverage must be in (0, 1]")
        if self.expected_interval_minutes < 1 or 1440 % self.expected_interval_minutes:
            raise ValueError("expected_interval_minutes must divide a day")
        for name in (
            "min_tail_count",
            "min_usable_descriptive",
            "min_valid_pairs",
            "min_covered_days_per_month",
            "min_years_per_calendar_month",
            "min_overlap_covered_days",
            "min_complete_years_long_term",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")

    def required_n(self, q: float) -> int:
        """Smallest sample for which q has >= ``min_tail_count`` values expected on each side."""
        return math.ceil(round(self.min_tail_count / min(q, 1 - q), 9))


def _r(x: float) -> float:
    return round(float(x), DECIMALS) + 0.0  # + 0.0 folds -0.0


def _label(q: float) -> str:
    return f"p{q * 100:g}"


def _guarded(value: float | None, n: int, required: int) -> dict[str, Any]:
    if n < required or value is None:
        return {"status": INSUFFICIENT_SAMPLE, "n": n, "required_n": required}
    return {"status": OK, "value": _r(value)}


def _t(row: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(row["observation_time_utc"])


def _minutes(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 60


def describe(
    values: Sequence[float], config: WaterLevelAnalysisConfig, unit: str
) -> dict[str, Any]:
    """Descriptive statistics of one sensor's sample (no pooling across sensors)."""
    a = np.sort(np.asarray(values, dtype=float))
    n = int(a.size)
    if n == 0:
        return {"count": 0, "status": "NO_DATA"}
    return {
        "count": n,
        "status": OK,
        f"mean_{unit}": _r(a.mean()),
        f"median_{unit}": _guarded(float(np.median(a)), n, config.required_n(0.5)),
        f"std_{unit}": _guarded(float(a.std(ddof=1)) if n >= 2 else None, n, 2),
        f"min_{unit}": _r(a[0]),
        f"max_{unit}": _r(a[-1]),
        f"range_{unit}": _r(a[-1] - a[0]),
        f"quantiles_{unit}": {
            _label(q): _guarded(
                float(np.quantile(a, q, method=QUANTILE_METHOD)), n, config.required_n(q)
            )
            for q in config.quantiles
        },
    }


def trend_eligible(row: Mapping[str, Any], config: WaterLevelAnalysisConfig) -> bool:
    """A usable row without a continuity-breaking flag (e.g. JPS severity ``ERROR``)."""
    return bool(row["usable"]) and not set(row["quality_flags"]) & set(
        config.continuity_breaking_flags
    )


def consecutive_changes(
    rows: Sequence[Mapping[str, Any]], config: WaterLevelAnalysisConfig
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[list[Mapping[str, Any]]]]:
    """(pairs, breaks, runs) over one sensor's rows in time order.

    A pair is two consecutive trend-eligible observations with no other row between them and a
    gap <= ``max_gap_minutes``; its change is attributed to the later time and uses only that
    observation and the one before it (backward-looking). Any other consecutive eligible
    observations form a break with its reason; runs are the maximal chains of pairs.
    """
    pairs: list[dict[str, Any]] = []
    breaks: list[dict[str, Any]] = []
    runs: list[list[Mapping[str, Any]]] = []
    prev: Mapping[str, Any] | None = None
    interrupted = False
    for r in sorted(rows, key=_t):
        if not trend_eligible(r, config):
            interrupted = prev is not None
            continue
        if prev is None:
            runs.append([r])
        else:
            gap = _minutes(_t(prev), _t(r))
            if interrupted or gap > config.max_gap_minutes:
                breaks.append(
                    {
                        "from_utc": prev["observation_time_utc"],
                        "to_utc": r["observation_time_utc"],
                        "gap_minutes": _r(gap),
                        "reason": NOT_USABLE_ROW_BETWEEN if interrupted else GAP_EXCEEDS_MAX,
                    }
                )
                runs.append([r])
            else:
                change = _r(float(r["value"]) - float(prev["value"]))
                tol = config.stable_tolerance_m
                pairs.append(
                    {
                        "from_utc": prev["observation_time_utc"],
                        "to_utc": r["observation_time_utc"],
                        "gap_minutes": _r(gap),
                        "change_m": change,
                        "rate_m_per_h": _r(change / (gap / 60)),
                        "direction": RISING
                        if change > tol
                        else FALLING
                        if change < -tol
                        else STABLE,
                    }
                )
                runs[-1].append(r)
        prev, interrupted = r, False
    return pairs, breaks, runs


def _run_summary(run: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "observations": len(run),
        "start_utc": run[0]["observation_time_utc"],
        "end_utc": run[-1]["observation_time_utc"],
        "duration_minutes": _r(_minutes(_t(run[0]), _t(run[-1]))),
        "net_change_m": _r(float(run[-1]["value"]) - float(run[0]["value"])),
    }


def covered_days(rows: Iterable[Mapping[str, Any]], config: WaterLevelAnalysisConfig) -> set[date]:
    """Local dates with at least ``min_day_coverage`` of their expected slots usable."""
    per_day = Counter(
        datetime.fromisoformat(r["observation_time_local"]).date() for r in rows if r["usable"]
    )
    slots = 1440 // config.expected_interval_minutes
    need = math.ceil(round(config.min_day_coverage * slots, 9))
    return {d for d, n in per_day.items() if n >= need}


def _calendar(days: set[date], config: WaterLevelAnalysisConfig) -> dict[str, Any]:
    per_month = Counter((d.year, d.month) for d in days)
    complete = sorted(ym for ym, n in per_month.items() if n >= config.min_covered_days_per_month)
    by_year = Counter(y for y, _ in complete)
    return {
        "covered_days": len(days),
        "complete_months": len(complete),
        "complete_years": sum(1 for n in by_year.values() if n == 12),
        "complete_months_by_calendar_month": {
            f"{m:02d}": n for m, n in sorted(Counter(m for _, m in complete).items())
        },
    }


def _threshold_reference(
    refs: Sequence[Mapping[str, Any]], last_usable: datetime | None
) -> dict[str, Any]:
    """Current JPS thresholds as captured, with provenance. Never a label, never historical."""
    entries, excluded = [], Counter[str]()
    for t in refs:
        if t["threshold_type"] not in REFERENCE_THRESHOLD_TYPES:
            excluded[str(t["threshold_type"])] += 1
            continue
        captured = datetime.fromisoformat(t["captured_at"])
        entries.append(
            {
                "threshold_type": t["threshold_type"],
                "value_m": _r(t["value_m"]),
                "threshold_source": t["threshold_source"],
                "captured_at": t["captured_at"],
                "valid_from": t.get("valid_from"),
                "temporal_validity": CURRENT_REFERENCE_ONLY,
                "valid_at_observation_times": NOT_ESTABLISHED,
                "captured_after_last_usable_observation": (
                    None if last_usable is None else captured > last_usable
                ),
            }
        )
    entries.sort(
        key=lambda e: (REFERENCE_THRESHOLD_TYPES.index(e["threshold_type"]), e["captured_at"])
    )
    return {
        "thresholds": entries,
        "excluded_threshold_types": dict(sorted(excluded.items())),
        "used_as_label": False,
        "note": "Current JPS values as captured; not versioned, not proven to apply at any "
        "observation time; descriptive reference only, never a label or target.",
    }


def observation_windows(
    rows: Sequence[Mapping[str, Any]], config: WaterLevelAnalysisConfig
) -> list[list[Mapping[str, Any]]]:
    """One sensor's rows in time order, split wherever consecutive canonical rows (usable or
    not) are more than ``max_window_gap_minutes`` apart."""
    windows: list[list[Mapping[str, Any]]] = []
    for r in sorted(rows, key=_t):
        if windows and _minutes(_t(windows[-1][-1]), _t(r)) <= config.max_window_gap_minutes:
            windows[-1].append(r)
        else:
            windows.append([r])
    return windows


def _window_summary(
    rows: Sequence[Mapping[str, Any]], config: WaterLevelAnalysisConfig
) -> dict[str, Any]:
    usable = [r for r in rows if r["usable"]]
    values = [float(r["value"]) for r in usable]
    n = len(usable)
    span = _minutes(_t(usable[0]), _t(usable[-1])) if n else None
    _, breaks, _ = consecutive_changes(rows, config)
    flagged = sum(1 for r in usable if not trend_eligible(r, config))
    if n < 2 or span is None:
        net: dict[str, Any] = _guarded(None, n, 2)
    elif breaks or flagged:  # the endpoints are not one continuous run
        net = {
            "status": SPANS_BREAKS,
            "span_minutes": _r(span),
            "breaks_between": len(breaks),
            "usable_rows_with_continuity_breaking_flags": flagged,
        }
    elif span > config.max_net_change_span_minutes:
        net = {"status": SPAN_EXCEEDS_GUARD, "span_minutes": _r(span)}
    else:
        net = {"status": OK, "value": _r(values[-1] - values[0]), "span_minutes": _r(span)}
    return {
        "first_row_utc": rows[0]["observation_time_utc"],
        "last_row_utc": rows[-1]["observation_time_utc"],
        "first_usable_utc": usable[0]["observation_time_utc"] if n else None,
        "last_usable_utc": usable[-1]["observation_time_utc"] if n else None,
        "first_usable_local": usable[0]["observation_time_local"] if n else None,
        "last_usable_local": usable[-1]["observation_time_local"] if n else None,
        "observed_duration_minutes": None if span is None else _r(span),
        "rows_by_dataset": dict(sorted(Counter(d for r in rows for d in r["datasets"]).items())),
        "canonical_rows": len(rows),
        "usable_rows": n,
        "usable_percent_of_rows": _r(100 * n / len(rows)),
        "levels": describe(values, config, "m"),
        "net_change_first_to_last_usable_m": net,
    }


def summarize_station(
    rows: Sequence[Mapping[str, Any]],
    config: WaterLevelAnalysisConfig,
    *,
    cadence: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    thresholds: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summary of one sensor's selected rows (already contract-checked, one ``fg_sensor_id``).
    Levels are summarised per observation window, never pooled across windows or sensors."""
    ordered = sorted(rows, key=_t)
    usable = [r for r in ordered if r["usable"]]
    not_usable = [r for r in ordered if not r["usable"]]
    n, total = len(usable), len(ordered)
    pairs, breaks, runs = consecutive_changes(ordered, config)
    cad = cadence or {}
    verified = bool(cad) and cad.get("off_grid_rows") == 0
    changes = [p["change_m"] for p in pairs]
    rates = [p["rate_m_per_h"] for p in pairs]
    usable_gaps = [_minutes(_t(a), _t(b)) for a, b in pairwise(usable)]
    longest = max(runs, key=len, default=None)  # max() keeps the earliest of equal runs
    return {
        "fg_sensor_id": ordered[0]["fg_sensor_id"],
        "fg_site_id": ordered[0]["fg_site_id"],
        "station": dict(metadata or {}),
        "coverage": {
            "canonical_rows": total,
            "usable_rows": n,
            "not_usable_rows": len(not_usable),
            "usable_percent_of_rows": _r(100 * n / total),
            "rows_by_dataset": dict(
                sorted(Counter(d for r in ordered for d in r["datasets"]).items())
            ),
            "not_usable_by_source_value": dict(
                sorted(
                    Counter(
                        f"{r.get('value_parse_status')}:{r.get('value_raw')}" for r in not_usable
                    ).items()
                )
            ),
            "not_usable_flags": dict(
                sorted(Counter(f for r in not_usable for f in r["quality_flags"]).items())
            ),
            "usable_rows_with_continuity_breaking_flags": sum(
                1 for r in usable if not trend_eligible(r, config)
            ),
            "history_expected_slots": cad.get("expected_slots"),
            "history_absent_slots": cad.get("absent_slots"),
            "history_rows_not_in_canonical": cad.get("history_rows_not_in_canonical"),
        },
        "observation_windows": [
            _window_summary(w, config) for w in observation_windows(ordered, config)
        ],
        "levels_pooled_across_windows": False,
        "continuity": {
            "cadence_status": CADENCE_VERIFIED if verified else CADENCE_UNVERIFIED,
            "max_gap_minutes": config.max_gap_minutes,
            "runs": len(runs),
            "longest_run": _run_summary(longest) if longest else None,
            "breaks": len(breaks),
            "breaks_by_reason": dict(sorted(Counter(b["reason"] for b in breaks).items())),
            "largest_gap_between_usable_minutes": _r(max(usable_gaps)) if usable_gaps else None,
        },
        "consecutive_changes": {
            "valid_pairs": len(pairs),
            "direction_counts": {
                d: sum(1 for p in pairs if p["direction"] == d) for d in (RISING, FALLING, STABLE)
            },
            "pair_gap_minutes": {
                f"{g:g}": k for g, k in sorted(Counter(p["gap_minutes"] for p in pairs).items())
            },
            "change": describe(changes, config, "m"),
            "rate_of_change": describe(rates, config, "m_per_h"),
            "max_abs_change_m": _r(max(map(abs, changes))) if changes else None,
            "pairs": pairs,
            "breaks": breaks,
        },
        "calendar": _calendar(covered_days(usable, config), config),
        "threshold_reference": (
            None
            if thresholds is None
            else _threshold_reference(thresholds, _t(usable[-1]) if n else None)
        ),
    }


def _max_window_usable(s: Mapping[str, Any]) -> int:
    return max((w["usable_rows"] for w in s["observation_windows"]), default=0)


def _entry(ok: bool, requirement: str, **observed: Any) -> dict[str, Any]:
    return {
        "status": SUFFICIENT if ok else INSUFFICIENT,
        "requirement": requirement,
        "observed": observed,
    }


def assess_sufficiency(
    stations: Sequence[Mapping[str, Any]],
    days_by_sensor: Mapping[str, set[date]],
    config: WaterLevelAnalysisConfig,
) -> dict[str, dict[str, Any]]:
    """Which analyses the analysed data can support. Every rule is a project analysis guard
    (configurable), not a universal statistical minimum."""
    c = config
    max_usable = max((_max_window_usable(s) for s in stations), default=0)
    max_pairs = max((s["consecutive_changes"]["valid_pairs"] for s in stations), default=0)
    max_pairs_verified = max(
        (
            s["consecutive_changes"]["valid_pairs"]
            for s in stations
            if s["continuity"]["cadence_status"] == CADENCE_VERIFIED
        ),
        default=0,
    )
    required = {_label(q): c.required_n(q) for q in c.quantiles}
    eligible = [
        s["fg_sensor_id"] for s in stations if _max_window_usable(s) >= c.min_usable_descriptive
    ]
    overlap = max(
        (len(days_by_sensor[a] & days_by_sensor[b]) for a, b in combinations(eligible, 2)),
        default=0,
    )
    months_met = max(
        (
            sum(
                1
                for n in s["calendar"]["complete_months_by_calendar_month"].values()
                if n >= c.min_years_per_calendar_month
            )
            for s in stations
        ),
        default=0,
    )
    seasonal = months_met == 12
    years = max((s["calendar"]["complete_years"] for s in stations), default=0)
    season_rule = (
        f"one station with all 12 calendar months complete (>= {c.min_covered_days_per_month} "
        f"covered days) in >= {c.min_years_per_calendar_month} years"
    )
    refs = sum(
        len(s["threshold_reference"]["thresholds"]) for s in stations if s["threshold_reference"]
    )
    return {
        "basic_descriptive": _entry(
            max_usable >= c.min_usable_descriptive,
            f"one station window with >= {c.min_usable_descriptive} usable observations",
            max_usable_per_window=max_usable,
        ),
        "quantiles": _entry(
            max_usable >= max(required.values()),
            f"one station window with enough usable observations for every configured "
            f"quantile (>= {c.min_tail_count} expected beyond it)",
            max_usable_per_window=max_usable,
            required_usable_by_quantile=required,
            estimable_quantiles=[k for k, n in required.items() if max_usable >= n],
        ),
        "consecutive_change": _entry(
            max_pairs >= c.min_valid_pairs,
            f"one station with >= {c.min_valid_pairs} continuous pairs "
            f"(gap <= {c.max_gap_minutes:g} min, no not-usable row between)",
            max_valid_pairs_per_station=max_pairs,
        ),
        "rate_of_change": _entry(
            max_pairs_verified >= c.min_valid_pairs,
            f"the consecutive-change rule on a station whose cadence is verified "
            f"({CADENCE_VERIFIED})",
            max_valid_pairs_on_verified_cadence=max_pairs_verified,
        ),
        "station_comparison": _entry(
            len(eligible) >= 2 and overlap >= c.min_overlap_covered_days,
            f">= 2 stations with the basic sample sharing >= {c.min_overlap_covered_days} "
            "covered days; coverage and quality metrics only, never raw levels (station datums "
            "differ)",
            stations_analysed=len(stations),
            stations_with_basic_sample=len(eligible),
            max_shared_covered_days=overlap,
        ),
        "seasonal_trend": _entry(
            seasonal, season_rule, max_calendar_months_meeting_rule=months_met
        ),
        "monsoon_comparison": _entry(
            seasonal and c.monsoon_definition_source is not None,
            f"{season_rule}, and season boundaries from a verified METMalaysia definition "
            "(the configured source is recorded, not checked by code)",
            max_calendar_months_meeting_rule=months_met,
            monsoon_definition_source=c.monsoon_definition_source,
        ),
        "threshold_event_analysis": _entry(
            False,
            "thresholds versioned with the period they applied to; JPS publishes current "
            "values only, so no historical threshold exceedance can be established here",
            versioned_thresholds=0,
            current_reference_thresholds=refs,
        ),
        "long_term_trend": _entry(
            years >= c.min_complete_years_long_term,
            f"one station with >= {c.min_complete_years_long_term} complete years",
            max_complete_years_per_station=years,
        ),
    }


def select_water_level(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], dict[str, int]]:
    """(WATER_LEVEL rows, counts of other measurement types). Contract violations raise."""
    selected, excluded = select_measurement(
        rows,
        measurement_type=MEASUREMENT,
        unit=UNIT,
        sensor_type=SensorType.WATER_LEVEL,
        value_ok=lambda v: True,  # negative levels are observed upstream (UNIT_POLICY.md)
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
    config: WaterLevelAnalysisConfig | None = None,
) -> dict[str, Any]:
    """The machine-readable water-level trend summary for one processed dataset version."""
    if not dataset_version:
        raise AnalysisContractError("dataset_version is required")
    cfg = config or WaterLevelAnalysisConfig()
    selected, excluded = select_water_level(rows)
    by_sensor: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in selected:
        by_sensor[r["fg_sensor_id"]].append(r)
    series = (quality_summary or {}).get("series", {})
    meta = station_metadata or {}
    stations, days = [], {}
    for sid in sorted(by_sensor):
        group = by_sensor[sid]
        if len({r["fg_site_id"] for r in group}) != 1:
            raise AnalysisContractError(f"sensor {sid}: rows disagree on fg_site_id")
        entry = series.get(f"{sid}/{MEASUREMENT}")
        # The summary is not hashed by the manifest; it must describe these very rows.
        if entry is not None and (
            entry.get("rows") != len(group)
            or entry.get("usable") != sum(1 for r in group if r["usable"])
        ):
            raise AnalysisContractError(f"sensor {sid}: quality summary does not match the rows")
        stations.append(
            summarize_station(
                group,
                cfg,
                cadence=(entry or {}).get("history_cadence"),
                metadata=meta.get(sid),
                thresholds=(
                    None if threshold_reference is None else threshold_reference.get(sid, [])
                ),
            )
        )
        days[sid] = covered_days(group, cfg)
    sufficiency = assess_sufficiency(stations, days, cfg)
    levels = [IMPLEMENTATION_VERIFICATION]
    if sufficiency["basic_descriptive"]["status"] == SUFFICIENT:
        levels.append(STATION_WINDOW_DESCRIPTIVE)
    if all(
        sufficiency[k]["status"] == SUFFICIENT for k in ("station_comparison", "seasonal_trend")
    ):
        levels.append(NETWORK_HISTORICAL)
    wl_sensors = sum(1 for m in meta.values() if m.get("sensor_type") == SensorType.WATER_LEVEL)
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
            "value": "canonical JPS water level (m, gauge datum; history `final` or listing "
            "`Aras Air (m)(Graf)` as promoted by Phase 2)",
            "trend_eligible": "usable row without a continuity-breaking flag",
            "pair": "two consecutive trend-eligible observations of one sensor with no row "
            "between them and gap <= max_gap_minutes; change = later - earlier, attributed to "
            "the later time (backward-looking)",
            "rate_of_change": "change_m / gap in hours of that pair",
            "direction": "RISING change > stable_tolerance_m, FALLING change < "
            "-stable_tolerance_m, else STABLE; with tolerance 0 STABLE is exact equality, not a "
            "hydrological stability threshold",
            "run": "maximal chain of consecutive pairs",
            "observation_window": "a sensor's canonical rows split where consecutive rows are "
            "more than max_window_gap_minutes apart; levels are summarised per window, never "
            "pooled across windows or sensors",
            "net_change": "last - first usable value of one window, only if the window's usable "
            "values form one continuous run (else SPANS_BREAKS) and span <= "
            "max_net_change_span_minutes",
            "quantile_method": f"numpy.quantile method={QUANTILE_METHOD!r} (Hyndman-Fan type 7)",
            "quantile_rule": "q reported only if n >= ceil(min_tail_count / min(q, 1 - q))",
            "std": "sample standard deviation (ddof=1)",
            "covered_day": "local date with >= min_day_coverage of its expected slots usable",
            "threshold_reference": "current JPS thresholds with source and captured_at; "
            f"{CURRENT_REFERENCE_ONLY}, never a label",
        },
        "config": asdict(cfg),
        "network": {
            "stations_analysed": len(stations),
            "water_level_sensors_in_station_master": wl_sensors or None,
            "stations_with_basic_sample": sufficiency["station_comparison"]["observed"][
                "stations_with_basic_sample"
            ],
            "canonical_rows": sum(s["coverage"]["canonical_rows"] for s in stations),
            "usable_rows": sum(s["coverage"]["usable_rows"] for s in stations),
            "cross_station_level_aggregation": "NONE (gauge datums differ)",
        },
        "stations": stations,
        "sufficiency": sufficiency,
        "evidence_levels_supported": levels,
        "scope": "Descriptive per-station statistics of the analysed windows only. Not a "
        "hydrological regime, seasonal or long-term trend; no labels, features, threshold "
        "events or predictive windows.",
    }


def load_threshold_reference(
    station_master_dir: Path,
) -> tuple[dict[str, list[dict[str, Any]]], str]:
    """(``fg_sensor_id`` -> captured JPS threshold rows; SHA-256 of thresholds.csv). Values are
    current at ``captured_at``; ``fg_label_eligible`` is not read."""
    tables, digest = read_station_master(station_master_dir, ("thresholds.csv",))
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for i, t in enumerate(tables["thresholds.csv"]):
        if t.get("unit") != UNIT:
            raise AnalysisContractError(f"threshold row {i}: unit {t.get('unit')!r} != m")
        try:
            value = float(t["value"])
            captured = datetime.fromisoformat(t["captured_at"])
        except (KeyError, ValueError) as e:
            raise AnalysisContractError(f"threshold row {i}: {e}") from e
        if captured.tzinfo is None:
            raise AnalysisContractError(f"threshold row {i}: captured_at has no UTC offset")
        if not math.isfinite(value) or t.get("threshold_type") not in set(ThresholdType):
            raise AnalysisContractError(f"threshold row {i}: invalid type or value")
        out[t["fg_sensor_id"]].append(
            {
                "threshold_type": t["threshold_type"],
                "value_m": value,
                "threshold_source": t.get("threshold_source") or None,
                "captured_at": t["captured_at"],
                "valid_from": t.get("valid_from") or None,
            }
        )
    return dict(out), digest


def write_summary(document: Mapping[str, Any], output_root: Path) -> tuple[Path, bool]:
    """Write-once ``<output_root>/<dataset_version>/water_level_trends.json``."""
    return write_once_json(document, output_root, OUTPUT_FILE)
