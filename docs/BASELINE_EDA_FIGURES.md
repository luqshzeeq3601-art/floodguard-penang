# Baseline EDA Figures Specification

Status: implemented 2026-09-25 (Phase 3 task "Produce baseline EDA figures"). Code:
`scripts/produce_baseline_figures.py`; tests `tests/test_baseline_figures.py` (synthetic offline data).

## 1. Objectives and Integrity Principles

Baseline Exploratory Data Analysis (EDA) figures provide visual inspection tools for data quality, hydrological trends, and operational warning boundaries.

### Core Visualization Integrity Rules
1. **Never Connect Missing Gaps**: In water-level and rainfall time-series plots, missing periods (`-9999`, `ERROR`, absent slots) are displayed as discontinuous gaps. Lines are **never interpolated or bridged** across missing intervals.
2. **Explicit Threshold Labeling**: JPS threshold lines (Waspada, Amaran, Bahaya) are explicitly labeled with `[CURRENT_REFERENCE_ONLY]` to prevent visual misrepresentation of unversioned metadata as historical truth.
3. **Hyetograph Presentation**: Rainfall 5-minute interval values are presented as bar distributions (hyetographs) without curve smoothing.
4. **Licensing Protection**: Figures generated from proprietary/permission-required JPS captures remain strictly within local git-ignored directories (`data/analysis/figures/<dataset_version>/`).

## 2. Generated Figure Artifacts

For each processed dataset version, the following figure types are produced:

- `rainfall_timeseries_<sensor_id>.png`: 5-minute hyetograph and non-zero rainfall intensity histogram.
- `water_level_timeseries_<sensor_id>.png`: River level time series with explicit gap breaks and reference threshold markers.
- `missingness_breakdown.png`: Bar breakdown of usable vs. missing 5-minute expected slots across all series.

## 3. Execution CLI

```bash
.venv\Scripts\python.exe scripts\produce_baseline_figures.py --dataset data/processed/observations/v1/<dataset_version>
```
