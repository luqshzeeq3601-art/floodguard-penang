"""Shared Streamlit helpers: client wiring, state rendering, safe frames.

No business logic here — pages call dashboard view-models and render the
result. DataFrames built here map ``None`` to ``NaN`` so charts break lines
at missing slots (never connect across gaps); zeros stay ``0.0``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from floodguard.dashboard import CACHE_TTL_SECONDS
from floodguard.dashboard.client import ApiResult, DashboardClient
from floodguard.dashboard.config import load_config
from floodguard.dashboard.viewmodels import (
    STATE_EMPTY,
    STATE_ERROR,
    STATE_OK,
    STATE_STALE,
    STATE_UNAVAILABLE,
    PageView,
)


@st.cache_resource(show_spinner=False)
def get_client(base_url: str, timeout_seconds: float) -> DashboardClient:
    """Process-cached API client (read-only; no user/session state inside)."""
    return DashboardClient(base_url=base_url, timeout_seconds=timeout_seconds)


def load_app_client() -> DashboardClient:
    """Client from environment configuration (validated at startup)."""
    config = load_config()
    return get_client(config.api_base_url, config.timeout_seconds)


def render_notices(view: PageView) -> None:
    """Render provenance/limitation notices (own strings only, no HTML)."""
    for notice in view.notices:
        st.caption(notice)


def render_state(view: PageView, *, empty_text: str = "Nothing to show yet.") -> bool:
    """Render non-ok states; return True when the caller should stop."""
    if view.state == STATE_OK:
        return False
    if view.state == STATE_EMPTY:
        st.info(empty_text)
    elif view.state == STATE_UNAVAILABLE:
        st.warning("Backend unavailable. Check the API service and retry.")
    elif view.state == STATE_STALE:
        st.warning("Data may be outdated; showing the last loaded snapshot.")
    else:
        st.error(f"Could not load this view ({STATE_ERROR}). Please retry later.")
    render_notices(view)
    return True


def series_frame(points: list[dict[str, Any]], time_key: str = "time") -> pd.DataFrame:
    """Build a chart frame with NaN gaps (missing stays missing)."""
    import math

    rows = [
        {
            "time": point.get(time_key),
            point.get("label", "value"): (
                float(point["value"]) if point.get("value") is not None else math.nan
            ),
        }
        for point in points
    ]
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
    return frame


def cache_ttl() -> int:
    """Explicit cache TTL (seconds) for read-only fetches."""
    return CACHE_TTL_SECONDS


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _cached_observations(
    base_url: str,
    timeout_seconds: float,
    sensor_id: str,
    measurement_type: str,
    start_utc: str,
    end_utc: str,
    limit: int,
) -> dict[str, object]:
    """Cached read-only observation fetch, keyed on primitives only.

    The key holds the API root plus every query input — never user/session
    state. TTL is explicit so changed lineage resurfaces promptly.
    """
    from floodguard.dashboard.client import ApiResult as _ApiResult

    scoped = DashboardClient(base_url=base_url, timeout_seconds=timeout_seconds)
    result: _ApiResult = scoped.list_observations(
        sensor_id=sensor_id,
        measurement_type=measurement_type,
        start_utc=start_utc,
        end_utc=end_utc,
        limit=limit,
    )
    return {"state": result.state, "data": result.data, "message": result.message}


def fetch_observations(
    client: DashboardClient,
    *,
    sensor_id: str,
    measurement_type: str,
    start_utc: str,
    end_utc: str,
    limit: int = 5000,
) -> ApiResult:
    """Observation fetch shared by pages (cached, TTL-explicit)."""
    from floodguard.dashboard.client import ApiResult as _ApiResult

    cached = _cached_observations(
        client.base_url,
        client.timeout_seconds,
        sensor_id,
        measurement_type,
        start_utc,
        end_utc,
        limit,
    )
    return _ApiResult(
        state=str(cached["state"]), data=cached["data"], message=str(cached["message"])
    )
