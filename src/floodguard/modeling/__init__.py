"""Phase 5 baselines and ML modeling for FloodGuard Penang.

Software/methodology implementation for the nine Phase 5 TASKS.md tasks.
Real FloodGuard empirical flood-classification validation is NOT possible
with the current local captures (zero positive flood-proxy events); see
``docs/PHASE5_COMPLETION.md`` and the feasibility gate in
``floodguard.modeling.feasibility``.

Evidence levels used by every evaluation result:

- ``SYNTHETIC_SOFTWARE_VALIDATION``: synthetic-fixture software checks only.
- ``LOCAL_REAL_DATA_DIAGNOSTIC``: local-window diagnostics, not model performance.
- ``REAL_PREDICTIVE_EVALUATION``: real predictive evaluation (not reached in Phase 5).
"""

from __future__ import annotations

from typing import Final

MODELING_SCHEMA_VERSION: Final[str] = "modeling/v1"
HORIZONS_MINUTES: Final[tuple[int, ...]] = (30, 60, 120)
MAX_HORIZON_MINUTES: Final[int] = 120

EVIDENCE_SYNTHETIC: Final[str] = "SYNTHETIC_SOFTWARE_VALIDATION"
EVIDENCE_LOCAL_DIAGNOSTIC: Final[str] = "LOCAL_REAL_DATA_DIAGNOSTIC"
EVIDENCE_REAL: Final[str] = "REAL_PREDICTIVE_EVALUATION"

NOT_EVALUABLE: Final[str] = "NOT_EVALUABLE"
INSUFFICIENT_EVENT_SUPPORT: Final[str] = "INSUFFICIENT_EVENT_SUPPORT"
NO_ELIGIBLE_MODEL: Final[str] = "NO_ELIGIBLE_MODEL"
MISSING_FUTURE_TARGET: Final[str] = "MISSING_FUTURE_TARGET"
TARGET_EVALUATED: Final[str] = "TARGET_EVALUATED"

SYNTHETIC_SOURCE: Final[str] = "SYNTHETIC_TEST_ONLY"
