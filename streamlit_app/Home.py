"""FloodGuard Penang — internal ML/analytics home (Streamlit)."""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="FloodGuard Penang", page_icon="🌊", layout="wide")

st.title("🌊 FloodGuard Penang — internal analytics")
st.write(
    "Operational summaries, station analysis, data quality and model "
    "diagnostics for Pulau Pinang. Experimental research interface — not an "
    "official warning service. Use the sidebar pages."
)
st.caption(
    "Data: JPS (permission required), MET Malaysia via data.gov.my (CC BY 4.0), "
    "DOSM boundaries. Thresholds are current references only."
)
