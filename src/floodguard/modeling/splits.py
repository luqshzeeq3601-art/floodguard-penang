"""Chronological train/validation/test splitting with horizon-aware boundary safety.

Design: docs/PHASE5_MODELING.md section on temporal splitting.

Rules:
- Never random-shuffle time-series observations.
- Exact timestamps order all partitions: train < validation < test.
- Maximum target horizon (+120 min) is protected by a purge/embargo: a training
  origin whose +120-minute target window reaches into the validation period is
  excluded from training (purged). The same rule applies at the
  validation/test boundary.
- Splits are centralized here; model modules must not reimplement split logic.
- When no positive-episode support exists, callers receive a structured
  ``INSUFFICIENT_EVENT_SUPPORT`` result instead of a valid-looking split.

Walk-forward folds use the same chronological + embargo semantics with an
expanding training window.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from floodguard.modeling import INSUFFICIENT_EVENT_SUPPORT, MAX_HORIZON_MINUTES

SPLITS_SCHEMA_VERSION: Final[str] = "splits/v1"


@dataclass(frozen=True)
class SplitConfig:
    """Configuration for chronological splitting."""

    train_end_utc: str
    validation_end_utc: str
    purge_embargo_minutes: int = MAX_HORIZON_MINUTES

    def __post_init__(self) -> None:
        train_end = datetime.fromisoformat(self.train_end_utc)
        val_end = datetime.fromisoformat(self.validation_end_utc)
        if not val_end > train_end:
            raise ValueError("validation_end_utc must be strictly after train_end_utc")
        if self.purge_embargo_minutes < 0:
            raise ValueError("purge_embargo_minutes must be >= 0")


@dataclass(frozen=True)
class PartitionResult:
    """One chronological partition with boundary accounting."""

    name: str
    row_count: int
    purged_row_count: int
    start_utc: str | None
    end_utc: str | None


@dataclass(frozen=True)
class ChronologicalSplit:
    """Result of a chronological three-way split."""

    status: str
    train: PartitionResult
    validation: PartitionResult
    test: PartitionResult
    config: SplitConfig
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "schema_version": SPLITS_SCHEMA_VERSION,
            "train": asdict(self.train),
            "validation": asdict(self.validation),
            "test": asdict(self.test),
            "config": asdict(self.config),
            "reason": self.reason,
        }


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _partition_summary(
    name: str, rows: list[dict[str, Any]], time_field: str, purged: int
) -> PartitionResult:
    if not rows:
        return PartitionResult(
            name=name, row_count=0, purged_row_count=purged, start_utc=None, end_utc=None
        )
    times = sorted(_parse_utc(str(r[time_field])) for r in rows)
    return PartitionResult(
        name=name,
        row_count=len(rows),
        purged_row_count=purged,
        start_utc=times[0].isoformat(),
        end_utc=times[-1].isoformat(),
    )


def partition_rows(
    rows: list[dict[str, Any]],
    config: SplitConfig,
    *,
    time_field: str = "prediction_origin_utc",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int, int]:
    """Partition row references with the embargo rule (single code path).

    Returns ``(train, validation, test, purged_train, purged_val)`` holding
    references to the input rows in input order. All callers (including
    scripts) must use this instead of reimplementing the rule, so reported
    split counts always describe the trained partitions (review Phase 6 M2).
    """
    train_end = _parse_utc(config.train_end_utc)
    val_end = _parse_utc(config.validation_end_utc)
    embargo = timedelta(minutes=config.purge_embargo_minutes)

    train_cutoff = train_end - embargo
    val_cutoff = val_end - embargo

    train_rows: list[dict[str, Any]] = []
    val_rows: list[dict[str, Any]] = []
    test_rows: list[dict[str, Any]] = []
    purged_train = 0
    purged_val = 0

    for row in rows:
        origin = _parse_utc(str(row[time_field]))
        if origin <= train_end:
            if origin <= train_cutoff:
                train_rows.append(row)
            else:
                # Origin in (train_end - embargo, train_end]: target window
                # reaches into validation; purge from training.
                purged_train += 1
        elif origin <= val_end:
            if origin <= val_cutoff:
                val_rows.append(row)
            else:
                purged_val += 1
        else:
            test_rows.append(row)
    return train_rows, val_rows, test_rows, purged_train, purged_val


def chronological_split(
    rows: list[dict[str, Any]],
    config: SplitConfig,
    *,
    time_field: str = "prediction_origin_utc",
) -> ChronologicalSplit:
    """Split rows chronologically with horizon-aware purge/embargo.

    Inclusion rules (documented, tested at exact boundaries):
    - train: origin <= train_end - embargo (purged origins excluded).
    - validation: train_end < origin <= validation_end - embargo for val rows
      whose target must not reach into test; validation origins with targets
      reaching into test are purged from validation scoring, not moved.
    - test: origin > validation_end.
    - Origins exactly at a boundary belong to the earlier side's rule as
      stated above; origins within 120 minutes after a boundary are excluded
      from the earlier partition by the embargo.
    """
    train_rows, val_rows, test_rows, purged_train, purged_val = partition_rows(
        rows, config, time_field=time_field
    )

    # Chronological ordering guard (no later observation in earlier partition).
    for earlier, later in ((train_rows, val_rows), (val_rows, test_rows)):
        if earlier and later:
            latest_earlier = max(_parse_utc(str(r[time_field])) for r in earlier)
            earliest_later = min(_parse_utc(str(r[time_field])) for r in later)
            if not latest_earlier < earliest_later:
                # Overlap can only happen if embargo is zero and duplicate
                # timestamps straddle the boundary; keep partitions but the
                # invariant below documents ordering. Raise to fail loudly.
                raise ValueError(
                    "chronological split invariant violated: "
                    f"{latest_earlier.isoformat()} !< {earliest_later.isoformat()}"
                )

    return ChronologicalSplit(
        status="OK",
        train=_partition_summary("train", train_rows, time_field, purged_train),
        validation=_partition_summary("validation", val_rows, time_field, purged_val),
        test=_partition_summary("test", test_rows, time_field, 0),
        config=config,
        reason=None,
    )


def insufficient_split(config: SplitConfig, reason: str) -> ChronologicalSplit:
    """Structured infeasibility result when event support is insufficient."""
    empty = PartitionResult(name="", row_count=0, purged_row_count=0, start_utc=None, end_utc=None)
    return ChronologicalSplit(
        status=INSUFFICIENT_EVENT_SUPPORT,
        train=PartitionResult(
            name="train",
            row_count=empty.row_count,
            purged_row_count=0,
            start_utc=None,
            end_utc=None,
        ),
        validation=PartitionResult(
            name="validation",
            row_count=0,
            purged_row_count=0,
            start_utc=None,
            end_utc=None,
        ),
        test=PartitionResult(
            name="test", row_count=0, purged_row_count=0, start_utc=None, end_utc=None
        ),
        config=config,
        reason=reason,
    )


@dataclass(frozen=True)
class WalkForwardFold:
    """One expanding-window walk-forward fold."""

    fold_index: int
    train_start_utc: str | None
    train_end_utc: str | None
    validation_start_utc: str | None
    validation_end_utc: str | None
    train_rows: int
    validation_rows: int
    purged_train_rows: int


def walk_forward_folds(
    rows: list[dict[str, Any]],
    validation_boundaries_utc: list[str],
    *,
    time_field: str = "prediction_origin_utc",
    embargo_minutes: int = MAX_HORIZON_MINUTES,
) -> list[WalkForwardFold]:
    """Build expanding-window walk-forward folds with embargo purge.

    Each fold trains on all origins <= boundary - embargo and validates on
    the most recent non-purged window: (previous_boundary, boundary - embargo]
    (all origins <= boundary - embargo for the first fold). Origins in
    (boundary - embargo, boundary] are embargo-purged from both training and
    validation because their +120-minute targets would reach past the fold
    boundary (review M2).
    """
    if not validation_boundaries_utc:
        raise ValueError("validation_boundaries_utc must be non-empty")
    boundaries = sorted(_parse_utc(b) for b in validation_boundaries_utc)
    ordered = sorted(rows, key=lambda r: _parse_utc(str(r[time_field])))
    embargo = timedelta(minutes=embargo_minutes)

    folds: list[WalkForwardFold] = []
    prev_boundary: datetime | None = None
    for i, boundary in enumerate(boundaries):
        train_cutoff = boundary - embargo
        train_rows = [r for r in ordered if _parse_utc(str(r[time_field])) <= train_cutoff]
        purged = sum(
            1
            for r in ordered
            if train_cutoff < _parse_utc(str(r[time_field])) <= boundary
            and (prev_boundary is None or _parse_utc(str(r[time_field])) > prev_boundary)
        )
        if prev_boundary is None:
            val_rows = [r for r in ordered if _parse_utc(str(r[time_field])) <= train_cutoff]
            # Validation window for the first fold starts at the first origin;
            # the embargo zone (train_cutoff, boundary] is purged, never validated.
            val_start = (
                min(_parse_utc(str(r[time_field])) for r in ordered).isoformat()
                if ordered
                else None
            )
        else:
            val_rows = [
                r for r in ordered if prev_boundary < _parse_utc(str(r[time_field])) <= train_cutoff
            ]
            val_start = prev_boundary.isoformat()
        train_times = [_parse_utc(str(r[time_field])) for r in train_rows]
        folds.append(
            WalkForwardFold(
                fold_index=i,
                train_start_utc=min(train_times).isoformat() if train_times else None,
                train_end_utc=max(train_times).isoformat() if train_times else None,
                validation_start_utc=val_start,
                validation_end_utc=boundary.isoformat(),
                train_rows=len(train_rows),
                validation_rows=len(val_rows),
                purged_train_rows=purged,
            )
        )
        prev_boundary = boundary
    return folds
