"""Discover Pulau Pinang rainfall stations listed by JPS Public Infobanjir.

Discovery/inventory only: two polite GET requests per run, no historical download.

1. State page (server-rendered): official district list, selected state label, footer
   "Kemaskini Terakhir".
2. Result fragment (the XHR the page itself issues): HTML table of rainfall stations.

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\discover_jps_rainfall_stations.py --save-raw
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import _jps_common as jc
from _jps_common import SchemaError, StatePage, parse_state_page

__all__ = ["SchemaError", "StatePage", "parse_result_table", "parse_state_page"]

STATE_PAGE_URL = f"{jc.BASE}/hujan/data-hujan/?state={jc.STATE_CODE}&type=NEGERI"
RESULT_URL = (
    f"{jc.BASE}/wp-content/themes/shapely/agency/searchresultrainfall.php"
    f"?state={jc.STATE_CODE}&district=ALL&station=ALL&loginStatus=0&language=0"
)
SOURCE_TIME_FORMAT = "%d/%m/%Y %H:%M:%S"
# Cells per data row: Bil, ID, name, district, last update, 6 daily, since-midnight, 1h.
CELLS_PER_ROW = 13
REQUIRED_HEADERS = ("ID Stesen", "Nama Stesen", "Daerah", "Kemaskini Terakhir", "Jumlah 1 Jam")
DEFAULT_OUTPUT = jc.METADATA_DIR / "penang_rainfall_stations.csv"
DEFAULT_RAW_DIR = jc.METADATA_DIR / "raw"

CSV_COLUMNS = (
    "jps_internal_id",
    "jps_display_station_id",
    "fg_display_station_id_flag",
    "station_name",
    "state",
    "district",
    "latest_observation_time",
    "fg_freshness_minutes",
    "fg_freshness_status",
    "source_row",
    "source_url",
    "discovered_at",
)


@dataclass(frozen=True)
class StationRecord:
    jps_internal_id: str
    jps_display_station_id: str
    fg_display_station_id_flag: str
    station_name: str
    state: str
    district: str
    latest_observation_time: str
    fg_freshness_minutes: int
    fg_freshness_status: str
    source_row: int
    source_url: str
    discovered_at: str


def parse_result_table(
    html: str, page: StatePage, source_url: str, discovered_at: str
) -> list[StationRecord]:
    """Parse the searchresultrainfall.php fragment into validated records sorted by internal id."""
    rows, ids = jc.parse_result_table(
        html,
        page,
        link_marker="rf-graph",
        required_headers=REQUIRED_HEADERS,
        cells_per_row=CELLS_PER_ROW,
        district_col=3,
    )
    times = [jc.parse_source_time(r[4], SOURCE_TIME_FORMAT, i) for i, r in enumerate(rows, 1)]
    flags = jc.fg_display_id_flags([r[1] for r in rows])
    records = [
        StationRecord(
            jps_internal_id=key,
            jps_display_station_id=row[1],
            fg_display_station_id_flag=flag,
            station_name=row[2],
            state=jc.EXPECTED_STATE,
            district=row[3],
            latest_observation_time=t.isoformat(),
            fg_freshness_minutes=minutes,
            fg_freshness_status=status,
            source_row=int(row[0]),
            source_url=source_url,
            discovered_at=discovered_at,
        )
        for row, key, t, flag, (minutes, status) in zip(
            rows, ids, times, flags, jc.fg_freshness(times), strict=True
        )
    ]
    return sorted(records, key=lambda r: r.jps_internal_id)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Discover JPS Pulau Pinang rainfall stations.")
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--save-raw", action="store_true", help="save result fragment as evidence")
    ap.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    args = ap.parse_args(argv)

    now = jc.now_myt()
    try:
        page = parse_state_page(jc.fetch(STATE_PAGE_URL))
        html = jc.fetch(RESULT_URL)
        records = parse_result_table(html, page, RESULT_URL, now.isoformat())
    except SchemaError as e:
        print(f"SCHEMA CHANGE: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"FETCH FAILED: {e}", file=sys.stderr)
        return 3

    if args.save_raw:
        print(f"raw evidence: {jc.save_raw(html, args.raw_dir, 'searchresultrainfall', now)}")
    jc.write_csv(records, CSV_COLUMNS, args.output)

    status = Counter(r.fg_freshness_status for r in records)
    flags = Counter(r.fg_display_station_id_flag for r in records)
    print(f"discovered_at={now.isoformat()} page_last_updated={page.page_last_updated!r}")
    print(f"stations={len(records)} fg_freshness={dict(status)} display_id_flags={dict(flags)}")
    print(f"districts={dict(sorted(Counter(r.district for r in records).items()))}")
    print(f"newest_observation={max(r.latest_observation_time for r in records)}")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
