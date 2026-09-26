# Phase 9 — Streamlit Contract: Internal Analytics UI

Status: **IMPLEMENTED** (2026-09-25, Phase 9). Library:
`src/floodguard/dashboard/` (`config`, `client`, `formatting`, `viewmodels`);
app: `streamlit_app/` (`Home.py`, `_shared.py`, `pages/` 1–8);
tests: `tests/test_dashboard_*.py` (3 files, 18 tests).

> Streamlit is the internal analyst interface, not a public frontend.
> Every page renders backend contracts with explicit states; nothing here
> invents alerts, predictions, probabilities, or model performance.

---

## 1. Architecture

```text
Streamlit page (thin render only)
  → dashboard.client.DashboardClient (single HTTP call site, typed states)
  → Phase 8 FastAPI (/health, /ready, /api/v1/*)
  → repositories / database
```

View-models (`dashboard/viewmodels.py`) are pure functions: backend results
in, render-ready structs out. Unit tests cover client, formatting, and all
view-models without importing Streamlit. App files are compile-checked and
boot-smoked (`streamlit run`, health endpoint `ok`).

## 2. Pages (TASKS.md Order)

| Page | Content contract |
|---|---|
| 1 Overview | Backend/database status, site/sensor counts, `NO_ELIGIBLE_MODEL` + `NO_ELIGIBLE_FORECAST_MODEL` |
| 2 Live Monitoring | Latest observation per sensor with factual age-in-minutes; per-sensor failures surfaced as unknown (never as missing); no freshness verdicts |
| 3 Flood Prediction | Stored forecasts with evidence labels; stored alert records (records only); empty when none |
| 4 Station Analysis | Info, WGS84 map point, site reference thresholds (current-only, NORMAL excluded), gap-honest charts |
| 5 Model Performance | Status verbatim, targets labeled goals, families seen in storage |
| 6 SHAP Explainability | Supported empty state (no eligible model; contributions ≠ causality) |
| 7 Data Quality | Established flag vocabulary, usable/missing/zero counts, unresolved-source evidence label |
| 8 Model Drift | Prerequisites-unmet empty state; station-volume context only, never drift verdicts |

## 3. Data Rules (Enforced)

- Missing chart slots are `None`→`NaN` (lines break); zeros stay `0.0`.
- Thresholds: Waspada/Amaran/Bahaya with provenance +
  `CURRENT_THRESHOLD_REFERENCE_ONLY`, site-level labeled; NORMAL excluded;
  never applied to rainfall.
- Units explicit everywhere (`mm`, `m`, `°C`); timestamps require tz-aware
  input and show `Asia/Kuala_Lumpur` + UTC; naive datetimes rejected.
- Evidence labels fixed: synthetic = "not real performance";
  local = "not Penang-wide"; unknown stays unknown.
- Quality aggregates reuse upstream flags; source markers are source states,
  never hardware diagnoses.
- Errors: backend unavailable/malformed/404/422/5xx/timeout all render
  without crashing and without stack traces.

## 4. Client, State, Config, Security

- One `DashboardClient` (base URL + timeout, injectable transport for
  tests); 10 s default timeout; responses validated against Phase 8 shapes.
- `st.cache_resource` keyed on `(base_url, timeout)`; `st.cache_data`
  keyed on query primitives with explicit 300 s TTL; no user/session state
  cached; no secrets anywhere; env-only config validated at startup.
- No `unsafe_allow_html`; backend strings render as text; IDs come from
  backend-sourced selectboxes (no SSRF surface); deterministic defaults.

## 5. Reviewer Findings (Independent Audit)

No HIGH. 2 MEDIUM + 10 LOW, all fixed or verified: cached per-sensor
fetches (M1), per-sensor failure surfacing (M2), naive-instant rejection
(L1), empty-shape guard (L2), instant-based latest pick without payload
mutation (L3), site-threshold labeling (L5), NaT warnings (L6), wired
helpers + stored-alerts expander (L7), `httpx` in the dashboard extra (L8).
L4 (hardcoded forecast absence) kept as declared-absence with notice;
L9 (CC BY 4.0 caption) verified against `DATA_LICENSING_AND_ACCESS.md` W1
and kept; L10 (`sys.path` bootstrap) accepted as documented Streamlit
multipage convention.
