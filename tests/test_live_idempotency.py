"""Idempotency tests (Phase 10, Task 4; offline, synthetic)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from floodguard.ingestion.adapters.jps import history_adapter
from floodguard.ingestion.fetch import AccessPermission
from floodguard.ingestion.hashing import sha256_hex
from floodguard.live import idempotency as live_idem
from floodguard.live import runner as live_runner
from floodguard.live.http import ALLOWED_URLS, ControlledFetcher, HttpConfig
from floodguard.live.metrics import MetricsCollector
from floodguard.live.runs import RunStatus, RunStore
from floodguard.station_master import SOURCE_JPS, SensorType

pytestmark = pytest.mark.usefixtures("no_network")

PERM = AccessPermission(
    source=SOURCE_JPS, scope="network_fetch", granted_by="s", reference="s", granted_on="2030-01-01"
)
RETRIEVED = datetime(2030, 1, 1, 8, 5, tzinfo=UTC)


def test_contract_describes_keys_and_policies() -> None:
    contract = live_idem.describe_contract()
    assert "source + dataset + partition + payload_sha256" in contract["raw_key"]
    assert (
        "canonical" in contract["canonical_key"].lower()
        or "observation" in contract["canonical_key"].lower()
    )
    assert "never silent" in contract["conflict_policy"].lower()


def test_raw_duplicate_helper_matches_manifest(tmp_path: Path) -> None:
    import csv

    from floodguard.ingestion.fetch import FetchResult
    from floodguard.ingestion.station_mapping import SensorMapper
    from floodguard.station_master import sensor_id, site_id

    csv_path = tmp_path / "sensors.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
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
        w.writerow(
            [
                sensor_id(SOURCE_JPS, "SYN001", SensorType.RAINFALL),
                site_id(SOURCE_JPS, "SYN001"),
                "RAINFALL",
                SOURCE_JPS,
                "SYN001",
                "station_master/v1",
            ]
        )
    mapper = SensorMapper.from_csv(csv_path)
    adapter = history_adapter(SensorType.RAINFALL, "SYN001", "https://example.test/?station=SYN001")
    url = next(iter(ALLOWED_URLS))
    fetcher = ControlledFetcher(adapter.source, PERM, HttpConfig())
    raw_root = tmp_path / "raw"
    target = live_runner.PollTarget(adapter, url, url)
    run = live_runner.LivePollRunner(
        targets=[target],
        fetcher_by_source={adapter.source: fetcher},
        raw_root=raw_root,
        mapper=mapper,
        session_factory=None,
        run_store=RunStore(tmp_path / "runs.jsonl"),
        metrics=MetricsCollector(),
        clock=lambda: 0.0,
    )
    payload = json.dumps(
        {
            "info": {"name": "S"},
            "values": [
                {
                    "dt": "01/01/2030 08:00",
                    "raw": "1.0",
                    "clean": "1.0",
                    "chourly": "1.0",
                    "cdaily": "1.0",
                    "tdaily": "1.0",
                    "cyearly": "1.0",
                    "c15min": "1.0",
                }
            ],
        }
    ).encode()
    sha = sha256_hex(payload)
    assert (
        live_idem.is_raw_duplicate(
            raw_root, adapter.source, adapter.dataset, adapter.partition, sha
        )
        is False
    )
    out = run.poll_target(
        target, transport=lambda u, t: FetchResult(payload, 200, RETRIEVED), retrieved_at=RETRIEVED
    )
    assert out.record.status == RunStatus.SUCCEEDED
    assert (
        live_idem.is_raw_duplicate(
            raw_root, adapter.source, adapter.dataset, adapter.partition, sha
        )
        is True
    )
    # Replay is a DUPLICATE at the raw layer and stays idempotent downstream.
    out2 = run.poll_target(
        target, transport=lambda u, t: FetchResult(payload, 200, RETRIEVED), retrieved_at=RETRIEVED
    )
    assert out2.record.status == RunStatus.DUPLICATE


def test_run_store_detects_incomplete_runs(tmp_path: Path) -> None:
    from floodguard.live.runs import RunRecord, RunStatus, new_run_id

    store = RunStore(tmp_path / "runs.jsonl")
    started = RunRecord(
        run_id=new_run_id(),
        source="S",
        dataset="d",
        started_at="2030-01-01T00:00:00+00:00",
        ended_at=None,
        status=RunStatus.FAILED,
    )
    # Incomplete runs are detectable (started but never closed).
    store.append(started)
    assert len(store.find_incomplete()) == 1
    assert store.last_successful_retrieval() is None
