"""5 — Model Performance: status, goals-as-goals, no synthetic KPIs."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from streamlit_app._shared import load_app_client, render_notices, render_state

from floodguard.dashboard import viewmodels
from floodguard.dashboard.formatting import model_status_label

st.title("Model Performance")
client = load_app_client()
view = viewmodels.performance_vm(client.get_model_info())
if render_state(view):
    st.stop()
summary = view.summary
st.write(f"Status: **{summary['status']}** ({model_status_label(str(summary['status']))})")
st.write(f"Production model: {summary['production_model']}")
st.write(f"Model families seen in storage: {summary['families_seen'] or 'none'}")
st.write(f"Recall target: {summary['recall_target']}")
st.write(f"F1 target: {summary['f1_target']}")
render_notices(view)
