"""Direct lag-builder regression tests (final-audit N1).

The M1 defect class (lag off-by-one) must be pinned at the builder level:
exact past levels, incomplete-set drops, origin/future exclusion.
"""

from __future__ import annotations

import pytest

from floodguard.forecasting.gradient_boosting import build_lag_delta_matrix
from floodguard.forecasting.statistical import StatisticalConfig, build_lag_matrix

pytestmark = pytest.mark.usefixtures("no_network")

CFG = StatisticalConfig()
OFFSETS = CFG.lag_offsets_minutes


def _history(base_minutes: int = 0, step: int = 5, n: int = 60) -> dict[str, float]:
    from datetime import UTC, datetime, timedelta

    t0 = datetime(2030, 1, 1, tzinfo=UTC) + timedelta(minutes=base_minutes)
    return {(t0 + timedelta(minutes=step * i)).isoformat(): 100.0 + i for i in range(n)}


def _origin(minutes: int) -> str:
    from datetime import UTC, datetime, timedelta

    return (datetime(2030, 1, 1, tzinfo=UTC) + timedelta(minutes=minutes)).isoformat()


def test_builders_return_exact_past_levels() -> None:
    history = _history()
    origin = _origin(300)  # index 60 in a 5-min grid starting at 0
    matrix, kept = build_lag_matrix(history, [origin], CFG)
    assert kept == [origin]
    # Origin-exclusive: lag_5 = value 5 min before origin, never the origin value.
    assert matrix[0][0] == history[_origin(295)]
    assert matrix[0] == [history[_origin(300 - lag)] for lag in OFFSETS]


def test_builders_drop_incomplete_lag_sets() -> None:
    history = _history()
    early = _origin(30)  # t-120 missing from history starting at 0
    matrix, kept = build_lag_matrix(history, [early], CFG)
    assert matrix == []
    assert kept == []
    matrix_d, kept_d = build_lag_delta_matrix(history, [early], OFFSETS)
    assert matrix_d == []
    assert kept_d == []


def test_builders_exclude_origin_and_future_values() -> None:
    history = _history(n=80)
    origin = _origin(300)
    matrix, _ = build_lag_matrix(history, [origin], CFG)
    origin_value = history[origin]
    future_value = history[_origin(305)]
    assert origin_value not in matrix[0]
    assert future_value not in matrix[0]
    matrix_d, _ = build_lag_delta_matrix(history, [origin], OFFSETS)
    flat = [v for row in matrix_d for v in row]
    assert origin_value not in flat
    assert future_value not in flat


def test_lag_delta_feature_count_and_order() -> None:
    history = _history()
    origin = _origin(300)
    matrix, kept = build_lag_delta_matrix(history, [origin], OFFSETS)
    assert kept == [origin]
    assert len(matrix[0]) == 2 * len(OFFSETS) - 1
