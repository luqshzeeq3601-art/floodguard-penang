"""Live poll orchestration: fetch -> raw -> normalize/validate -> DB (Phase 10, Task 1).

Reuses Phase 1/2 adapters, canonical IDs, quality/database contracts::

    permission gate -> HTTP fetch -> raw immutable storage
    -> parse / normalize / validate -> idempotent repository write
    -> run history + metrics

Rainfall and water-level semantics stay separated; excluded fields are never
promoted (via ``validation.observations``). Unknown source IDs are quarantined
by the mapper, never added to the station master. Timestamps preserve raw text,
normalized time, retrieval time and timezone evidence; retrieval time is never
substituted for observation time (``UNSPECIFIED_ASSUMED``).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from floodguard.backend.models import Observation
from floodguard.backend.repositories import ConflictError, ObservationRepository, RepositoryError
from floodguard.ingestion import manifest, storage
from floodguard.ingestion.contracts import Adapter, BatchStatus
from floodguard.ingestion.fetch import FetchResult, PermissionNotGrantedError
from floodguard.ingestion.hashing import sha256_hex
from floodguard.ingestion.pipeline import ingest_batch
from floodguard.ingestion.station_mapping import SensorMapper
from floodguard.live.http import ControlledFetcher, HttpConfig
from floodguard.live.metrics import MetricsCollector
from floodguard.live.runs import RunRecord, RunStatus, RunStore, new_run_id, utc_now_iso
from floodguard.preprocessing import station_ids, timestamps, units
from floodguard.validation import observations, quality_flags

LOG = logging.getLogger("floodguard.live.runner")

ClockFn = Callable[[], float]
TransportFn = Callable[[str, float], FetchResult]


@dataclass(frozen=True)
class PollTarget:
    """One configured live source/dataset to poll."""

    adapter: Adapter
    url: str
    source_reference: str


@dataclass(frozen=True)
class PollOutcome:
    record: RunRecord
    canonical_inserted: int
    stage_seconds: dict[str, float]


def _error_category(exc: Exception) -> str:
    name = type(exc).__name__
    if isinstance(exc, PermissionNotGrantedError):
        return "PERMISSION"
    if isinstance(exc, ConflictError):
        return "CONFLICT"
    if isinstance(exc, RepositoryError):
        return "DB_FAILURE"
    if "Timeout" in name or "timeout" in name.lower():
        return "TIMEOUT"
    if "HTTP" in name or "URLError" in name or "Connection" in name:
        return "NETWORK"
    if "Schema" in name or "Payload" in name:
        return "SCHEMA"
    return f"OTHER:{name}"


def _parse_utc(text: str | None) -> datetime | None:
    if not text:
        return None
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _require_utc(value: Any) -> datetime:
    moment = _parse_utc(value if isinstance(value, str) else None)
    assert moment is not None, "canonical row lacks observation_time_utc"
    return moment


def _quantize_4dp(value: Any) -> Decimal | None:
    """Match Numeric(12,4) storage scale so identical replays compare equal.

    Repository idempotency compares Decimal via ``str``; ``Decimal('2.0')``
    and ``Decimal('2.0000')`` would falsely conflict. Quantizing to the
    column scale keeps the replay signature stable (JPS precision is coarser).
    """
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.0000"))


def _to_orm(
    row: Mapping[str, Any], *, raw_time_by_key: Mapping[tuple[str, ...], str | None]
) -> Observation:
    key = (
        str(row["source"]),
        str(row["fg_sensor_id"]),
        str(row["measurement_type"]),
        str(row["observation_time_utc"]),
    )
    raw_text = raw_time_by_key.get(key)
    value = row.get("value")
    local_raw = row.get("observation_time_local")
    first_raw = row.get("first_retrieved_at")
    value_raw = row.get("value_raw")
    return Observation(
        source=str(row["source"]),
        fg_sensor_id=str(row["fg_sensor_id"]),
        measurement_type=str(row["measurement_type"]),
        observation_time_utc=_require_utc(row.get("observation_time_utc")),
        observation_time_raw=raw_text,
        observation_time_local=_parse_utc(local_raw if isinstance(local_raw, str) else None),
        timezone_status=str(row.get("timezone_status") or "UNSPECIFIED_ASSUMED"),
        first_retrieved_at=_parse_utc(first_raw if isinstance(first_raw, str) else None),
        value=_quantize_4dp(value),
        value_raw=str(value_raw) if value_raw is not None else None,
        unit=str(row["unit"]),
        usable=bool(row.get("usable")),
        quality_flags=list(row.get("quality_flags") or []),
        duplicate_status=str(row.get("duplicate_status") or "UNIQUE"),
        provenance=list(row.get("provenance") or []),
        datasets=list(row.get("datasets") or []),
        schema_version=str(row.get("observation_schema_version") or "observations/v1"),
    )


def _normalize_records(
    raw_records: Sequence[Mapping[str, Any]],
    *,
    mapper: SensorMapper | None,
    quarantined: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run the existing validation chain; returns (canonical_rows, quality_rows)."""
    records = list(raw_records)
    ts_rows = [] if quarantined else [timestamps.normalize_record(r) for r in records]
    sid_rows = (
        [station_ids.normalize_record(r, mapper) for r in records]
        if mapper is not None and any(r.get("source") in mapper.sources for r in records)
        else []
    )
    # Forecasts have no station master: station layer stays empty (quality flags NO_STATION_SENSOR).
    if mapper is None:
        sid_rows = []
    unit_rows = [u for r in records for u in units.validate_record(r)]
    q_rows = quality_flags.flag_batch(
        records,
        quarantined=quarantined,
        timestamp_rows=ts_rows,
        station_rows=sid_rows,
        unit_rows=unit_rows,
    )
    canonical, _excluded = observations.build_observations(q_rows)
    return canonical, q_rows


