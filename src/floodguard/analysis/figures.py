"""Baseline EDA figure generation for rainfall, water level, missingness, and events.

Design: docs/BASELINE_EDA_FIGURES.md.

Produces professional, factual figures:
- Gaps in water level are NEVER bridged with interpolated lines; missing periods are shown as gaps.
- Threshold lines are explicitly labeled as CURRENT_REFERENCE_ONLY.
- Outputs are saved to git-ignored data/analysis/figures/<dataset_version>/ (PNG format).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

# Use headless Agg backend
matplotlib.use("Agg")


def plot_rainfall_timeseries(
    rainfall_doc: dict[str, Any],
    processed_rows: list[dict[str, Any]],
    output_dir: Path,
) -> list[Path]:
    """Plot rainfall 5-minute interval time series and distribution."""
    dataset_version = rainfall_doc["dataset_version"]
    rf_rows = [
        r
        for r in processed_rows
        if r.get("measurement_type") == "RAINFALL_INTERVAL" and r.get("usable")
    ]
    if not rf_rows:
        return []

    by_sensor: dict[str, list[dict[str, Any]]] = {}
    for r in rf_rows:
        by_sensor.setdefault(r["fg_sensor_id"], []).append(r)

    generated: list[Path] = []
    for sid, srows in by_sensor.items():
        srows.sort(key=lambda x: x["observation_time_utc"])
        times = [datetime.fromisoformat(r["observation_time_local"]) for r in srows]
        values = [float(r["value"]) for r in srows]

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={"height_ratios": [2, 1]})

        # Time series (hyetograph)
        ax1.bar(times, values, width=0.003, color="#1f77b4", edgecolor="none", align="center")
        ax1.set_title(
            f"Rainfall 5-Min Intervals — Station {sid} (Dataset: {dataset_version})",
            fontsize=11,
            fontweight="bold",
        )
        ax1.set_ylabel("Rainfall (mm)")
        ax1.grid(True, linestyle="--", alpha=0.5)

        # Histogram of non-zero rainfall
        wet_vals = [v for v in values if v > 0]
        if wet_vals:
            ax2.hist(wet_vals, bins=20, color="#2ca02c", edgecolor="black", alpha=0.7)
            ax2.set_xlabel("Rainfall Intensity (mm / 5-min interval)")
            ax2.set_ylabel("Wet Intervals Count")
            ax2.set_title(f"Wet-Interval Distribution (n={len(wet_vals)})", fontsize=10)
        else:
            ax2.text(0.5, 0.5, "No wet intervals in sample (100% zero)", ha="center", va="center")
            ax2.set_axis_off()

        plt.tight_layout()
        out_file = output_dir / f"rainfall_timeseries_{sid}.png"
        fig.savefig(out_file, dpi=150)
        plt.close(fig)
        generated.append(out_file)

    return generated


def plot_water_level_timeseries(
    wl_doc: dict[str, Any],
    processed_rows: list[dict[str, Any]],
    output_dir: Path,
) -> list[Path]:
    """Plot water-level time series with explicit gaps and reference thresholds."""
    dataset_version = wl_doc["dataset_version"]
    wl_rows = [r for r in processed_rows if r.get("measurement_type") == "WATER_LEVEL"]
    if not wl_rows:
        return []

    thresholds_by_sensor = {
        s["fg_sensor_id"]: s.get("threshold_reference", {}).get("thresholds", [])
        for s in wl_doc.get("stations", [])
    }

    by_sensor: dict[str, list[dict[str, Any]]] = {}
    for r in wl_rows:
        by_sensor.setdefault(r["fg_sensor_id"], []).append(r)

    generated: list[Path] = []
    for sid, srows in by_sensor.items():
        srows.sort(key=lambda x: x["observation_time_utc"])

        # Split into continuous runs so missing intervals create disjoint lines
        # (never connected across gaps)
        segments: list[tuple[list[datetime], list[float]]] = []
        cur_t: list[datetime] = []
        cur_v: list[float] = []

        prev_t: datetime | None = None
        for r in srows:
            if not r.get("usable"):
                if cur_t:
                    segments.append((cur_t, cur_v))
                    cur_t, cur_v = [], []
                prev_t = None
                continue

            t = datetime.fromisoformat(r["observation_time_local"])
            v = float(r["value"])

            if prev_t is not None and (t - prev_t).total_seconds() > 300 and cur_t:
                segments.append((cur_t, cur_v))
                cur_t, cur_v = [], []

            cur_t.append(t)
            cur_v.append(v)
            prev_t = t

        if cur_t:
            segments.append((cur_t, cur_v))

        fig, ax = plt.subplots(figsize=(11, 5))

        for seg_t, seg_v in segments:
            ax.plot(
                np.asarray(seg_t),
                np.asarray(seg_v),
                color="#1f77b4",
                linewidth=1.5,
                marker="o",
                markersize=2.5,
            )

        thresh_colors = {"WASPADA": "#ff7f0e", "AMARAN": "#d62728", "BAHAYA": "#9467bd"}
        for th in thresholds_by_sensor.get(sid, []):
            ttype = th.get("threshold_type")
            tval = th.get("value_m")
            if ttype in thresh_colors and tval is not None:
                ax.axhline(
                    y=float(tval),
                    color=thresh_colors[ttype],
                    linestyle="--",
                    linewidth=1.2,
                    label=f"{ttype} ({tval:.2f}m) [CURRENT_REFERENCE_ONLY]",
                )

        ax.set_title(
            f"Water Level Time Series — Station {sid} (Dataset: {dataset_version})\n"
            "(Gaps represent missing data; thresholds are unversioned current references)",
            fontsize=10,
            fontweight="bold",
        )
        ax.set_ylabel("River Water Level (m)")
        ax.set_xlabel("Local Time (Asia/Kuala_Lumpur)")
        ax.grid(True, linestyle="--", alpha=0.5)
        if thresholds_by_sensor.get(sid):
            ax.legend(loc="upper right", fontsize=8)

        plt.tight_layout()
        out_file = output_dir / f"water_level_timeseries_{sid}.png"
        fig.savefig(out_file, dpi=150)
        plt.close(fig)
        generated.append(out_file)

    return generated


def plot_missingness_summary(
    missing_doc: dict[str, Any],
    output_dir: Path,
) -> list[Path]:
    """Plot missingness summary breakdown by sensor and type."""
    dataset_version = missing_doc["dataset_version"]
    series = missing_doc.get("series", [])
    if not series:
        return []

    fig, ax = plt.subplots(figsize=(10, 5))

    labels = []
    usable_counts = []
    missing_counts = []

    for s in series:
        sid = s["fg_sensor_id"]
        mtype = s["measurement_type"]
        labels.append(f"{sid}\n({mtype})")

        usable = sum(w.get("usable_slots", 0) for w in s.get("cadence_windows", []))
        missing = sum(w.get("missing_slots", 0) for w in s.get("cadence_windows", []))
        usable_counts.append(usable)
        missing_counts.append(missing)

    x = range(len(labels))
    width = 0.5

    ax.bar(x, usable_counts, width, label="Usable Slots", color="#2ca02c", alpha=0.8)
    ax.bar(
        x,
        missing_counts,
        width,
        bottom=usable_counts,
        label="Missing Slots",
        color="#d62728",
        alpha=0.8,
    )

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Expected 5-Min Slots")
    ax.set_title(
        f"Observation Availability & Missingness by Series (Dataset: {dataset_version})",
        fontsize=11,
        fontweight="bold",
    )
    ax.legend(loc="upper right")
    ax.grid(True, linestyle="--", alpha=0.4, axis="y")

    plt.tight_layout()
    out_file = output_dir / "missingness_breakdown.png"
    fig.savefig(out_file, dpi=150)
    plt.close(fig)
    return [out_file]


def produce_all_figures(
    analysis_root: Path,
    dataset_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Produce all baseline figures from analysis artifacts and canonical observations."""
    output_dir.mkdir(parents=True, exist_ok=True)

    data_bytes = (dataset_dir / "observations.jsonl").read_bytes()
    rows = [json.loads(line) for line in data_bytes.decode("utf-8").splitlines() if line.strip()]
    manifest = json.loads((dataset_dir / "dataset_manifest.json").read_text(encoding="utf-8"))
    dataset_version = manifest["dataset_version"]

    generated: list[str] = []

    # 1. Rainfall
    rf_file = analysis_root / "rainfall" / dataset_version / "rainfall_distribution.json"
    if rf_file.is_file():
        rf_doc = json.loads(rf_file.read_text(encoding="utf-8"))
        rf_figs = plot_rainfall_timeseries(rf_doc, rows, output_dir)
        generated.extend(str(f) for f in rf_figs)

    # 2. Water Level
    wl_file = analysis_root / "water_level" / dataset_version / "water_level_trends.json"
    if wl_file.is_file():
        wl_doc = json.loads(wl_file.read_text(encoding="utf-8"))
        wl_figs = plot_water_level_timeseries(wl_doc, rows, output_dir)
        generated.extend(str(f) for f in wl_figs)

    # 3. Missingness
    miss_file = analysis_root / "missingness" / dataset_version / "missingness.json"
    if miss_file.is_file():
        miss_doc = json.loads(miss_file.read_text(encoding="utf-8"))
        miss_figs = plot_missingness_summary(miss_doc, output_dir)
        generated.extend(str(f) for f in miss_figs)

    return {
        "dataset_version": dataset_version,
        "figures_directory": str(output_dir),
        "figures_count": len(generated),
        "figures": generated,
    }
