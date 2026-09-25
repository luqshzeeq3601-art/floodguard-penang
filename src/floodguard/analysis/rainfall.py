"""Distribution analysis of verified 5-min interval rainfall.

Design: docs/RAINFALL_DISTRIBUTION_ANALYSIS.md.

Input is the Phase 2 canonical table (``processed/observations/v1/<dataset_version>/``). Only rows
with ``measurement_type = RAINFALL_INTERVAL`` (JPS history ``raw``: rain in the 5-min interval
ending at the observation time), unit ``mm`` and ``usable = true`` enter the statistics; every
other rainfall field, the listing 1-hour total and water level are excluded by construction.

Descriptive EDA only: every statistic is computed per station (``fg_sensor_id``) over the values
as observed. Nothing is filled, windowed, lagged, transformed or labelled, and no threshold is
applied except the documented wet-interval definition. Estimates that need more data than the
window holds are returned as ``INSUFFICIENT_SAMPLE`` instead of a number, and
``assess_sufficiency`` states which analyses the data can support. Pure and deterministic.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import Any, Final

import numpy as np

from floodguard.analysis.dataset import (
    AnalysisContractError,
    ProcessedDataset,
    load_processed_dataset,
    load_station_metadata,
    select_measurement,
    to_json_bytes,
    write_once_json,
)
from floodguard.preprocessing.units import MeasurementType
from floodguard.station_master import SensorType
from floodguard.validation.observations import SCHEMA_VERSION as OBSERVATION_SCHEMA

__all__ = [
    "ProcessedDataset",
    "RainfallContractError",
    "load_processed_dataset",
    "load_station_metadata",
    "to_json_bytes",
]

SCHEMA_VERSION = "rainfall_distribution/v1"
MEASUREMENT = MeasurementType.RAINFALL_INTERVAL
UNIT = "mm"
INTERVAL_MINUTES = 5
DECIMALS = 6  # output rounding (mm, proportions); JPS reports rainfall to at most 1 decimal
OUTPUT_FILE = "rainfall_distribution.json"
QUANTILE_METHOD: Final = "linear"  # numpy default, Hyndman & Fan (1996) type 7

OK = "OK"
INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
SUFFICIENT, INSUFFICIENT = "SUFFICIENT", "INSUFFICIENT"
IMPLEMENTATION_VERIFICATION = "IMPLEMENTATION_VERIFICATION"
STATION_WINDOW_DESCRIPTIVE = "STATION_WINDOW_DESCRIPTIVE"
NETWORK_HISTORICAL = "NETWORK_HISTORICAL"


RainfallContractError = AnalysisContractError  # name kept for existing callers


@dataclass(frozen=True)
class RainfallAnalysisConfig:
    """Every rule is a documented, configurable parameter (docs/RAINFALL_DISTRIBUTION_ANALYSIS.md
    section 4). Defaults are conservative guards, not hydrological thresholds."""

    wet_threshold_mm: float = 0.0  # wet interval: value > this
    quantiles: tuple[float, ...] = (0.5, 0.75, 0.9, 0.95, 0.99)
    min_tail_count: int = 5  # quantile q needs >= this many values expected on each side of it
    min_samples_skewness: int = 30
    min_covered_days_descriptive: int = 1  # basic descriptive statistics
    min_wet_samples: int = 10
    min_day_coverage: float = 0.8  # covered day: >= this share of its 288 intervals usable
    min_covered_days_per_month: int = 20  # complete month
    min_years_per_calendar_month: int = 2  # seasonal / monsoon analyses
    min_overlap_covered_days: int = 30  # station comparison
    min_complete_years_extreme: int = 20  # extreme values / return periods
    monsoon_definition_source: str | None = None  # verified METMalaysia season boundaries

    def __post_init__(self) -> None:
        if not (math.isfinite(self.wet_threshold_mm) and self.wet_threshold_mm >= 0):
            raise ValueError("wet_threshold_mm must be finite and >= 0")
        qs = self.quantiles
        if not qs or list(qs) != sorted(set(qs)) or not all(0 < q < 1 for q in qs):
            raise ValueError("quantiles must be unique, ascending and inside (0, 1)")
        if not 0 < self.min_day_coverage <= 1:
            raise ValueError("min_day_coverage must be in (0, 1]")
        for name in (
            "min_tail_count",
            "min_samples_skewness",
            "min_covered_days_descriptive",
            "min_wet_samples",
            "min_covered_days_per_month",
            "min_years_per_calendar_month",
            "min_overlap_covered_days",
            "min_complete_years_extreme",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")
        if self.min_samples_skewness < 3:
            raise ValueError("min_samples_skewness must be >= 3")

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


def _skewness(a: np.ndarray, required: int) -> dict[str, Any]:
    """Adjusted Fisher-Pearson sample skewness G1 (as pandas ``Series.skew``)."""
    n = int(a.size)
    if n < required:
        return _guarded(None, n, required)
    if a[0] == a[-1]:  # sorted input: constant sample
        return {"status": "UNDEFINED_ZERO_VARIANCE", "n": n}
    d = a - a.mean()
    g1 = float(np.mean(d**3) / np.mean(d**2) ** 1.5)
    return _guarded(g1 * math.sqrt(n * (n - 1)) / (n - 2), n, required)


def describe(values: Sequence[float], config: RainfallAnalysisConfig) -> dict[str, Any]:
    """Descriptive statistics of one sample (mm per 5-min interval)."""
    a = np.sort(np.asarray(values, dtype=float))
    n = int(a.size)
    if n == 0:
        return {"count": 0, "status": "NO_DATA"}
    return {
        "count": n,
        "status": OK,
        "total_mm": _r(a.sum()),
        "mean_mm": _r(a.mean()),
        "median_mm": _guarded(float(np.median(a)), n, config.required_n(0.5)),
        "min_mm": _r(a[0]),
        "max_mm": _r(a[-1]),
        "std_mm": _guarded(float(a.std(ddof=1)) if n >= 2 else None, n, 2),
        "skewness": _skewness(a, config.min_samples_skewness),
        "quantiles_mm": {
            _label(q): _guarded(
                float(np.quantile(a, q, method=QUANTILE_METHOD)), n, config.required_n(q)
            )
            for q in config.quantiles
        },
    }


def _concentration(values: Sequence[float], min_wet: int) -> dict[str, Any] | None:
    """How few intervals carry the window's rainfall (None when the window is dry)."""
    total = math.fsum(values)
    if total <= 0:
        return None
    ranked = sorted((v for v in values if v > 0), reverse=True)
    if len(ranked) < min_wet:
        return _guarded(None, len(ranked), min_wet)
    running, k = 0.0, 0
    while running < total / 2:
        running += ranked[k]
        k += 1
    return {
        "largest_interval_share_of_total": _r(ranked[0] / total),
        "intervals_for_half_of_total": k,
        "share_of_usable_intervals_for_half_of_total": _r(k / len(values)),
    }


