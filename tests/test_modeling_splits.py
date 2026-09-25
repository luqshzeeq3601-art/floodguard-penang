"""Chronological splitting, horizon embargo, and walk-forward tests (Phase 5 tasks 5-6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from floodguard.modeling.splits import (
    SplitConfig,
    chronological_split,
    insufficient_split,
    walk_forward_folds,
)

pytestmark = pytest.mark.usefixtures("no_network")

START = datetime(2030, 1, 1, tzinfo=UTC)


def _row(i: int) -> dict[str, object]:
    return {"prediction_origin_utc": (START + timedelta(minutes=5 * i)).isoformat(), "v": i}


def test_chronological_order_train_lt_val_lt_test() -> None:
    rows = [_row(i) for i in range(60)]
    cfg = SplitConfig(
        train_end_utc=(START + timedelta(minutes=5 * 29)).isoformat(),
        validation_end_utc=(START + timedelta(minutes=5 * 44)).isoformat(),
    )
    split = chronological_split(rows, cfg)
    assert split.status == "OK"
    assert split.train.row_count + split.validation.row_count + split.test.row_count <= 60
    # Embargo purges origins whose +120m target reaches the next partition.
    assert split.train.purged_row_count > 0
    assert split.validation.purged_row_count > 0


def test_exact_boundary_inclusion_rules() -> None:
    # One interval before / exactly at / one interval after train_end.
    train_end = START + timedelta(minutes=60)
    val_end = START + timedelta(minutes=120)
    cfg = SplitConfig(train_end_utc=train_end.isoformat(), validation_end_utc=val_end.isoformat())
    before = {"prediction_origin_utc": (train_end - timedelta(minutes=5)).isoformat()}
    exact = {"prediction_origin_utc": train_end.isoformat()}
    after = {"prediction_origin_utc": (train_end + timedelta(minutes=5)).isoformat()}
    # With a zero embargo the boundary rule is exact.
    cfg_zero = SplitConfig(
        train_end_utc=train_end.isoformat(),
        validation_end_utc=val_end.isoformat(),
        purge_embargo_minutes=0,
    )
    split = chronological_split([before, exact, after], cfg_zero)
    assert split.train.row_count == 2  # before + exactly at train_end
    assert split.validation.row_count == 1  # one interval after
    _ = cfg


def test_within_120_minutes_of_boundary_is_purged() -> None:
    train_end = START + timedelta(minutes=600)
    val_end = START + timedelta(minutes=1200)
    cfg = SplitConfig(train_end_utc=train_end.isoformat(), validation_end_utc=val_end.isoformat())
    # Origin 119 minutes after train_end cutoff region: inside embargo.
    origin = train_end - timedelta(minutes=119)
    split = chronological_split([{"prediction_origin_utc": origin.isoformat()}], cfg)
    assert split.train.row_count == 0
    assert split.train.purged_row_count == 1


def test_insufficient_event_support_structure() -> None:
    cfg = SplitConfig(
        train_end_utc=(START + timedelta(hours=1)).isoformat(),
        validation_end_utc=(START + timedelta(hours=2)).isoformat(),
    )
    split = insufficient_split(cfg, "zero positive episodes")
    assert split.status == "INSUFFICIENT_EVENT_SUPPORT"
    assert split.reason == "zero positive episodes"


def test_walk_forward_expanding_windows() -> None:
    rows = [_row(i) for i in range(100)]
    boundaries = [
        (START + timedelta(minutes=5 * 40)).isoformat(),
        (START + timedelta(minutes=5 * 70)).isoformat(),
    ]
    folds = walk_forward_folds(rows, boundaries)
    assert len(folds) == 2
    assert folds[1].train_rows >= folds[0].train_rows  # expanding window
    assert all(f.train_rows > 0 for f in folds)


def test_split_rejects_inverted_boundaries() -> None:
    with pytest.raises(ValueError, match="strictly after"):
        SplitConfig(
            train_end_utc=(START + timedelta(hours=2)).isoformat(),
            validation_end_utc=(START + timedelta(hours=1)).isoformat(),
        )
