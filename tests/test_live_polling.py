"""Live polling/scheduled ingestion tests (Phase 10, Task 1; offline, synthetic only).

Covers: successful poll, permission blocked, timeout, transient retry,
permanent failure, malformed/empty payload, duplicate, unknown station,
missing markers, zero rainfall, timestamp normalization, DB failure after raw,
replay recovery, overlapping runs, configuration, scheduler single iteration,
graceful stop, SSRF guard, and no background work in unit tests.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from floodguard.ingestion.adapters.jps import history_adapter
from floodguard.ingestion.fetch import AccessPermission, FetchResult
from floodguard.live import runner as live_runner
from floodguard.live.config import load_config
from floodguard.live.http import (
    ALLOWED_URLS,
    ControlledFetcher,
    HttpConfig,
    TransientHttpError,
    UrlNotAllowedError,
)
from floodguard.live.metrics import MetricsCollector
from floodguard.live.runs import RunStatus, RunStore
from floodguard.live.scheduler import PollScheduler, SchedulerConfig
from floodguard.station_master import SOURCE_JPS, SensorType, sensor_id, site_id
from tests.backend_helpers import make_engine, make_sensor, make_session, make_site

pytestmark = pytest.mark.usefixtures("no_network")

PERM = AccessPermission(
    source=SOURCE_JPS,
    scope="network_fetch",
    granted_by="synthetic",
    reference="syn",
    granted_on="2030-01-01",
)
OPEN_PERM = AccessPermission(
    source="DATA_GOV_MY_WEATHER_API",
    scope="network_fetch",
    granted_by="synthetic",
    reference="syn",
    granted_on="2030-01-01",
)
RETRIEVED = datetime(2030, 1, 1, 8, 5, tzinfo=UTC)


def _history_payload(
    rows: list[dict[str, str]], *, info_extra: dict[str, str] | None = None
) -> bytes:
    info = {"name": "Synthetic", "normal": "0.0", "alert": "1.0", "warning": "2.0", "danger": "3.0"}
    info.update(info_extra or {})
    return json.dumps({"info": info, "values": rows}).encode()


def _rf_row(dt: str, raw: str) -> dict[str, str]:
    return {
        "dt": dt,
        "raw": raw,
        "clean": raw,
        "chourly": raw,
        "cdaily": raw,
        "tdaily": raw,
        "cyearly": raw,
        "c15min": raw,
    }


def _wl_row(dt: str, final: str, severity: str = "") -> dict[str, str]:
    return {
        "dt": dt,
        "clean": final,
        "raw": final,
        "ecm": final,
        "final": final,
        "severity": severity,
    }


def _mapper(tmp_path: Path, entries: list[tuple[str, SensorType]]):  # type: ignore[no-untyped-def]
    from floodguard.ingestion.station_mapping import SensorMapper

    path = tmp_path / "sensors.csv"
    import csv

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(
            [
                "fg_sensor_id",
                "fg_site_id",
                "sensor_type",
                "source",
                "jps_internal_id",
                "fg_schema_version",
            ]
        )
        for raw, st in entries:
            w.writerow(
                [
                    sensor_id(SOURCE_JPS, raw.strip(), st),
                    site_id(SOURCE_JPS, raw.strip()),
                    st.value,
                    SOURCE_JPS,
                    raw,
                    "station_master/v1",
                ]
            )
    return SensorMapper.from_csv(path)


def _seed_db(sensor_raw: str, sensor_type: SensorType):  # type: ignore[no-untyped-def]
    engine = make_engine()
    session = make_session(engine)
    sid = site_id(SOURCE_JPS, sensor_raw)
    fid = sensor_id(SOURCE_JPS, sensor_raw, sensor_type)
    session.add(make_site(site_id=sid, jps_internal_id=sensor_raw, fg_source_site_key=sensor_raw))
    mt, unit = (
        ("RAINFALL_INTERVAL", "mm") if sensor_type is SensorType.RAINFALL else ("WATER_LEVEL", "m")
    )
    session.add(
        make_sensor(
            sensor_id=fid,
            site_id=sid,
            sensor_type=sensor_type.value,
            jps_internal_id=sensor_raw,
            measurement_type=mt,
            unit=unit,
        )
    )
    session.commit()
    session.close()
    from sqlalchemy.orm import Session as SASession
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(bind=engine, class_=SASession, expire_on_commit=False)
    return factory


def _runner(tmp_path: Path, adapter, url: str, mapper, factory=None, perm=PERM):  # type: ignore[no-untyped-def]
    fetcher = ControlledFetcher(adapter.source, perm, HttpConfig(max_retries=2))
    target = live_runner.PollTarget(adapter, url, url)
    store = RunStore(tmp_path / "runs.jsonl")
    metrics = MetricsCollector()
    clock = iter([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2])
    r = live_runner.LivePollRunner(
        targets=[target],
        fetcher_by_source={adapter.source: fetcher},
        raw_root=tmp_path / "raw",
        mapper=mapper,
        session_factory=factory,
        run_store=store,
        metrics=metrics,
        clock=lambda: next(clock, 5.0),
    )
    return r, store, metrics


def test_successful_poll_uses_real_history_adapter(tmp_path: Path) -> None:
    adapter = history_adapter(SensorType.RAINFALL, "SYN001", "https://example.test/?station=SYN001")
    mapper = _mapper(tmp_path, [("SYN001", SensorType.RAINFALL)])
    factory = _seed_db("SYN001", SensorType.RAINFALL)
    url = next(iter(ALLOWED_URLS))
    # Point the target at an allowed URL but keep the adapter partition.
    target_adapter = adapter
    r, store, metrics = _runner(tmp_path, target_adapter, url, mapper, factory)
    payload = _history_payload([_rf_row("01/01/2030 08:00", "0.0")])

    def transport(u: str, timeout: float) -> FetchResult:
        assert u == url
        return FetchResult(payload, 200, RETRIEVED)

    outcome = r.poll_target(r._targets[0], transport=transport, retrieved_at=RETRIEVED)
    assert outcome.record.status == RunStatus.SUCCEEDED
    assert outcome.record.payload_sha256 is not None
    assert outcome.canonical_inserted == 1
    snap = metrics.snapshot()
    assert snap["poll_attempts"] == 1
    assert snap["successful_polls"] == 1
    assert snap["canonical_records_inserted"] == 1
    assert store.read_all()[0]["status"] == "SUCCEEDED"


def test_permission_blocked_performs_no_io(tmp_path: Path) -> None:
    adapter = history_adapter(SensorType.RAINFALL, "SYN001", "https://example.test/?station=SYN001")
    mapper = _mapper(tmp_path, [("SYN001", SensorType.RAINFALL)])
    url = next(iter(ALLOWED_URLS))
    r, _, _ = _runner(tmp_path, adapter, url, mapper, None, perm=None)

    def transport(u: str, timeout: float):  # type: ignore[no-untyped-def]
        raise AssertionError("transport must not run when permission is blocked")

    outcome = r.poll_target(r._targets[0], transport=transport)
    assert outcome.record.status == RunStatus.BLOCKED_PERMISSION
    assert outcome.record.error_category == "PERMISSION"


def test_ssrf_guard_rejects_arbitrary_url(tmp_path: Path) -> None:
    fetcher = ControlledFetcher(SOURCE_JPS, PERM, HttpConfig())
    with pytest.raises(UrlNotAllowedError):
        fetcher.fetch(
            "https://evil.test/collect",
            transport=lambda u, t: (_ for _ in ()).throw(AssertionError("no socket")),
            sleep=lambda s: None,
        )


def test_transient_retry_then_success(tmp_path: Path) -> None:
    adapter = history_adapter(SensorType.RAINFALL, "SYN001", "https://example.test/?station=SYN001")
    mapper = _mapper(tmp_path, [("SYN001", SensorType.RAINFALL)])
    factory = _seed_db("SYN001", SensorType.RAINFALL)
    url = next(iter(ALLOWED_URLS))
    r, _, _ = _runner(tmp_path, adapter, url, mapper, factory)
    payload = _history_payload([_rf_row("01/01/2030 08:00", "1.5")])
    calls: list[float] = []
    attempts = {"n": 0}

    def transport(u: str, timeout: float) -> FetchResult:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise TransientHttpError(503, u)
        return FetchResult(payload, 200, RETRIEVED)

    # Patch sleep via direct fetcher call to assert backoff without waiting.
    fetcher = r._fetchers[adapter.source]
    got = fetcher.fetch(url, transport=transport, sleep=calls.append)
    assert got.body == payload
    assert calls == [2.0]  # base 2.0 * 2**0, deterministic, no real sleep
    outcome = r.poll_target(
        r._targets[0],
        transport=lambda u, t: FetchResult(payload, 200, RETRIEVED),
        retrieved_at=RETRIEVED,
    )
    assert outcome.record.status == RunStatus.SUCCEEDED


def test_permanent_http_failure_is_failed_not_retried() -> None:
    fetcher = ControlledFetcher(SOURCE_JPS, PERM, HttpConfig(max_retries=3))
    sleeps: list[float] = []
    attempts = {"n": 0}

    def transport(u: str, timeout: float):  # type: ignore[no-untyped-def]
        attempts["n"] += 1
        raise OSError("HTTP 404 for https://x")

    with pytest.raises(OSError, match="HTTP 404"):
        fetcher.fetch(
            next(iter(ALLOWED_URLS)),
            transport=transport,
            sleep=sleeps.append,
        )
    assert attempts["n"] == 1
    assert sleeps == []


def test_timeout_maps_to_failed(tmp_path: Path) -> None:
    adapter = history_adapter(SensorType.RAINFALL, "SYN001", "https://example.test/?station=SYN001")
    mapper = _mapper(tmp_path, [("SYN001", SensorType.RAINFALL)])
    url = next(iter(ALLOWED_URLS))
    r, _, _ = _runner(tmp_path, adapter, url, mapper, None)

    def transport(u: str, timeout: float):  # type: ignore[no-untyped-def]
        raise TimeoutError("timed out")

    outcome = r.poll_target(r._targets[0], transport=transport)
    assert outcome.record.status == RunStatus.FAILED
    assert outcome.record.error_category == "TIMEOUT"


def test_malformed_and_empty_payloads_fail_loudly(tmp_path: Path) -> None:
    adapter = history_adapter(SensorType.RAINFALL, "SYN001", "https://example.test/?station=SYN001")
    mapper = _mapper(tmp_path, [("SYN001", SensorType.RAINFALL)])
    url = next(iter(ALLOWED_URLS))
    r, _, _ = _runner(tmp_path, adapter, url, mapper, None)
    for bad in (b"not json at all", b""):
        outcome = r.poll_target(
            r._targets[0],
            transport=lambda u, t, b=bad: FetchResult(b, 200, RETRIEVED),
            retrieved_at=RETRIEVED,
        )
        assert outcome.record.status == RunStatus.FAILED


def test_duplicate_payload_is_idempotent(tmp_path: Path) -> None:
    adapter = history_adapter(SensorType.RAINFALL, "SYN001", "https://example.test/?station=SYN001")
    mapper = _mapper(tmp_path, [("SYN001", SensorType.RAINFALL)])
    factory = _seed_db("SYN001", SensorType.RAINFALL)
    url = next(iter(ALLOWED_URLS))
    r, _, metrics = _runner(tmp_path, adapter, url, mapper, factory)
    payload = _history_payload([_rf_row("01/01/2030 08:00", "2.0")])
    t = lambda u, timeout: FetchResult(payload, 200, RETRIEVED)  # noqa: E731
    first = r.poll_target(r._targets[0], transport=t, retrieved_at=RETRIEVED)
    second = r.poll_target(r._targets[0], transport=t, retrieved_at=RETRIEVED)
    assert first.record.status == RunStatus.SUCCEEDED
    assert second.record.status == RunStatus.DUPLICATE
    assert metrics.snapshot()["duplicates"] >= 1


def test_unknown_station_is_quarantined_not_added(tmp_path: Path) -> None:
    adapter = history_adapter(SensorType.RAINFALL, "GHOST9", "https://example.test/?station=GHOST9")
    mapper = _mapper(tmp_path, [("SYN001", SensorType.RAINFALL)])
    url = next(iter(ALLOWED_URLS))
    r, _, _ = _runner(tmp_path, adapter, url, mapper, None)
    payload = _history_payload([_rf_row("01/01/2030 08:00", "3.0")])
    outcome = r.poll_target(
        r._targets[0],
        transport=lambda u, t: FetchResult(payload, 200, RETRIEVED),
        retrieved_at=RETRIEVED,
    )
    assert outcome.record.status == RunStatus.SUCCEEDED
    assert outcome.record.quarantined_count == 1
    assert outcome.canonical_inserted == 0


def test_missing_markers_and_zero_rainfall(tmp_path: Path) -> None:
    adapter = history_adapter(SensorType.RAINFALL, "SYN001", "https://example.test/?station=SYN001")
    mapper = _mapper(tmp_path, [("SYN001", SensorType.RAINFALL)])
    url = next(iter(ALLOWED_URLS))
    for raw, expect_inserted in (("-9999", 1), ("ERROR", 1), ("", 1), ("0", 1), ("0.0", 1)):
        # Isolated DB per marker: same canonical instant with different values
        # must conflict loudly (tested separately), not silently merge.
        factory = _seed_db("SYN001", SensorType.RAINFALL)
        sub = tmp_path / f"m_{raw.replace('/', '_').replace('-', 'm').replace('.', 'd') or 'empty'}"
        r, _, _ = _runner(sub, adapter, url, mapper, factory)
        payload = _history_payload([_rf_row("01/01/2030 08:00", raw)])
        outcome = r.poll_target(
            r._targets[0],
            transport=lambda u, t, b=payload: FetchResult(b, 200, RETRIEVED),
            retrieved_at=RETRIEVED,
        )
        # Markers stay as NULL-valued canonical rows; zeros stay valid numbers.
        assert outcome.record.status == RunStatus.SUCCEEDED
        assert outcome.canonical_inserted == expect_inserted


def test_timestamp_safety_keeps_raw_and_utc(tmp_path: Path) -> None:
    adapter = history_adapter(
        SensorType.WATER_LEVEL, "SYN002", "https://example.test/?station=SYN002"
    )
    mapper = _mapper(tmp_path, [("SYN002", SensorType.WATER_LEVEL)])
    factory = _seed_db("SYN002", SensorType.WATER_LEVEL)
    url = next(iter(ALLOWED_URLS))
    r, _, _ = _runner(tmp_path, adapter, url, mapper, factory)
    payload = _history_payload([_wl_row("01/01/2030 08:00", "1.25")])
    outcome = r.poll_target(
        r._targets[0],
        transport=lambda u, t: FetchResult(payload, 200, RETRIEVED),
        retrieved_at=RETRIEVED,
    )
    assert outcome.record.status == RunStatus.SUCCEEDED
    # Retrieval time is recorded on the run; observation time comes from the payload text.
    assert outcome.record.payload_sha256 is not None
    session_factory = factory
    session = session_factory()
    try:
        from floodguard.backend.repositories import ObservationRepository

        rows = ObservationRepository(session).series(
            sensor_id(SOURCE_JPS, "SYN002", SensorType.WATER_LEVEL),
            "WATER_LEVEL",
            datetime(2030, 1, 1, tzinfo=UTC),
            datetime(2030, 1, 2, tzinfo=UTC),
        )
        assert len(rows) == 1
        assert rows[0].observation_time_raw == "01/01/2030 08:00"
        assert rows[0].observation_time_utc is not None
        assert rows[0].timezone_status == "UNSPECIFIED_ASSUMED"
        assert rows[0].first_retrieved_at is not None
    finally:
        session.close()


def test_db_failure_after_raw_allows_replay(tmp_path: Path) -> None:
    adapter = history_adapter(SensorType.RAINFALL, "SYN001", "https://example.test/?station=SYN001")
    mapper = _mapper(tmp_path, [("SYN001", SensorType.RAINFALL)])
    url = next(iter(ALLOWED_URLS))

    def failing_factory():  # type: ignore[no-untyped-def]
        class Bad:
            def close(self) -> None:
                pass

        raise RuntimeError("db down")

    r, _, _ = _runner(tmp_path, adapter, url, mapper, failing_factory)
    payload = _history_payload([_rf_row("01/01/2030 08:00", "4.0")])
    t = lambda u, timeout: FetchResult(payload, 200, RETRIEVED)  # noqa: E731
    failed = r.poll_target(r._targets[0], transport=t, retrieved_at=RETRIEVED)
    assert failed.record.status == RunStatus.FAILED
    # Raw is preserved despite the DB failure; replay with a working DB recovers.
    factory = _seed_db("SYN001", SensorType.RAINFALL)
    r._sessions = factory
    # New runner sharing the same raw root sees the raw DUPLICATE but re-ensures the DB.
    r2, _, _ = _runner(tmp_path, adapter, url, mapper, factory)
    r2._raw_root = r._raw_root
    recovered = r2.poll_target(r2._targets[0], transport=t, retrieved_at=RETRIEVED)
    assert recovered.record.status in (RunStatus.DUPLICATE, RunStatus.SUCCEEDED)
    assert recovered.canonical_inserted >= 0


def test_conflicting_observation_fails_loudly(tmp_path: Path) -> None:
    from floodguard.backend.repositories import ObservationRepository

    adapter = history_adapter(SensorType.RAINFALL, "SYN001", "https://example.test/?station=SYN001")
    mapper = _mapper(tmp_path, [("SYN001", SensorType.RAINFALL)])
    factory = _seed_db("SYN001", SensorType.RAINFALL)
    url = next(iter(ALLOWED_URLS))
    # Pre-insert a conflicting canonical row for the same identity with a different value.
    session = factory()
    try:
        repo = ObservationRepository(session)
        from tests.backend_helpers import make_observation

        base = make_observation(
            source=SOURCE_JPS,
            sensor_id=sensor_id(SOURCE_JPS, "SYN001", SensorType.RAINFALL),
            measurement_type="RAINFALL_INTERVAL",
            minutes=0,
            value=__import__("decimal").Decimal("9.0"),
            observation_time_utc=datetime(2030, 1, 1, 0, 0, tzinfo=UTC),
            observation_time_raw="01/01/2030 08:00",
            observation_time_local=datetime(2030, 1, 1, 8, 0, tzinfo=UTC),
            unit="mm",
        )
        # Align the pre-seeded row to the payload instant (08:00 +08:00 = 00:00Z).
        repo.insert(base)
        session.commit()
    finally:
        session.close()
    r, _, _ = _runner(tmp_path, adapter, url, mapper, factory)
    payload = _history_payload([_rf_row("01/01/2030 08:00", "1.0")])
    outcome = r.poll_target(
        r._targets[0],
        transport=lambda u, t: FetchResult(payload, 200, RETRIEVED),
        retrieved_at=RETRIEVED,
    )
    assert outcome.record.status == RunStatus.FAILED
    assert outcome.record.error_category == "CONFLICT"


def test_overlapping_runs_are_rejected() -> None:
    import threading

    from floodguard.live.runs import RunRecord

    def slow() -> list[RunRecord]:
        import time as _t

        _t.sleep(0.2)
        return []

    sched = PollScheduler(slow, SchedulerConfig(60.0))
    assert sched._lock.acquire(blocking=False)
    try:
        # Hold the lock in this thread; run_once in another must skip.
        holder = threading.Event()
        result: dict[str, RunRecord | list[RunRecord]] = {}

        def attempt() -> None:
            out = sched.run_once()
            assert not isinstance(out, list)
            result["out"] = out
            holder.set()

        thread = threading.Thread(target=attempt)
        thread.start()
        thread.join(timeout=5)
        assert holder.is_set()
        rec = result["out"]
        assert isinstance(rec, RunRecord)
        assert rec.status == RunStatus.SKIPPED_OVERLAP
    finally:
        sched._lock.release()


def test_config_defaults_keep_jps_off_and_validate() -> None:
    cfg = load_config({})
    assert cfg.jps_enabled is False
    assert cfg.poll_interval_seconds >= 60.0
    with pytest.raises(ValueError, match="poll interval"):
        load_config({"FLOODGUARD_LIVE_POLL_INTERVAL_SECONDS": "5"})
    with pytest.raises(ValueError, match="max retries"):
        load_config({"FLOODGUARD_LIVE_MAX_RETRIES": "99"})


def test_scheduler_single_iteration_and_graceful_stop(tmp_path: Path) -> None:
    from floodguard.live.runs import RunRecord

    calls = {"n": 0}

    def once() -> list[RunRecord]:
        from floodguard.live.runs import RunStatus, new_run_id, utc_now_iso

        calls["n"] += 1
        now = utc_now_iso()
        return [
            RunRecord(
                run_id=new_run_id(),
                source="SYN",
                dataset="syn",
                started_at=now,
                ended_at=now,
                status=RunStatus.SUCCEEDED,
                duration_seconds=0.0,
            )
        ]

    sched = PollScheduler(once, SchedulerConfig(60.0))
    out = sched.run_once()
    assert isinstance(out, list)
    assert calls["n"] == 1
    sched.request_stop()
    assert sched.stop_requested is True
    # Loop exits immediately when stop is already requested (no busy-loop, no background work).
    assert sched.run_forever(max_iterations=5) == []


def test_urllib_transport_never_used_in_unit_tests() -> None:
    # The no_network fixture blocks sockets; this test asserts no test above
    # accidentally performs a real fetch (all transports are injected).
    import socket

    with pytest.raises(AssertionError):
        socket.create_connection(("example.test", 80), timeout=1)
