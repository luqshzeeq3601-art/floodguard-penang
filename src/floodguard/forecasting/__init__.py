"""Phase 6 water-level forecasting for FloodGuard Penang.

Future water-level forecasting / sequence-model evaluation phase. Horizons
+30/+60/+120 minutes stay separate evaluation targets.

> **Data constraint (explicit).** Current local captures hold two
> water-level station-days (154 usable intervals) and no verified flood
> events. Tiny station windows cannot establish Penang-wide forecasting
> performance. Real results are ``LOCAL_REAL_DATA_DIAGNOSTIC`` at best.
>
> ```text
> NO PHASE 6 MODEL HAS BEEN VALIDATED AS A GENERALIZABLE PENANG WATER-LEVEL FORECASTER.
> ```

Evidence levels (shared with Phase 5):

- ``SYNTHETIC_SOFTWARE_VALIDATION``: synthetic-fixture software checks only.
- ``LOCAL_REAL_DATA_DIAGNOSTIC``: local-window diagnostics, not performance.
- ``REAL_PREDICTIVE_EVALUATION``: real predictive evaluation (not reached).
"""

from __future__ import annotations

from typing import Final

FORECASTING_SCHEMA_VERSION: Final[str] = "forecasting/v1"
HORIZONS_MINUTES: Final[tuple[int, ...]] = (30, 60, 120)
MAX_HORIZON_MINUTES: Final[int] = 120

# Sequence lookback choices are project configuration (not hydrological law).
LOOKBACK_CHOICES_MINUTES: Final[tuple[int, ...]] = (60, 120, 180)
DEFAULT_LOOKBACK_MINUTES: Final[int] = 120
CADENCE_MINUTES: Final[int] = 5
MAX_GAP_MINUTES: Final[float] = 5.0

EVIDENCE_SYNTHETIC: Final[str] = "SYNTHETIC_SOFTWARE_VALIDATION"
EVIDENCE_LOCAL_DIAGNOSTIC: Final[str] = "LOCAL_REAL_DATA_DIAGNOSTIC"
EVIDENCE_REAL: Final[str] = "REAL_PREDICTIVE_EVALUATION"

NOT_EVALUABLE: Final[str] = "NOT_EVALUABLE"
NO_ELIGIBLE_FORECAST_MODEL: Final[str] = "NO_ELIGIBLE_FORECAST_MODEL"
NOT_JUSTIFIED: Final[str] = "NOT_JUSTIFIED"
MISSING_TARGET: Final[str] = "MISSING_TARGET"
TARGET_AVAILABLE: Final[str] = "TARGET_AVAILABLE"
SYNTHETIC_SOURCE: Final[str] = "SYNTHETIC_TEST_ONLY"
