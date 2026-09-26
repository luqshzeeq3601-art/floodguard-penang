"""6 — SHAP Explainability: supported empty state (no eligible model)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from streamlit_app._shared import render_state

from floodguard.dashboard import viewmodels

st.title("SHAP Explainability")
view = viewmodels.shap_vm()
render_state(view, empty_text="No SHAP explanations available: no eligible model exists.")
