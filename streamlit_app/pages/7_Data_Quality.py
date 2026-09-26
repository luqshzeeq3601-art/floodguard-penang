"""7 — Data Quality: established flags, coverage, runs (no new taxonomy)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from streamlit_app._shared import load_app_client, render_notices, render_state

from floodguard.dashboard import viewmodels
from floodguard.dashboard.formatting import quality_summary

st.title("Data Quality")
client = load_app_client()
stations = client.list_stations(limit=1000)
sensor_ids: list[str] = []
if stations.state == "ok" and isinstance(stations.data, list):
    for site in stations.data:
        if isinstance(site, dict):
            sensor_ids.extend(
                f"{site.get('fg_site_id')}/{sensor.get('fg_sensor_id')}"
                f":{sensor.get('measurement_type')}"
                for sensor in site.get("sensors", [])
                if isinstance(sensor, dict)
            )
choice = st.selectbox("Sensor", sorted(set(sensor_ids))) if sensor_ids else None
if choice is None:
    st.info("No sensors registered yet.")
    st.stop()
site_id, rest = choice.split("/", 1)
sensor_id, measurement = rest.split(":", 1)
observations = client.list_observations(
    sensor_id=sensor_id,
    measurement_type=measurement,
    start_utc="2000-01-01T00:00:00+00:00",
    end_utc="2100-01-01T00:00:00+00:00",
    limit=5000,
)
items: list[dict[str, object]] = []
if observations.state == "ok" and isinstance(observations.data, dict):
    raw_items = observations.data.get("items", [])
    items = [row for row in raw_items if isinstance(row, dict)]
summary = quality_summary(items)
# The page cannot know whether the backend serves real or synthetic rows;
# say so instead of picking a flattering label.
summary["evidence"] = "UNRESOLVED_SOURCE"
view = viewmodels.quality_vm(observations, summary)
if render_state(view, empty_text="No observations in range."):
    st.stop()
st.write(
    f"Total: {summary['total']} — usable: {summary['usable']} — "
    f"missing/unusable: {summary['missing_or_unusable']} — zeros: {summary['zero_values']}"
)
st.write("Flag counts (established vocabulary):")
st.dataframe(
    [{"flag": flag, "count": count} for flag, count in summary["flag_counts"].items()],
    use_container_width=True,
)
render_notices(view)
