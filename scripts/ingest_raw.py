"""Ingest ONE captured raw payload into the immutable raw store, print the report JSON, exit.

No loop, no scheduler, and no JPS network access: JPS payloads must be supplied with --input
(JPS retrieval is PERMISSION REQUIRED; see docs/RAW_INGESTION_DESIGN.md). Only
``data-gov-my-weather --fetch`` performs a network request (one GET, CC BY 4.0 open API).

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\ingest_raw.py jps-rainfall --input FILE \\
        --retrieved-at 2026-09-24T01:39:20+08:00 --source-reference URL
    .venv\\Scripts\\python.exe scripts\\ingest_raw.py jps-water-level-history --input FILE \\
        --retrieved-at ISO --source-reference URL --source-station-id 27608

Exit codes: 0 SUCCEEDED or DUPLICATE, 1 FAILED, 2 rejected before a batch started (arguments,
input file or station master unusable; nothing is written and no manifest entry is made).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from floodguard.ingestion.adapters.data_gov_my import FORECAST_URL, WeatherForecastAdapter
from floodguard.ingestion.adapters.jps import RAINFALL_LISTING, WATER_LEVEL_LISTING, history_adapter
from floodguard.ingestion.contracts import Adapter, BatchStatus
from floodguard.ingestion.fetch import OPEN_DATA_GOV_MY, PermissionedFetcher
from floodguard.ingestion.pipeline import ingest_batch
from floodguard.ingestion.station_mapping import (
    DEFAULT_SENSORS_CSV,
    SensorMapper,
    StationMappingError,
)
from floodguard.station_master import SensorType

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = ROOT / "data" / "raw"
DEFAULT_STATION_MASTER = ROOT / DEFAULT_SENSORS_CSV


def aware_datetime(text: str) -> datetime:
    try:
        t = datetime.fromisoformat(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"not ISO 8601: {text!r}") from e
    if t.tzinfo is None:
        raise argparse.ArgumentTypeError(f"--retrieved-at needs an explicit offset: {text!r}")
    return t


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Ingest one raw payload (offline, one batch).")
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser, *, required: bool = True) -> None:
        p.add_argument("--input", type=Path, required=required, help="captured payload file")
        p.add_argument("--retrieved-at", type=aware_datetime, required=required)
        p.add_argument("--source-reference", required=required, help="request URL or file ref")
        p.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)

    for name in (
        "jps-rainfall",
        "jps-water-level",
        "jps-rainfall-history",
        "jps-water-level-history",
    ):
        p = sub.add_parser(name)
        common(p)
        p.add_argument("--station-master", type=Path, default=DEFAULT_STATION_MASTER)
        if name.endswith("history"):
            p.add_argument(
                "--source-station-id", required=True, help="jps_internal_id as requested"
            )
    w = sub.add_parser("data-gov-my-weather", help="data.gov.my Weather API forecast")
    common(w, required=False)
    w.add_argument("--fetch", action="store_true", help="make ONE live request (CC BY 4.0 API)")
    return ap


def _adapter(args: argparse.Namespace) -> Adapter:
    if args.command == "jps-rainfall":
        return RAINFALL_LISTING
    if args.command == "jps-water-level":
        return WATER_LEVEL_LISTING
    if args.command == "jps-rainfall-history":
        return history_adapter(SensorType.RAINFALL, args.source_station_id, args.source_reference)
    if args.command == "jps-water-level-history":
        return history_adapter(
            SensorType.WATER_LEVEL, args.source_station_id, args.source_reference
        )
    return WeatherForecastAdapter()


def main(argv: Sequence[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    try:
        adapter = _adapter(args)
    except ValueError as e:
        ap.error(str(e))
    mapper = None
    if args.command == "data-gov-my-weather":
        if args.fetch == (args.input is not None):
            ap.error("data-gov-my-weather: give exactly one of --input or --fetch")
        if args.fetch:
            got = PermissionedFetcher(adapter.source, OPEN_DATA_GOV_MY).fetch(FORECAST_URL)
            payload, retrieved_at, reference = got.body, got.retrieved_at, FORECAST_URL
        elif args.retrieved_at is None or args.source_reference is None:
            ap.error("--input needs --retrieved-at and --source-reference")
    else:
        try:
            mapper = SensorMapper.from_csv(args.station_master)
        except StationMappingError as e:
            print(f"REJECTED: {e}", file=sys.stderr)
            return 2
    if args.input is not None:
        try:
            payload = args.input.read_bytes()
        except OSError as e:
            print(f"REJECTED: cannot read input: {e}", file=sys.stderr)
            return 2
        retrieved_at, reference = args.retrieved_at, args.source_reference

    report = ingest_batch(
        payload,
        adapter,
        source_reference=reference,
        retrieved_at=retrieved_at,
        raw_root=args.raw_root,
        mapper=mapper,
    )
    print(json.dumps(report.to_json_dict(), ensure_ascii=False, indent=2))
    return 1 if report.status is BatchStatus.FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
