"""Deterministic synthetic datasets for Phase 5 software validation.

Source marker: SYNTHETIC_TEST_ONLY. These fixtures never share paths/naming
with real JPS datasets and must never be used for portfolio performance
claims. They provide chronological structure, synthetic positive/negative
episodes crossing and not crossing split boundaries, missing targets, and
balanced/imbalanced cases to exercise splits, metrics, training, and
selection plumbing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Final

from floodguard.modeling import HORIZONS_MINUTES, SYNTHETIC_SOURCE

SYNTHETIC_SCHEMA_VERSION: Final[str] = "synthetic/v1"


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def make_synthetic_joined_rows(
    *,
    n_origins: int = 72,
    start_utc: datetime | None = None,
    positive_blocks: tuple[tuple[int, int], ...] = ((10, 16), (40, 48)),
    step_minutes: int = 5,
    task_suffixes: tuple[str, ...] = ("exceed_waspada",),
    include_missing_tail: bool = True,
) -> list[dict[str, Any]]:
    """Build deterministic joined feature/label rows (SYNTHETIC_TEST_ONLY).

    Positive blocks are index ranges [start, end) whose future labels are 1;
    all other evaluable origins are 0. The final +120-minute tail is marked
    MISSING_FUTURE_TARGET when ``include_missing_tail`` is True.
    """
    start = start_utc or datetime(2030, 1, 1, tzinfo=UTC)
    rows: list[dict[str, Any]] = []
    positive_set = {i for block in positive_blocks for i in range(block[0], block[1])}
    for i in range(n_origins):
        origin = start + timedelta(minutes=step_minutes * i)
        is_positive = i in positive_set
        level = 2.5 if is_positive else 1.0
        row: dict[str, Any] = {
            "source": SYNTHETIC_SOURCE,
            "fg_sensor_id": "SYN_WL_1",
            "fg_site_id": "SYN_SITE_1",
            "prediction_origin_utc": _iso(origin),
            "prediction_origin_local": _iso(origin),
            "wl_level_m": level,
            "wl_rate_30m_m_per_h": 0.6 if is_positive else 0.0,
            "rf_roll_60m_sum_mm": 25.0 if is_positive else 0.0,
            "wl_dist_to_waspada_m": 0.5 if is_positive else -1.0,
            "time_hour": origin.hour,
            "time_hour_sin": 0.0,
            "station_latitude": 5.41,
            "station_longitude": 100.32,
        }
        for horizon in HORIZONS_MINUTES:
            # Real truncation differs per horizon (+30: 6 slots, +60: 12,
            # +120: 24 at 5-minute cadence); synthetic tails match (review L8).
            tail = horizon // step_minutes if include_missing_tail else 0
            status_key = f"target_plus_{horizon}m_status"
            if i >= n_origins - tail:
                row[status_key] = "MISSING_FUTURE_TARGET"
                row[f"target_plus_{horizon}m_future_level_m"] = None
                row[f"target_plus_{horizon}m_delta_level_m"] = None
                for suffix in task_suffixes:
                    row[f"target_plus_{horizon}m_{suffix}"] = None
            else:
                row[status_key] = "TARGET_EVALUATED"
                row[f"target_plus_{horizon}m_future_level_m"] = level
                row[f"target_plus_{horizon}m_delta_level_m"] = 0.0
                for suffix in task_suffixes:
                    row[f"target_plus_{horizon}m_{suffix}"] = 1 if is_positive else 0
        rows.append(row)
    return rows


def make_all_negative_rows(n_origins: int = 48, **kwargs: Any) -> list[dict[str, Any]]:
    """All-negative synthetic fixture (zero positives edge case)."""
    kwargs["positive_blocks"] = ()
    return make_synthetic_joined_rows(n_origins=n_origins, **kwargs)


def make_all_positive_rows(n_origins: int = 48, **kwargs: Any) -> list[dict[str, Any]]:
    """All-positive synthetic fixture (zero negatives edge case)."""
    kwargs["positive_blocks"] = ((0, n_origins),)
    kwargs["include_missing_tail"] = False
    return make_synthetic_joined_rows(n_origins=n_origins, **kwargs)