def _interval_date(row: Mapping[str, Any]) -> date:
    """Local calendar date of the interval's start (the value covers the 5 min ending at the
    row's local time, so a 00:00 value belongs to the previous day)."""
    local = datetime.fromisoformat(row["observation_time_local"])
    return (local - timedelta(minutes=INTERVAL_MINUTES)).date()


def covered_days(rows: Iterable[Mapping[str, Any]], config: RainfallAnalysisConfig) -> set[date]:
    """Local dates with at least ``min_day_coverage`` of their 288 intervals usable."""
    per_day = Counter(_interval_date(r) for r in rows if r["usable"])
    need = math.ceil(round(config.min_day_coverage * 24 * 60 / INTERVAL_MINUTES, 9))
    return {d for d, n in per_day.items() if n >= need}


def _calendar(days: set[date], config: RainfallAnalysisConfig) -> dict[str, Any]:
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


def summarize_station(
    rows: Sequence[Mapping[str, Any]],
    config: RainfallAnalysisConfig,
    *,
    cadence: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Summary of one sensor's selected rows (already contract-checked, one ``fg_sensor_id``)."""
    usable = sorted((r for r in rows if r["usable"]), key=lambda r: r["observation_time_utc"])
    values = [float(r["value"]) for r in usable]
    wet = [v for v in values if v > config.wet_threshold_mm]
    zero = sum(1 for v in values if v == 0.0)
    n = len(values)
    not_usable = [r for r in rows if not r["usable"]]
    cad = cadence or {}
    return {
        "fg_sensor_id": rows[0]["fg_sensor_id"],
        "fg_site_id": rows[0]["fg_site_id"],
        "station": dict(metadata or {}),
        "window": {
            "first_usable_utc": usable[0]["observation_time_utc"] if usable else None,
            "last_usable_utc": usable[-1]["observation_time_utc"] if usable else None,
            "first_usable_local": usable[0]["observation_time_local"] if usable else None,
            "last_usable_local": usable[-1]["observation_time_local"] if usable else None,
        },
        "coverage": {
            "rows_in_table": len(rows),
            "usable_intervals": n,
            "not_usable_intervals": len(not_usable),
            "not_usable_flags": dict(
                sorted(Counter(f for r in not_usable for f in r["quality_flags"]).items())
            ),
            "history_expected_slots": cad.get("expected_slots"),
            "history_absent_slots": cad.get("absent_slots"),
            "history_rows_not_in_canonical": cad.get("history_rows_not_in_canonical"),
        },
        "occurrence": {
            "zero_count": zero,
            "zero_proportion": _r(zero / n) if n else None,
            "wet_count": len(wet),
            "wet_proportion": _r(len(wet) / n) if n else None,
            "nonzero_below_wet_threshold_count": n - zero - len(wet),
        },
        "all_intervals": describe(values, config),
        "wet_only": describe(wet, config),
        "concentration": _concentration(values, config.min_wet_samples),
        "calendar": _calendar(covered_days(usable, config), config),
    }


def _entry(ok: bool, requirement: str, **observed: Any) -> dict[str, Any]:
    return {
        "status": SUFFICIENT if ok else INSUFFICIENT,
        "requirement": requirement,
        "observed": observed,
    }


def assess_sufficiency(
    stations: Sequence[Mapping[str, Any]],
    days_by_sensor: Mapping[str, set[date]],
    config: RainfallAnalysisConfig,
) -> dict[str, dict[str, Any]]:
    """Which analyses the analysed data can support (rules in the config)."""
    c = config
    max_days = max((s["calendar"]["covered_days"] for s in stations), default=0)
    max_wet = max((s["occurrence"]["wet_count"] for s in stations), default=0)
    required = {_label(q): c.required_n(q) for q in c.quantiles}
    eligible = [
        s["fg_sensor_id"]
        for s in stations
        if s["calendar"]["covered_days"] >= c.min_covered_days_descriptive
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
    return {
        "basic_descriptive": _entry(
            max_days >= c.min_covered_days_descriptive,
            f"one station with >= {c.min_covered_days_descriptive} covered day(s) "
            f"(>= {c.min_day_coverage:.0%} of a day's intervals usable)",
            max_covered_days_per_station=max_days,
        ),
        "wet_only_statistics": _entry(
            max_wet >= c.min_wet_samples,
            f"one station with >= {c.min_wet_samples} wet intervals",
            max_wet_intervals_per_station=max_wet,
        ),
        "wet_only_quantiles": _entry(
            max_wet >= max(required.values()),
            f"one station with enough wet intervals for every configured quantile "
            f"(>= {c.min_tail_count} expected beyond it)",
            max_wet_intervals_per_station=max_wet,
            required_wet_intervals_by_quantile=required,
            estimable_quantiles=[k for k, n in required.items() if max_wet >= n],
        ),
        "station_comparison": _entry(
            len(eligible) >= 2 and overlap >= c.min_overlap_covered_days,
            f">= 2 stations sharing >= {c.min_overlap_covered_days} covered days",
            stations_analysed=len(stations),
            stations_with_basic_sample=len(eligible),
            max_shared_covered_days=overlap,
        ),
        "seasonal_analysis": _entry(
            seasonal, season_rule, max_calendar_months_meeting_rule=months_met
        ),
        "monsoon_comparison": _entry(
            seasonal and c.monsoon_definition_source is not None,
            f"{season_rule}, and season boundaries from a verified METMalaysia definition "
            "(the configured source is recorded, not checked by code)",
            max_calendar_months_meeting_rule=months_met,
            monsoon_definition_source=c.monsoon_definition_source,
        ),
        "extreme_event_analysis": _entry(
            years >= c.min_complete_years_extreme,
            f"one station with >= {c.min_complete_years_extreme} complete years "
            "(annual-maximum / return-period methods)",
            max_complete_years_per_station=years,
        ),
    }


def select_rainfall_intervals(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], dict[str, int]]:
    """(RAINFALL_INTERVAL rows, counts of other measurement types). Contract violations raise."""
    return select_measurement(
        rows,
        measurement_type=MEASUREMENT,
        unit=UNIT,
        sensor_type=SensorType.RAINFALL,
        value_ok=lambda v: v >= 0,
        value_rule="rainfall must be >= 0",
    )


def analyze(
    rows: Iterable[Mapping[str, Any]],
    *,
    dataset_version: str,
    observations_sha256: str | None = None,
    quality_summary: Mapping[str, Any] | None = None,
    station_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    station_master_sha256: str | None = None,
    config: RainfallAnalysisConfig | None = None,
) -> dict[str, Any]:
    """The machine-readable rainfall-distribution summary for one processed dataset version."""
    if not dataset_version:
        raise RainfallContractError("dataset_version is required")
    cfg = config or RainfallAnalysisConfig()
    selected, excluded = select_rainfall_intervals(rows)
    by_sensor: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in selected:
        by_sensor[r["fg_sensor_id"]].append(r)
    series = (quality_summary or {}).get("series", {})
    meta = station_metadata or {}
    stations, days = [], {}
    for sid in sorted(by_sensor):
        group = by_sensor[sid]
        if len({r["fg_site_id"] for r in group}) != 1:
            raise RainfallContractError(f"sensor {sid}: rows disagree on fg_site_id")
        cadence = series.get(f"{sid}/{MEASUREMENT}", {}).get("history_cadence")
        stations.append(summarize_station(group, cfg, cadence=cadence, metadata=meta.get(sid)))
        days[sid] = covered_days(group, cfg)
    sufficiency = assess_sufficiency(stations, days, cfg)
    levels = [IMPLEMENTATION_VERIFICATION]
    if sufficiency["basic_descriptive"]["status"] == SUFFICIENT:
        levels.append(STATION_WINDOW_DESCRIPTIVE)
    if all(
        sufficiency[k]["status"] == SUFFICIENT for k in ("station_comparison", "seasonal_analysis")
    ):
        levels.append(NETWORK_HISTORICAL)
    rainfall_sensors = sum(1 for m in meta.values() if m.get("sensor_type") == SensorType.RAINFALL)
    return {
        "analysis_schema_version": SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "input": {
            "observation_schema_version": OBSERVATION_SCHEMA,
            "observations_sha256": observations_sha256,
            "station_master_sha256": station_master_sha256,
            "selection": {"measurement_type": str(MEASUREMENT), "unit": UNIT, "usable": True},
            "rainfall_interval_rows": len(selected),
            "excluded_rows_by_measurement_type": excluded,
        },
        "definitions": {
            "value": "rain in the 5-min interval ending at observation_time (mm per interval)",
            "wet_interval": f"usable value > {cfg.wet_threshold_mm} mm",
            "zero_interval": "usable value == 0 mm (true zero; missing values are never zero)",
            "quantile_method": f"numpy.quantile method={QUANTILE_METHOD!r} (Hyndman-Fan type 7)",
            "quantile_rule": "q reported only if n >= ceil(min_tail_count / min(q, 1 - q))",
            "std": "sample standard deviation (ddof=1)",
            "skewness": "adjusted Fisher-Pearson G1",
            "covered_day": "local date (of the interval start) with >= min_day_coverage of 288 "
            "intervals usable",
        },
        "config": asdict(cfg),
        "network": {
            "stations_analysed": len(stations),
            "rainfall_sensors_in_station_master": rainfall_sensors or None,
        },
        "stations": stations,
        "sufficiency": sufficiency,
        "evidence_levels_supported": levels,
        "scope": "Descriptive statistics of the analysed station windows only. Not a "
        "climatology, not a flood-trigger distribution; no labels, features or thresholds.",
    }


def write_summary(document: Mapping[str, Any], output_root: Path) -> tuple[Path, bool]:
    """Write-once ``<output_root>/<dataset_version>/rainfall_distribution.json``.
    Returns (path, written); identical existing content is a no-op, different content raises."""
    return write_once_json(document, output_root, OUTPUT_FILE)
