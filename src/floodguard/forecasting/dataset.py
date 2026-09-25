"""Point-in-time forecasting dataset: sequence windows and exact-horizon targets.

A sample at prediction origin ``t`` contains history only up to and including
``t``; targets sit at ``t + 30/60/120`` min. Rules:

- Backward-looking windows only; never bridge unrelated capture windows.
- No gap larger than ``max_gap_minutes`` (verified 5-min cadence) anywhere in
  the ``[t - lookback, t + horizon]`` span; missing slots reject the sample
  for that horizon (counted, never interpolated).
- Exact target instant required (no nearest-neighbor substitution, no
  interpolation to make a target evaluable).
- Missing water level is never zero; incomplete sequences are rejected.
- Stable sample identity: sensor, site, origin, dataset version, lookback,
  horizon (never bare row position).
- Per-sensor construction; absolute levels never pooled across stations here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any, Final

from floodguard.forecasting import (
    CADENCE_MINUTES,
    DEFAULT_LOOKBACK_MINUTES,
    HORIZONS_MINUTES,
    MAX_GAP_MINUTES,
    TARGET_AVAILABLE,
)

DATASET_SCHEMA_VERSION: Final[str] = "forecast_dataset/v1"


@dataclass(frozen=True)
class ForecastDatasetConfig:
    """Sequence-window configuration (project config, not hydrological law)."""

    lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES
    horizons_minutes: tuple[int, ...] = HORIZONS_MINUTES
    cadence_minutes: int = CADENCE_MINUTES
    max_gap_minutes: float = MAX_GAP_MINUTES
    dataset_version: str = "unknown"

    def __post_init__(self) -> None:
        if self.lookback_minutes <= 0:
            raise ValueError("lookback_minutes must be > 0")
        if self.lookback_minutes % self.cadence_minutes != 0:
            raise ValueError("lookback_minutes must be a multiple of cadence_minutes")
        if not self.horizons_minutes or any(h <= 0 for h in self.horizons_minutes):
            raise ValueError("horizons_minutes must be positive")
        if not self.max_gap_minutes > 0:
            raise ValueError("max_gap_minutes must be > 0")


@dataclass(frozen=True)
class ForecastSample:
    """One origin with its backward sequence and one horizon target."""

    fg_sensor_id: str
    fg_site_id: str
    origin_utc: str
    origin_local: str
    dataset_version: str
    lookback_minutes: int
    horizon_minutes: int
    input_times_utc: tuple[str, ...]
    input_levels_m: tuple[float, ...]
    origin_level_m: float
    target_level_m: float
    target_status: str = TARGET_AVAILABLE

    def sample_id(self) -> str:
        return (
            f"{self.fg_sensor_id}|{self.origin_utc}|"
            f"lb{self.lookback_minutes}|plus{self.horizon_minutes}m"
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["sample_id"] = self.sample_id()
        return payload


@dataclass(frozen=True)
class DatasetBuildReport:
    """Per-sensor accounting of sample construction."""

    fg_sensor_id: str
    usable_rows: int
    samples_built: int
    rejected_missing_input: int
    rejected_gap: int
    rejected_missing_target: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _is_usable(row: dict[str, Any]) -> bool:
    return bool(row.get("usable")) and isinstance(row.get("value"), (int, float))


def build_forecast_samples(
    canonical_rows: list[dict[str, Any]],
    config: ForecastDatasetConfig | None = None,
) -> tuple[dict[int, list[ForecastSample]], list[DatasetBuildReport]]:
    """Build per-horizon forecast samples from canonical WATER_LEVEL rows.

    Returns ({horizon: samples}, [per-sensor reports]). Only origins whose
    full input grid and exact target are usable become samples.
    """
    cfg = config or ForecastDatasetConfig()
    step = timedelta(minutes=cfg.cadence_minutes)
    lookback_steps = cfg.lookback_minutes // cfg.cadence_minutes

    by_sensor: dict[str, list[dict[str, Any]]] = {}
    for row in canonical_rows:
        if row.get("measurement_type") != "WATER_LEVEL":
            continue
        by_sensor.setdefault(str(row["fg_sensor_id"]), []).append(row)

    per_horizon: dict[int, list[ForecastSample]] = {h: [] for h in cfg.horizons_minutes}
    reports: list[DatasetBuildReport] = []

    for sensor_id, rows in sorted(by_sensor.items()):
        ordered = sorted(rows, key=lambda r: _parse_utc(str(r["observation_time_utc"])))
        usable_by_time = {
            _parse_utc(str(r["observation_time_utc"])): r for r in ordered if _is_usable(r)
        }
        usable_times = sorted(usable_by_time.keys())
        usable_set = set(usable_times)
        site_id = str(ordered[0].get("fg_site_id", ""))

        built = 0
        rej_input = 0
        rej_gap = 0
        rej_target = 0

        for origin in usable_times:
            input_times = [origin - step * (lookback_steps - 1 - k) for k in range(lookback_steps)]
            # Input grid must be fully usable (no missing-as-zero, no fill).
            if any(t not in usable_set for t in input_times):
                rej_input += 1
                continue
            # No gap bridging: consecutive usable rows across the span must
            # sit on the exact cadence grid (absent slots reject).
            span_start = input_times[0]
            in_span = [t for t in usable_times if span_start <= t <= origin]
            bridged = any(
                (b - a).total_seconds() / 60.0 > cfg.max_gap_minutes + 1e-9
                for a, b in pairwise(in_span)
            )
            if bridged:
                rej_gap += 1
                continue
            origin_row = usable_by_time[origin]
            levels = tuple(float(usable_by_time[t]["value"]) for t in input_times)
            for horizon in cfg.horizons_minutes:
                target_time = origin + timedelta(minutes=horizon)
                target_row = usable_by_time.get(target_time)
                if target_row is None:
                    rej_target += 1
                    continue
                # Target instant must be exactly t + h on the grid (it is, by
                # timed construction) and inside the same continuous run: every
                # consecutive pair in [origin, target] must respect max_gap.
                between = [t for t in usable_times if origin < t <= target_time]
                chain = [origin, *between]
                gapped = any(
                    (b - a).total_seconds() / 60.0 > cfg.max_gap_minutes + 1e-9
                    for a, b in pairwise(chain)
                )
                if gapped or (between and between[-1] != target_time):
                    rej_target += 1
                    continue
                per_horizon[horizon].append(
                    ForecastSample(
                        fg_sensor_id=sensor_id,
                        fg_site_id=site_id,
                        origin_utc=origin.isoformat(),
                        origin_local=str(origin_row.get("observation_time_local", "")),
                        dataset_version=cfg.dataset_version,
                        lookback_minutes=cfg.lookback_minutes,
                        horizon_minutes=horizon,
                        input_times_utc=tuple(t.isoformat() for t in input_times),
                        input_levels_m=levels,
                        origin_level_m=float(origin_row["value"]),
                        target_level_m=float(target_row["value"]),
                    )
                )
                built += 1

        reports.append(
            DatasetBuildReport(
                fg_sensor_id=sensor_id,
                usable_rows=len(usable_times),
                samples_built=built,
                rejected_missing_input=rej_input,
                rejected_gap=rej_gap,
                rejected_missing_target=rej_target,
            )
        )

    for horizon in per_horizon:
        per_horizon[horizon].sort(key=lambda s: (s.fg_sensor_id, s.origin_utc))
    return per_horizon, reports
