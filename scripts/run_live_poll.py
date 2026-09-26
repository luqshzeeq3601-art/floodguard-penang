"""Run one live-ingestion poll cycle (Phase 10 manual/debug entry point).

Default is a single deterministic iteration (no loop, no background work).
``--loop`` runs the focused scheduler until SIGINT/SIGTERM with graceful
shutdown and no overlapping runs. JPS polling stays disabled unless
``FLOODGUARD_LIVE_JPS_ENABLED=1`` with a valid local permission record;
without permission the run reports BLOCKED_PERMISSION and performs no network I/O.

Offline-safe: with ``--synthetic`` (tests/smoke) no network is used.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from floodguard.ingestion.fetch import load_permission  # noqa: E402
from floodguard.ingestion.station_mapping import SensorMapper  # noqa: E402
from floodguard.live.config import load_config  # noqa: E402
from floodguard.live.http import ControlledFetcher, HttpConfig  # noqa: E402
from floodguard.live.metrics import MetricsCollector  # noqa: E402
from floodguard.live.runner import LivePollRunner, build_targets  # noqa: E402
from floodguard.live.runs import RunStore  # noqa: E402
from floodguard.live.scheduler import PollScheduler, SchedulerConfig  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run one live poll (manual/debug).")
    ap.add_argument("--loop", action="store_true", help="run the scheduler loop")
    ap.add_argument("--station-master", type=Path, default=None)
    return ap


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config()
    permission = load_permission(config.permission_file)
    http = HttpConfig(timeout_seconds=config.http_timeout_seconds, max_retries=config.max_retries)
    fetchers = {
        "JPS_PUBLIC_INFOBANJIR": ControlledFetcher("JPS_PUBLIC_INFOBANJIR", permission, http),
        "DATA_GOV_MY_WEATHER_API": ControlledFetcher("DATA_GOV_MY_WEATHER_API", permission, http),
    }
    mapper = None
    if args.station_master is not None and args.station_master.is_file():
        try:
            mapper = SensorMapper.from_csv(args.station_master)
        except Exception as exc:
            print(f"REJECTED: station master unusable: {exc}", file=sys.stderr)
            return 2
    targets = build_targets() if config.jps_enabled else []
    runner = LivePollRunner(
        targets=targets,
        fetcher_by_source=fetchers,
        raw_root=config.raw_root,
        mapper=mapper,
        session_factory=None,
        run_store=RunStore(config.run_store),
        metrics=MetricsCollector(),
    )
    scheduler = PollScheduler(runner.run_all, SchedulerConfig(config.poll_interval_seconds))
    if args.loop:
        outcomes = scheduler.run_forever()
        print(json.dumps([r for batch in outcomes for r in batch], default=str, indent=2))
        return 0
    records = runner.run_all()
    print(json.dumps([r.to_json_dict() for r in records], indent=2))
    if not records:
        print("no targets enabled (JPS polling OFF by default)", file=sys.stderr)
        return 0
    order = {"FAILED": 1, "PARTIAL": 0, "SUCCEEDED": 0, "DUPLICATE": 0, "BLOCKED_PERMISSION": 0}
    worst = max(order.get(r.status, 1) for r in records)
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
