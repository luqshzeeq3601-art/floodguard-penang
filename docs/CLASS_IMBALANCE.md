# Class Imbalance and Event-Count Viability Analysis

Status: implemented 2026-09-25 (Phase 3 task "Verify class imbalance"). Code:
`src/floodguard/analysis/class_imbalance.py`; CLI `scripts/verify_class_imbalance.py`; tests
`tests/test_class_imbalance.py` (synthetic offline data).

## 1. Class Imbalance and Event Episode Metrics

In flood forecasting, class imbalance manifests at two distinct levels:
1. **Observation-Level Imbalance**: The proportion of individual 5-minute intervals exceeding threshold levels ($Waspada, Amaran, Bahaya$) relative to base river levels.
2. **Episode-Level Viability**: The number of independent contiguous flood episodes. A continuous flood event may produce dozens of consecutive positive rows, but represents only a single hydrological event. Models evaluated on row-level accuracy without independent episode separation risk massive data leakage and severe overfitting.

For each station, threshold, and horizon (+30, +60, +120 minutes):
- `positive_count`: Evaluable prediction origins where future outcome is positive.
- `negative_count`: Evaluable prediction origins where future outcome is negative.
- `positive_prevalence_percent`: $100 \times \frac{\text{positives}}{\text{evaluable}}$.
- `imbalance_ratio_negative_to_positive`: $\frac{\text{negatives}}{\text{positives}}$.
- `contiguous_exceedance_episodes`: Number of distinct continuous episodes.

## 2. Train / Validation / Test Splitting Feasibility

A valid chronological train/validation/test split for temporal flood early warning requires:
- $\ge 10$ distinct contiguous event episodes across the dataset.
- $\ge 30$ positive instances across the dataset.

Without multi-year continuous historical coverage, local captures provide insufficient positive examples.

| Feasibility Check | Criteria | Status on Local Captures |
|---|---|---|
| `imbalance_analysis_verification` | End-to-end execution of imbalance metrics | `SUFFICIENT` |
| `chronological_split_viability` | $\ge 10$ episodes and $\ge 30$ positive labels | `INSUFFICIENT` (history too sparse) |
| `extreme_class_imbalance_risk` | Non-zero positive events observed | `INSUFFICIENT` (0 positive events in captures) |

## 3. Machine-Readable Schema and Output

Output path: `data/analysis/class_imbalance/<dataset_version>/class_imbalance.json` (`class_imbalance/v1`).
