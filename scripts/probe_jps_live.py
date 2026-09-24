"""One-shot probe of the JPS Pulau Pinang state listings as a live source.

Not a scheduler: by default ONE listing request (plus one state-page request to load the
official district list). ``--samples N --interval S`` takes a small bounded series for
update-behaviour measurement (N <= 20, S >= 60 s).

Reuses the discovery scripts' table contract (``_jps_common.parse_result_table``) - no second
HTML parser. Keeps ``observation_time`` (source display time, no declared timezone) separate from
``retrieved_at`` (local clock, +08:00). ``fg_*`` fields are FloodGuard-derived.

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\probe_jps_live.py water_level
    .venv\\Scripts\\python.exe scripts\\probe_jps_live.py rainfall --station 27608 --station 27661
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import _jps_common as jc
import discover_jps_rainfall_stations as rf
import discover_jps_water_level_stations as wl
from _jps_common import SchemaError, StatePage

SOURCE = "jps_publicinfobanjir"
MAX_SAMPLES = 20
MIN_INTERVAL_S = 60
HEADER_KEYS = ("Content-Type", "Cache-Control", "ETag", "Last-Modified", "Expires", "Date")


@dataclass(frozen=True)
class ListingSpec:
    state_page_url: str
    result_url: str
    link_marker: str
    required_headers: tuple[str, ...]
    cells_per_row: int
    time_col: int
    time_format: str
    value_cols: dict[str, int]  # output name -> cell index (text kept verbatim)
    primary: str  # value that must be numeric for the observation to count as data


SPECS = {
    "rainfall": ListingSpec(
        rf.STATE_PAGE_URL,
        rf.RESULT_URL,
        "rf-graph",
        rf.REQUIRED_HEADERS,
        rf.CELLS_PER_ROW,
        4,
        rf.SOURCE_TIME_FORMAT,
        {"rainfall_since_midnight_mm": 11, "rainfall_1h_mm": 12},
        "rainfall_1h_mm",
    ),
    "water_level": ListingSpec(
        wl.STATE_PAGE_URL,
        wl.RESULT_URL,
        "wl-graph",
        wl.REQUIRED_HEADERS,
        wl.CELLS_PER_ROW,
        6,
        wl.SOURCE_TIME_FORMAT,
        {
            "water_level_m": 7,
            "threshold_normal": 8,
            "threshold_alert": 9,
            "threshold_warning": 10,
            "threshold_danger": 11,
        },
        "water_level_m",
    ),
}


@dataclass(frozen=True)
class Observation:
    source: str
    measurement_type: str
    jps_internal_id: str
    jps_display_station_id: str
    station_name: str
    district: str
    observation_time_raw: str
    observation_time: str | None  # ISO, source-local, no offset
    retrieved_at: str
    values: dict[str, str]
    fg_age_minutes: int | None
    fg_live_status: str


def _primary_ok(text: str) -> bool:
    if text in ("", jc.MISSING_SENTINEL):
        return False
    try:
        float(text)
    except ValueError:
        return False
    return True


def parse_listing(
    html: str, sensor: str, page: StatePage, retrieved_at: datetime
) -> list[Observation]:
    """Listing fragment -> observations. Table-level problems raise SchemaError; row-level
    timestamp/value problems are kept and classified (INVALID / NO_DATA), never dropped."""
    spec = SPECS[sensor]
    rows, ids = jc.parse_result_table(
        html,
        page,
        link_marker=spec.link_marker,
        required_headers=spec.required_headers,
        cells_per_row=spec.cells_per_row,
        district_col=3,
    )
    out = []
    for row, key in zip(rows, ids, strict=True):
        raw_t = row[spec.time_col]
        try:
            t: datetime | None = datetime.strptime(raw_t, spec.time_format)  # noqa: DTZ007
        except ValueError:
            t = None
        values = {name: row[col] for name, col in spec.value_cols.items()}
        age = jc.fg_age_minutes(t, retrieved_at)
        out.append(
            Observation(
                source=SOURCE,
                measurement_type=sensor,
                jps_internal_id=key,
                jps_display_station_id=row[1],
                station_name=row[2],
                district=row[3],
                observation_time_raw=raw_t,
                observation_time=t.isoformat() if t else None,
                retrieved_at=retrieved_at.isoformat(),
                values=values,
                fg_age_minutes=age,
                fg_live_status=jc.fg_live_status(
                    age, _primary_ok(values[spec.primary]), jc.LIVE_RULES[sensor]
                ),
            )
        )
    return sorted(out, key=lambda o: o.jps_internal_id)


def take_sample(sensor: str, page: StatePage, stations: set[str], save_raw: Path | None) -> Any:
    spec = SPECS[sensor]
    retrieved_at = jc.now_myt()
    resp = jc.fetch_response(spec.result_url)
    meta: dict[str, Any] = {
        "retrieved_at": retrieved_at.isoformat(),
        "http_status": resp.status,
        "headers": {k: resp.headers[k] for k in HEADER_KEYS if k in resp.headers},
        "bytes": len(resp.body.encode("utf-8")),
    }
    if resp.status != 200:
        raise OSError(f"HTTP {resp.status} for {spec.result_url}")
    obs = parse_listing(resp.body, sensor, page, retrieved_at)
    if save_raw:
        stem = "searchresultrainfall" if sensor == "rainfall" else "aras-air-data"
        meta["raw_file"] = str(jc.save_raw(resp.body, save_raw, stem, retrieved_at))
    meta["rows"] = len(obs)
    if stations:
        obs = [o for o in obs if o.jps_internal_id in stations]
    return {"meta": meta, "observations": [asdict(o) for o in obs]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="One-shot JPS Pulau Pinang live listing probe.")
    ap.add_argument("sensor", choices=sorted(SPECS))
    ap.add_argument("--station", action="append", default=[], help="jps_internal_id filter")
    ap.add_argument("--samples", type=int, default=1, help=f"1..{MAX_SAMPLES} (default 1)")
    ap.add_argument("--interval", type=int, default=105, help=f">= {MIN_INTERVAL_S} s")
    ap.add_argument("--jsonl", type=Path, help="append each sample as one JSON line")
    ap.add_argument("--save-raw", type=Path, metavar="DIR", help="save the first sample body")
    args = ap.parse_args(argv)
    if not 1 <= args.samples <= MAX_SAMPLES or args.interval < MIN_INTERVAL_S:
        print(
            f"REQUEST REJECTED: samples must be 1..{MAX_SAMPLES}, interval >= {MIN_INTERVAL_S}",
            file=sys.stderr,
        )
        return 4

    try:
        page = jc.parse_state_page(jc.fetch(SPECS[args.sensor].state_page_url))
        for i in range(args.samples):
            if i:
                time.sleep(max(0.0, args.interval - jc.REQUEST_DELAY_S))
            sample = take_sample(
                args.sensor, page, set(args.station), args.save_raw if i == 0 else None
            )
            line = json.dumps(sample, ensure_ascii=False)
            if args.jsonl:
                args.jsonl.parent.mkdir(parents=True, exist_ok=True)
                with args.jsonl.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            statuses: dict[str, int] = {}
            for o in sample["observations"]:
                statuses[o["fg_live_status"]] = statuses.get(o["fg_live_status"], 0) + 1
            newest = max((o["observation_time"] or "" for o in sample["observations"]), default="")
            print(
                f"{sample['meta']['retrieved_at']} rows={sample['meta']['rows']} "
                f"newest_observation={newest} fg_live_status={dict(sorted(statuses.items()))}"
            )
            if args.samples == 1 and not args.jsonl:
                print(line)
    except SchemaError as e:
        print(f"SCHEMA CHANGE: {e}", file=sys.stderr)
        return 2
    except OSError as e:  # includes HTTP 403/429: stop, do not retry
        print(f"FETCH FAILED: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
