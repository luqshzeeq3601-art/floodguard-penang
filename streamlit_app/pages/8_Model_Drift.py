"""8 — Model Drift: prerequisites unmet; volume context only, never verdicts."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from streamlit_app._shared import load_app_client, render_notices, render_state

from floodguard.dashboard import viewmodels

st.title("Model Drift")
client = load_app_client()
stations = client.list_stations(limit=1000)
volume: list[dict[str, object]] = []
if stations.state == "ok" and isinstance(stations.data, list):
    volume = [
        {
            "site": str(site.get("fg_site_id", "")),
            "sensors": len(site.get("sensors", [])),
            "district": site.get("district"),
        }
        for site in stations.data
        if isinstance(site, dict)
    ]
view = viewmodels.drift_vm(volume)
if render_state(view, empty_text="No station inventory available for volume context."):
    st.stop()
st.dataframe(view.tables["volume"], use_container_width=True)
render_notices(view)
