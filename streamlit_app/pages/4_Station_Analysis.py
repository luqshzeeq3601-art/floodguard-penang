"""4 — Station Analysis: info, map point, thresholds, gap-honest charts."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st
from streamlit_app._shared import (
    fetch_observations,
    load_app_client,
    render_notices,
    render_state,
    series_frame,
)

from floodguard.dashboard import viewmodels
from floodguard.dashboard.formatting import format_timestamp


def _format_captured(raw: object) -> object:
    from datetime import datetime

    if not isinstance(raw, str) or not raw:
        return raw
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return raw
    if moment.tzinfo is None:
        return raw
    return format_timestamp(moment)


st.title("Station Analysis")
client = load_app_client()
stations = client.list_stations(limit=1000)
options: dict[str, str] = {}
if stations.state == "ok" and isinstance(stations.data, list):
    for site in stations.data:
        if isinstance(site, dict):
            label = f"{site.get('site_name') or site.get('fg_site_id')} ({site.get('district')})"
            options[label] = str(site.get("fg_site_id", ""))
choice = st.selectbox("Site", sorted(options)) if options else None
if choice is None:
    st.info("No sites registered yet.")
    st.stop()
site_result = client.get_station(options[choice])
view = viewmodels.station_vm(site_result)
if render_state(view, empty_text="Site not found."):
    st.stop()
st.write(view.summary)
map_points = view.series.get("map_point", [])
if map_points:
    st.map(pd.DataFrame(map_points), use_container_width=True)
st.subheader("Site reference thresholds (current only, not per-sensor flood states)")
threshold_rows = [
    {**row, "captured_at": _format_captured(row.get("captured_at"))}
    for row in view.tables["thresholds"]
]
st.dataframe(threshold_rows, use_container_width=True)
render_notices(view)

st.subheader("Observations (gaps break lines; missing stays missing)")
sensors = (
    site_result.data.get("sensors", [])
    if site_result.state == "ok" and isinstance(site_result.data, dict)
    else []
)
for sensor in sensors:
    sensor_id = str(sensor.get("fg_sensor_id", ""))
    measurement = str(sensor.get("measurement_type", ""))
    unit = str(sensor.get("unit", ""))
    with st.expander(f"{sensor_id} — {measurement} ({unit})"):
        observations = fetch_observations(
            client,
            sensor_id=sensor_id,
            measurement_type=measurement,
            start_utc="2000-01-01T00:00:00+00:00",
            end_utc="2100-01-01T00:00:00+00:00",
        )
        chart = viewmodels.observation_series_vm(
            observations, measurement_type=measurement, unit=unit
        )
        if chart.state == "empty":
            st.info("No observations in range.")
            continue
        if chart.state != "ok":
            st.warning("Could not load this series.")
            continue
        frame = series_frame(chart.series["values"])
        if bool(frame["time"].isna().any()):
            st.warning("Some timestamps were unreadable and are excluded from the chart.")
            frame = frame.dropna(subset=["time"])
        st.line_chart(frame.set_index("time"), use_container_width=True)
        st.caption(
            f"{chart.summary['points']} points, "
            f"{chart.summary['missing_points']} missing, "
            f"{chart.summary['zero_points']} zeros ({unit})."
        )
