"""Phase 9 Streamlit dashboard: internal ML/analytics interface.

Thin UI over the Phase 8 FastAPI contracts. All business logic lives in the
backend (`repositories`, `api`) and in the pure view-model layer here
(`client`, `formatting`, `viewmodels`) — Streamlit pages render only.

Honesty rules (enforced in code, not just docs):

- `NO_ELIGIBLE_MODEL` / `NO_ELIGIBLE_FORECAST_MODEL` are displayed as-is,
  never converted into predictions or probabilities.
- Synthetic/test data is labeled synthetic everywhere it appears.
- Missing observations break charts (NaN gaps); zeros stay zeros.
- Thresholds show Waspada/Amaran/Bahaya only, as
  `CURRENT_THRESHOLD_REFERENCE_ONLY`; NORMAL is never a flood target.
- No live alerts, production predictions, or flood-risk probabilities exist.
"""

from __future__ import annotations

from typing import Final

DASHBOARD_SCHEMA_VERSION: Final[str] = "dashboard/v1"
LOCAL_TIMEZONE: Final[str] = "Asia/Kuala_Lumpur"

EVIDENCE_SYNTHETIC: Final[str] = "SYNTHETIC_SOFTWARE_VALIDATION"
EVIDENCE_LOCAL_DIAGNOSTIC: Final[str] = "LOCAL_REAL_DATA_DIAGNOSTIC"
EVIDENCE_REAL: Final[str] = "REAL_PREDICTIVE_EVALUATION"

NO_MODEL: Final[str] = "NO_ELIGIBLE_MODEL"
NO_FORECAST_MODEL: Final[str] = "NO_ELIGIBLE_FORECAST_MODEL"

DEFAULT_TIMEOUT_SECONDS: Final[float] = 10.0
CACHE_TTL_SECONDS: Final[int] = 300
