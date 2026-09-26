"""1 — Overview: backend status, coverage, model eligibility."""

from __future__ import annotations

import sys
from pathlib import Path

# Pages run as top-level modules; repo root is needed for streamlit_app imports.
# (floodguard itself is installed editable and needs no path hack.)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from streamlit_app._shared import load_app_client, render_notices, render_state

from floodguard.dashboard import viewmodels

st.title("Overview")
client = load_app_client()
view = viewmodels.overview_vm(
    client.get_health(),
    client.get_ready(),
    client.list_stations(limit=1000),
    client.get_model_info(),
)
if render_state(view, empty_text="No stations registered yet."):
    st.stop()
summary = view.summary
col1, col2, col3, col4 = st.columns(4)
col1.metric("Backend", summary["backend"])
col2.metric("Sites", summary["sites"])
col3.metric("Sensors", summary["sensors"])
col4.metric("Database", summary["database"])
st.write(f"PostGIS: {summary['postgis']}")
st.write(f"Classification model: {summary['model_status']}")
st.write(f"Forecasting model: {summary['forecast_model_status']}")
render_notices(view)
