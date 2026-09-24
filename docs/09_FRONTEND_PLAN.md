# React Operational UI Plan

## 1. Role

React/TypeScript is the polished operational/public-facing interface.

It is separate from Streamlit.

## 2. Primary Views

### Dashboard

- Penang map;
- station risk;
- latest observations;
- active warnings;
- data freshness.

### Station Detail

- latest rainfall;
- latest water level;
- trends;
- predictions at 30/60/120 min;
- model explanation;
- data-quality status.

### Alert History

- alert time;
- station;
- horizon;
- risk;
- model version;
- resolved/active status.

## 3. UX Principles

- Make the highest-risk information easy to scan.
- Avoid excessive warning colors.
- Separate observation from prediction.
- Show timestamps and units.
- Show stale/offline state explicitly.
- Do not hide uncertainty.

## 4. API Boundary

Frontend communicates through FastAPI.

The browser must not:

- load model artifacts;
- calculate ML features;
- contain secret API credentials;
- replicate server threshold logic.

## 5. Design System

Visual and interaction specification (tokens, views, data semantics, states): root `design.md`.
