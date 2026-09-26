"""3 — Flood Prediction: stored forecasts with evidence (never invented)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from streamlit_app._shared import load_app_client, render_state

from floodguard.dashboard import viewmodels

st.title("Flood Prediction")
client = load_app_client()
stations = client.list_stations(limit=1000)
sensor_ids: list[str] = []
if stations.state == "ok" and isinstance(stations.data, list):
    for site in stations.data:
        if isinstance(site, dict):
            sensor_ids.extend(
                str(sensor.get("fg_sensor_id", ""))
                for sensor in site.get("sensors", [])
                if isinstance(sensor, dict)
            )
sensor_id = st.selectbox("Sensor", sorted(set(sensor_ids))) if sensor_ids else None
horizon = st.selectbox("Horizon (minutes)", (30, 60, 120))
if sensor_id is None:
    st.info("No sensors registered yet.")
    st.stop()
view = viewmodels.prediction_vm(
    client.list_predictions(sensor_id=sensor_id, horizon_minutes=int(horizon), limit=50),
    client.get_model_info(),
)
if render_state(view, empty_text="No stored forecasts for this sensor and horizon."):
    st.stop()
st.dataframe(view.tables["predictions"], use_container_width=True)

with st.expander("Stored alert records (records only — no delivery, no live alerts)"):
    alerts = client.list_alerts(sensor_id=sensor_id)
    if alerts.state == "ok" and isinstance(alerts.data, list) and alerts.data:
        st.dataframe(alerts.data, use_container_width=True)
    else:
        st.info("No stored alert records for this sensor.")
