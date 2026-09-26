"""2 — Live Monitoring: latest observation per sensor (facts, no verdicts)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
from streamlit_app._shared import fetch_observations, load_app_client, render_notices, render_state

from floodguard.dashboard import viewmodels
from floodguard.dashboard.formatting import format_age_minutes, format_value


def _instant(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


st.title("Live Monitoring")
client = load_app_client()
stations = client.list_stations(limit=1000)
latest_by_sensor: dict[str, dict[str, object]] = {}
failed_sensors: list[str] = []
if stations.state == "ok" and isinstance(stations.data, list):
    end = datetime.now(UTC).isoformat()
    start = "2000-01-01T00:00:00+00:00"
    for site in stations.data:
        if not isinstance(site, dict):
            continue
        for sensor in site.get("sensors", []):
            sensor_id = str(sensor.get("fg_sensor_id", ""))
            measurement = str(sensor.get("measurement_type", ""))
            unit = str(sensor.get("unit", ""))
            observations = fetch_observations(
                client,
                sensor_id=sensor_id,
                measurement_type=measurement,
                start_utc=start,
                end_utc=end,
            )
            if observations.state != "ok" or not isinstance(observations.data, dict):
                failed_sensors.append(sensor_id)
                latest_by_sensor[sensor_id] = {"value": None, "usable": None}
                continue
            items_raw = observations.data.get("items", [])
            items: list[dict[str, Any]] = [row for row in items_raw if isinstance(row, dict)]
            timed = [(row, _instant(row.get("observation_time_utc"))) for row in items]
            valid = [(row, moment) for row, moment in timed if moment is not None]
            if not valid:
                latest_by_sensor[sensor_id] = {"value": None, "usable": None}
                continue
            last = dict(max(valid, key=lambda pair: pair[1])[0])
            last["unit"] = unit
            latest_by_sensor[sensor_id] = last
if failed_sensors:
    shown = ", ".join(sorted(failed_sensors)[:5])
    suffix = "…" if len(failed_sensors) > 5 else ""
    st.warning(
        f"{len(failed_sensors)} sensor(s) could not be read ({shown}{suffix}); "
        "shown as unknown, not as missing data."
    )

view = viewmodels.monitoring_vm(stations, latest_by_sensor, now_utc=datetime.now(UTC))
if render_state(view, empty_text="No sensors registered yet."):
    st.stop()
rows = [
    {
        "site": row["site"],
        "sensor": row["sensor"],
        "type": row["type"],
        "latest": format_value(row["value"], row["unit"]),
        "usable": row["usable"],
        "observed_utc": row["observation_time_utc"],
        "age": format_age_minutes(row["age_minutes"]),
    }
    for row in view.tables["latest"]
]
st.dataframe(rows, use_container_width=True)
render_notices(view)
