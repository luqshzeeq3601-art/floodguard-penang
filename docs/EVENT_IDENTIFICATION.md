# Provisional Flood and Threshold Event Identification

Status: implemented 2026-09-25 (Phase 3 task "Identify flood/threshold events"). Code:
`src/floodguard/analysis/events.py`; CLI `scripts/identify_events.py`; tests
`tests/test_event_identification.py` (synthetic offline data).

## 1. Core Principles and Ground-Truth Distinction

This module establishes a strict conceptual separation among three terms:

1. **Observed Threshold Exceedance**: An individual usable canonical water-level observation ($usable = \text{true}$, unit $m$, no continuity-breaking flags) where $value \ge threshold\_value$.
2. **Contiguous Exceedance Episode**: A maximal sequence of consecutive threshold exceedance observations with valid cadence ($\Delta t \le 5.0\text{ min}$) without missing-data interruptions.
3. **Verified Historical Flood Event**: An official, dated record of ground-level flood inundation. **Count = 0 in the current dataset** because no official event-dated flood dataset overlapping JPS 2024+ history has been verified.

Thresholds are current JPS values captured from listing metadata (`CURRENT_THRESHOLD_REFERENCE_ONLY`). They are not versioned and are **not proven to have applied at historical observation timestamps** (`valid_at_observation_times: NOT_ESTABLISHED`). `NORMAL` thresholds are permanently excluded and never eligible for flood labeling.

## 2. Segmentation Algorithm and Termination Rules

For a selected water-level sensor and reference threshold (Waspada, Amaran, Bahaya):

- **Start**: The first usable observation where $value \ge threshold\_value$.
- **Continuity**: Subsequent usable observations where $value \ge threshold\_value$ and $\Delta t \le 5.0\text{ min}$.
- **Termination**:
  - `ENDED_BELOW_THRESHOLD`: A usable observation occurs with $value < threshold\_value$.
  - `INTERRUPTED_BY_MISSING_DATA`: A not-usable row (e.g. `-9999`, `ERROR`), missing slot, or time gap $> 5.0\text{ min}$ occurs. Missing periods are **never** bridged or forward-filled.
  - `WINDOW_EDGE`: The episode reaches the end of the observation window or capture batch without a closing observation.

## 3. Data Sufficiency Guards

| Analysis Guard | Criteria | Status on Local Captures |
|---|---|---|
| `implementation_verification` | End-to-end execution of segmentation algorithm | `SUFFICIENT` |
| `provisional_exceedance_detection` | $\ge 1$ station with $\ge 30$ usable rows and reference thresholds | `SUFFICIENT` |
| `episode_sample_statistics` | $\ge 1$ station with $\ge 5$ distinct episodes | `INSUFFICIENT` (sample too sparse) |
| `historical_flood_ground_truth` | Official overlapping flood event catalogue | `INSUFFICIENT` (no official dataset) |

## 4. Machine-Readable Schema and Output

Output path: `data/analysis/events/<dataset_version>/threshold_events.json` (`threshold_events/v1`).

The output records:
- Input dataset version, observation SHA-256, station master hash, threshold reference hash.
- Strict definitions and configuration parameters.
- Station-by-station evaluations for each reference threshold:
  - Usable observation count, exceedance observation count, exceedance percentage.
  - Number of contiguous episodes.
  - Breakdown by termination reason.
  - Episode array with `episode_id`, timestamps (UTC/local), observation count, duration in minutes, peak water level, max exceedance, termination reason, and `CURRENT_THRESHOLD_REFERENCE_ONLY` validity flag.
- Verified historical flood events ($= 0$).
