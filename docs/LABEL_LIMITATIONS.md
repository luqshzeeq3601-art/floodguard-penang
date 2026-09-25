# FloodGuard Penang — Label Design Limitations and Feasibility Analysis

Status: completed 2026-09-25 (Phase 3 task "Document label limitations").

This document provides a comprehensive technical audit of the prediction targets, operational proxy labels, and hydrological limitations for the FloodGuard Penang early-warning platform.

---

## 1. Operational Proxy Labels vs. Verified Flood Ground Truth

The primary classification and early-warning tasks in FloodGuard are defined around **threshold exceedances and escalations** (+30, +60, and +120 minute horizons).

### Critical Distinction
- **Verified Flood Event**: An official, dated record of ground inundation, property damage, or river overtopping verified by NADMA, JPS, or state authorities. **No official event-dated flood catalogue overlapping 2024+ JPS history exists** in the public domain.
- **Operational Proxy Target**: A sensor-level water-level observation meeting or exceeding a designated threshold ($WL(t+h) \ge \theta$).
- **Rule**: A threshold exceedance must **never** be cited as a confirmed flood disaster without independent official verification.

---

## 2. Threshold Metadata Limitations

### 2.1 Lack of Historical Threshold Versioning
JPS publishes current threshold values on its live web portals and returns these current threshold values alongside historical query responses. JPS provides no historical threshold revision log. Therefore:
- Current thresholds are marked `CURRENT_THRESHOLD_REFERENCE_ONLY`.
- Historical applicability is marked `valid_at_observation_times: NOT_ESTABLISHED`.
- River dredging, gauge datum recalibration, or threshold adjustments over time could alter the true physical meaning of historical levels.

### 2.2 National vs. Penang JPS Portal Discrepancies
During data discovery (Phase 1), comparison of threshold values between the National Public Infobanjir portal and the Penang State portal revealed conflicting threshold levels for **3 out of 5** compared water-level stations (`data/metadata/gis/GIS_FLOOD_DATASETS.md`). All threshold records retain their source provenance (`threshold_source: JPS_STATE` vs `JPS_NATIONAL`).

### 2.3 Non-Flood Semantics of NORMAL
The `NORMAL` threshold is published as `0.00 m` on 14 out of 22 Penang stations and represents a baseline datum offset rather than a flood severity state. `NORMAL` is permanently excluded from label eligibility (`fg_label_eligible: false`).

---

## 3. Missing Data and Horizon Truncation

### 3.1 Strict Non-Imputation Rule for Future Labels
When evaluating a prediction target at origin $t$ for horizon $t + h$:
- If the observation at $t + h$ is missing (`-9999`, `ERROR`, `Tiada Data`, blank, or absent slot), the target is classified as `MISSING_FUTURE_TARGET`.
- **Never impute missing future outcomes as 0 (non-flood)**. Doing so would introduce severe label bias and create artificial false negatives during sensor outages that often coincide with severe weather.

### 3.2 Capture Window Boundary Truncation
In finite historical captures:
- Predictions at origin $t$ within the final 30 minutes cannot evaluate the +30 min target.
- Predictions within the final 60 minutes cannot evaluate the +60 min target.
- Predictions within the final 120 minutes cannot evaluate the +120 min target.
- These origins are properly marked `MISSING_FUTURE_TARGET` due to boundary censoring.

---

## 4. Class Imbalance and Sample Feasibility

### 4.1 Row-Level Exceedances vs. Independent Contiguous Episodes
A prolonged high-water event may produce 20–50 consecutive 5-minute intervals above threshold. Treating each interval as an independent positive training sample causes massive data leakage and false confidence in model performance.
- Valid model evaluation requires splitting by **independent continuous episodes** (hydrological storms/events).

### 4.2 Local Sample Sufficiency Assessment
On the verified local captures:
- Total rainfall history: 1 station-day (289 intervals, station 27608).
- Total water-level history: 2 station-days (stations 26460 and 27608).
- **Total flood / threshold events observed in local captures**: **0**.
- **Empirical Feasibility Status**: **INSUFFICIENT for ML training or statistical evaluation**.

---

## 5. Summary of Label Feasibility Matrix

| Requirement | Current Status | Blocker / Dependency |
|---|---|---|
| Multi-Horizon Target Logic (+30, +60, +120 min) | **VERIFIED & TESTED** | None (Code complete) |
| Deterministic Episode Segmentation | **VERIFIED & TESTED** | None (Code complete) |
| Missing-Target Safety Protocols | **VERIFIED & TESTED** | None (Code complete) |
| Class Imbalance Quantification Code | **VERIFIED & TESTED** | None (Code complete) |
| Penang-wide Multi-Year Training Data | **BLOCKED** | JPS Bulk History Permission |
| Chronological Train/Val/Test Split Viability | **INSUFFICIENT** | JPS Multi-Year History Required |
| Confirmed Flood Ground-Truth Labels | **NOT AVAILABLE** | Official Disaster Inundation Records |