class LivePollRunner:
    """One-shot live poller (scheduler calls this via ``run_once_fn``)."""

    def __init__(
        self,
        *,
        targets: Sequence[PollTarget],
        fetcher_by_source: Mapping[str, ControlledFetcher],
        raw_root: Path,
        mapper: SensorMapper | None,
        session_factory: Callable[[], Session] | None,
        run_store: RunStore | None,
        metrics: MetricsCollector | None = None,
        clock: ClockFn | None = None,
    ) -> None:
        self._targets = list(targets)
        self._fetchers = dict(fetcher_by_source)
        self._raw_root = raw_root
        self._mapper = mapper
        self._sessions = session_factory
        self._runs = run_store
        self._metrics = metrics or MetricsCollector()
        self._clock = clock or time.perf_counter

    @property
    def metrics(self) -> MetricsCollector:
        return self._metrics

    def _write_db(
        self,
        canonical: Sequence[Mapping[str, Any]],
        quality: Sequence[Mapping[str, Any]],
    ) -> dict[str, int]:
        if self._sessions is None:
            return {"inserted": 0, "duplicate_identical": 0}
        raw_time: dict[tuple[str, ...], str | None] = {}
        for q in quality:
            k = (
                str(q.get("source")),
                str(q.get("fg_sensor_id")),
                str(q.get("measurement_type")),
                str(q.get("observation_time_utc")),
            )
            raw_time.setdefault(k, q.get("observation_time_raw"))
        session = self._sessions()
        try:
            repo = ObservationRepository(session)
            rows = [_to_orm(r, raw_time_by_key=raw_time) for r in canonical]
            counts = repo.insert_many(rows)
            session.commit()
            return counts
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _load_prior_raw(
        self, prior: Mapping[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        accepted: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        for key, bucket in (("records_path", accepted), ("quarantine_path", quarantined)):
            rel = str(prior.get(key) or "")
            if not rel:
                continue
            data = storage.fs_path(self._raw_root / rel).read_bytes()
            for line in data.decode("utf-8").splitlines():
                if line.strip():
                    bucket.append(json.loads(line))
        return accepted, quarantined

    def poll_target(
        self,
        target: PollTarget,
        *,
        transport: TransportFn | None = None,
        retrieved_at: datetime | None = None,
    ) -> PollOutcome:
        run_id = new_run_id()
        started = utc_now_iso()
        t0 = self._clock()
        stages: dict[str, float] = {}
        fetcher = self._fetchers.get(target.adapter.source)
        if fetcher is None:
            raise ValueError(f"no fetcher for source {target.adapter.source!r}")

        def close(
            status: RunStatus,
            *,
            fetched: int = 0,
            accepted: int = 0,
            quarantined: int = 0,
            duplicates: int = 0,
            error: str | None = None,
            payload_sha: str | None = None,
            batch_id: str | None = None,
            canonical_inserted: int = 0,
        ) -> PollOutcome:
            ended = utc_now_iso()
            duration = self._clock() - t0
            record = RunRecord(
                run_id=run_id,
                source=target.adapter.source,
                dataset=target.adapter.dataset,
                started_at=started,
                ended_at=ended,
                status=status,
                records_fetched=fetched,
                records_accepted=accepted,
                quarantined_count=quarantined,
                duplicate_count=duplicates,
                error_category=error,
                payload_sha256=payload_sha,
                batch_id=batch_id,
                duration_seconds=duration,
            )
            if self._runs is not None:
                self._runs.append(record)
            self._metrics.record_run(
                record, canonical_inserted=canonical_inserted, stage_seconds=stages
            )
            LOG.info(
                "live poll",
                extra={
                    "run_id": run_id,
                    "source": target.adapter.source,
                    "dataset": target.adapter.dataset,
                    "status": str(status),
                    "error_category": error,
                },
            )
            return PollOutcome(record, canonical_inserted, dict(stages))

        # HTTP fetch (permission gate inside the fetcher runs before any socket).
        t_fetch = self._clock()
        try:
            fetched = fetcher.fetch(target.url, transport=transport)
        except PermissionNotGrantedError as exc:
            stages["fetch"] = self._clock() - t_fetch
            return close(RunStatus.BLOCKED_PERMISSION, error=_error_category(exc))
        except Exception as exc:
            stages["fetch"] = self._clock() - t_fetch
            return close(RunStatus.FAILED, error=_error_category(exc))
        stages["fetch"] = self._clock() - t_fetch
        payload: bytes = fetched.body
        retrieval = retrieved_at or fetched.retrieved_at
        payload_sha = sha256_hex(payload)

        # Raw immutable storage (idempotent; DUPLICATE re-ensures the DB).
        t_raw = self._clock()
        try:
            report = ingest_batch(
                payload,
                target.adapter,
                source_reference=target.source_reference,
                retrieved_at=retrieval,
                raw_root=self._raw_root,
                mapper=self._mapper,
            )
        except Exception as exc:
            stages["raw_store"] = self._clock() - t_raw
            return close(RunStatus.FAILED, error=_error_category(exc), payload_sha=payload_sha)
        stages["raw_store"] = self._clock() - t_raw

        if report.status is BatchStatus.FAILED:
            return close(
                RunStatus.FAILED,
                fetched=report.input_rows,
                accepted=report.accepted_rows,
                quarantined=report.quarantined_rows,
                error=(report.error_reason or "RAW_FAILED")[:200],
                payload_sha=payload_sha,
            )

        is_duplicate = report.status is BatchStatus.DUPLICATE
        # Normalize + validate (existing contracts; forecasts yield zero canonical rows).
        t_norm = self._clock()
        try:
            if is_duplicate:
                prior = manifest.find_succeeded(
                    self._raw_root,
                    target.adapter.source,
                    target.adapter.dataset,
                    target.adapter.partition,
                    payload_sha,
                )
                if prior is None:
                    return close(
                        RunStatus.FAILED,
                        error="MANIFEST_MISSING_PRIOR",
                        payload_sha=payload_sha,
                    )
                accepted_raw, quarantined_raw = self._load_prior_raw(prior)
                canonical_a, quality_a = _normalize_records(
                    accepted_raw, mapper=self._mapper, quarantined=False
                )
                canonical_q, quality_q = _normalize_records(
                    quarantined_raw, mapper=self._mapper, quarantined=True
                )
                canonical = canonical_a + canonical_q
                quality = quality_a + quality_q
                prior_batch = prior.get("batch_id")
                batch_id: str | None = (
                    str(prior_batch) if prior_batch is not None else report.batch_id
                )
            else:
                # Read back the just-written artifacts so normalization sees stored bytes.
                paths = list(report.artifact_paths)
                rel_records = str(paths[1]) if len(paths) > 1 else ""
                rel_quar = str(paths[2]) if len(paths) > 2 else ""
                accepted_raw = self._read_jsonl(rel_records)
                quarantined_raw = self._read_jsonl(rel_quar)
                canonical_a, quality_a = _normalize_records(
                    accepted_raw, mapper=self._mapper, quarantined=False
                )
                canonical_q, quality_q = _normalize_records(
                    quarantined_raw, mapper=self._mapper, quarantined=True
                )
                canonical = canonical_a + canonical_q
                quality = quality_a + quality_q
                batch_id = report.batch_id
        except Exception as exc:
            stages["normalize"] = self._clock() - t_norm
            return close(
                RunStatus.FAILED,
                fetched=report.input_rows,
                accepted=report.accepted_rows,
                quarantined=report.quarantined_rows,
                error=_error_category(exc),
                payload_sha=payload_sha,
                batch_id=report.batch_id,
            )
        stages["normalize"] = self._clock() - t_norm

        # Idempotent DB write (transactional; conflicts fail loudly).
        t_db = self._clock()
        try:
            counts = self._write_db(canonical, quality)
        except Exception as exc:
            stages["db_write"] = self._clock() - t_db
            return close(
                RunStatus.FAILED,
                fetched=report.input_rows,
                accepted=report.accepted_rows,
                quarantined=report.quarantined_rows,
                duplicates=1 if is_duplicate else 0,
                error=_error_category(exc),
                payload_sha=payload_sha,
                batch_id=batch_id,
            )
        stages["db_write"] = self._clock() - t_db
        inserted = int(counts.get("inserted", 0))
        dup_identical = int(counts.get("duplicate_identical", 0))
        status = RunStatus.DUPLICATE if (is_duplicate and inserted == 0) else RunStatus.SUCCEEDED
        return close(
            status,
            fetched=report.input_rows,
            accepted=report.accepted_rows,
            quarantined=report.quarantined_rows,
            duplicates=(dup_identical + (1 if is_duplicate else 0)),
            payload_sha=payload_sha,
            batch_id=batch_id,
            canonical_inserted=inserted,
        )

    def _read_jsonl(self, relpath: str) -> list[dict[str, Any]]:
        # artifact_paths are stored as "<dataset>/.../<sha>.<ext>" relative to raw root.
        if not relpath:
            return []
        # ingest_batch reports paths as str(PurePosixPath); resolve under raw root.
        candidate = Path(relpath)
        if not candidate.is_absolute():
            # artifact_paths entries are already relative dataset paths.
            full = storage.fs_path(self._raw_root.joinpath(*candidate.parts))
        else:
            full = candidate
        if not full.exists():
            return []
        out = []
        for line in full.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out

    def run_all(
        self,
        *,
        transport: TransportFn | None = None,
    ) -> list[RunRecord]:
        """Poll every configured target; one failure never corrupts the rest."""
        records: list[RunRecord] = []
        for target in self._targets:
            try:
                outcome = self.poll_target(target, transport=transport)
            except Exception as exc:
                ended = utc_now_iso()
                record = RunRecord(
                    run_id=new_run_id(),
                    source=target.adapter.source,
                    dataset=target.adapter.dataset,
                    started_at=ended,
                    ended_at=ended,
                    status=RunStatus.FAILED,
                    error_category=_error_category(exc),
                    duration_seconds=0.0,
                )
                if self._runs is not None:
                    self._runs.append(record)
                self._metrics.record_run(record)
                records.append(record)
                continue
            records.append(outcome.record)
        return records


def build_targets(
    *,
    rainfall_adapter: Adapter | None = None,
    water_level_adapter: Adapter | None = None,
    rainfall_url: str | None = None,
    water_level_url: str | None = None,
) -> list[PollTarget]:
    """Live listing targets (listings only; history backfill stays explicit)."""
    from floodguard.ingestion.adapters.jps import RAINFALL_LISTING, WATER_LEVEL_LISTING
    from floodguard.live.http import JPS_RAINFALL_LISTING_URL, JPS_WATER_LEVEL_LISTING_URL

    rf = rainfall_adapter or RAINFALL_LISTING
    wl = water_level_adapter or WATER_LEVEL_LISTING
    rf_url = rainfall_url or JPS_RAINFALL_LISTING_URL
    wl_url = water_level_url or JPS_WATER_LEVEL_LISTING_URL
    return [
        PollTarget(rf, rf_url, rf_url),
        PollTarget(wl, wl_url, wl_url),
    ]


def http_config_from_live(timeout_seconds: float, max_retries: int) -> HttpConfig:
    return HttpConfig(timeout_seconds=timeout_seconds, max_retries=max_retries)
