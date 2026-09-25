# Prediction Label and Target Definition (+30, +60, +120 min)

Status: implemented 2026-09-25 (Phase 3 task "Define +30/+60/+120 labels"). Code:
`src/floodguard/analysis/labels.py`; CLI `scripts/define_labels.py`; tests
`tests/test_label_definition.py` (synthetic offline data).

## 1. Prediction Horizons and Operational Target Design

The system requires flood risk forecasts at multiple lead times:
- **+30 minutes** ($h = 30\text{ min}$)
- **+60 minutes** ($h = 60\text{ min}$)
- **+120 minutes** ($h = 120\text{ min}$)

For each usable observation at prediction origin $t$, future targets are evaluated at $t + h$:

1. **Proxy Threshold Exceedance** (Binary Classification):
   $$Y_{\text{exceed}}(t, h, \theta) = \mathbb{I}[WL(t + h) \ge \theta]$$
   where $\theta \in \{\text{Waspada}, \text{Amaran}, \text{Bahaya}\}$.
2. **Proxy Threshold Escalation / Onset** (Binary Classification):
   $$Y_{\text{escalate}}(t, h, \theta) = \mathbb{I}[WL(t) < \theta \land WL(t + h) \ge \theta]$$
   Captures transitions into flood risk within the horizon window.
3. **Future Water Level / Delta** (Regression):
   $$\Delta WL(t, h) = WL(t + h) - WL(t)$$
   $$\text{Rate}(t, h) = \frac{\Delta WL(t, h)}{h / 60}\text{ (m/h)}$$

## 2. Temporal Safety and Leakage Protections

- **Separation of Target and Feature Space**: A feature vector at origin $t$ may only contain observations $t' \le t$. Future observations $t + h$ belong strictly to the target artifact.
- **No Target Imputation**: If the future observation $t + h$ is missing, not usable, or falls beyond the end of the capture batch, the target status is recorded as `MISSING_FUTURE_TARGET`. It is **never** forward-filled or assumed to be non-flood (0).
- **Provisional Status**: Because thresholds are captured from current JPS metadata without historical versioning, all labels carry `CURRENT_THRESHOLD_REFERENCE_ONLY` and serve as operational proxies rather than confirmed flood ground truth.

## 3. Label Feasibility on Available History

| Feasibility Check | Criteria | Status on Local Captures |
|---|---|---|
| `label_construction_verification` | Multi-horizon execution logic verified | `SUFFICIENT` |
| `evaluable_origins_sufficiency` | $\ge 1$ station with $\ge 30$ usable origin points | `SUFFICIENT` |
| `positive_label_feasibility` | $\ge 10$ positive examples per horizon/threshold | `INSUFFICIENT` (sparse/zero positives) |
| `ground_truth_validity` | Official historical ground-truth flood catalogue | `INSUFFICIENT` (proxy reference only) |

## 4. Machine-Readable Schema and Output

Output path: `data/analysis/labels/<dataset_version>/labels.json` (`labels/v1`).
