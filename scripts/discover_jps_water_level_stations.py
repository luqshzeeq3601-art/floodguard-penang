"""Discover Pulau Pinang river water-level stations listed by JPS Public Infobanjir.

Discovery/inventory only: two polite GET requests per run, no historical download.

1. State page ``/aras-air/data-paras-air/?state=PNG&type=NEGERI``: official district list,
   selected state label, footer "Kemaskini Terakhir".
2. Result fragment (the XHR the page itself issues): HTML table of water-level stations with
   basin, latest level and published threshold levels.

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\discover_jps_water_level_stations.py --save-raw
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

STATE_PAGE_URL = f"{jc.BASE}/aras-air/data-paras-air/?state={jc.STATE_CODE}&type=NEGERI"
RESULT_URL = (
    f"{jc.BASE}/index.php/aras-air/data-paras-air/aras-air-data/"
    f"?state={jc.STATE_CODE}&district=ALL&station=ALL"
)
SOURCE_TIME_FORMAT = "%d/%m/%Y %H:%M"
# Bil, ID, name, district, basin, sub-basin, last update, level, normal, alert, warning, danger.
CELLS_PER_ROW = 12
REQUIRED_HEADERS = (
    "ID Stesen",
    "Nama Stesen",
    "Daerah",
    "Lembangan",
    "Sub Lembangan",
    "Kemaskini Terakhir",
    "Aras Air (m)",
    "Tahap Nilai Ambang",
    "Normal",
    "Waspada",
    "Amaran",
    "Bahaya",
)
DEFAULT_OUTPUT = jc.METADATA_DIR / "penang_water_level_stations.csv"
DEFAULT_RAW_DIR = jc.METADATA_DIR / "raw"

CSV_COLUMNS = (
    "jps_internal_id",
    "jps_display_station_id",
    "fg_display_station_id_flag",
    "station_name",
    "state",
    "district",
    "main_basin",
    "sub_river_basin",
    "latest_observation_time",
    "water_level_m",
    "threshold_normal",
    "threshold_alert",
    "threshold_warning",
    "threshold_danger",
    "fg_threshold_order_flag",
    "fg_freshness_minutes",
    "fg_freshness_status",
    "source_row",
    "source_url",
    "discovered_at",
)


@dataclass(frozen=True)
class WaterLevelStationRecord:
    jps_internal_id: str
    jps_display_station_id: str
    fg_display_station_id_flag: str
    station_name: str
    state: str
    district: str
    main_basin: str
    sub_river_basin: str
    latest_observation_time: str
    water_level_m: str
    threshold_normal: str
    threshold_alert: str
    threshold_warning: str
    threshold_danger: str
    fg_threshold_order_flag: str
    fg_freshness_minutes: int
    fg_freshness_status: str
    source_row: int
    source_url: str
    discovered_at: str


def _check_number(text: str, what: str, row: int) -> float | None:
    """Published numbers are kept verbatim; this only verifies they are blank or numeric."""
    if text == "":
        return None
    try:
        return float(text)
    except ValueError as e:
        raise SchemaError(f"row {row}: non-numeric {what} {text!r}") from e


def fg_threshold_order_flag(
    alert: float | None, warning: float | None, danger: float | None
) -> str:
    """JPS levels escalate Waspada (alert) -> Amaran (warning) -> Bahaya (danger).

    "Normal" is not checked: its meaning relative to the others is not documented
    (many rows publish 0.00).
    """
    if alert is None or warning is None or danger is None:
        return "missing"
    return "ok" if alert <= warning <= danger else "not_ascending"


def parse_result_table(
    html: str, page: StatePage, source_url: str, discovered_at: str
) -> list[WaterLevelStationRecord]:
    """Parse the aras-air-data fragment into validated records sorted by internal id."""
    rows, ids = jc.parse_result_table(
        html,
        page,
        link_marker="wl-graph",
        required_headers=REQUIRED_HEADERS,
        cells_per_row=CELLS_PER_ROW,
        district_col=3,
    )
    times = [jc.parse_source_time(r[6], SOURCE_TIME_FORMAT, i) for i, r in enumerate(rows, 1)]
    orders = []
    for i, r in enumerate(rows, 1):
        _check_number(r[7], "water level", i)
        _check_number(r[8], "normal threshold", i)
        a, w, d = (_check_number(r[c], f"threshold col {c}", i) for c in (9, 10, 11))
        orders.append(fg_threshold_order_flag(a, w, d))
    flags = jc.fg_display_id_flags([r[1] for r in rows])
    records = [
        WaterLevelStationRecord(
            jps_internal_id=key,
            jps_display_station_id=row[1],
            fg_display_station_id_flag=flag,
            station_name=row[2],
            state=jc.EXPECTED_STATE,
            district=row[3],
            main_basin=row[4],
            sub_river_basin=row[5],
            latest_observation_time=t.isoformat(),
            water_level_m=row[7],
            threshold_normal=row[8],
            threshold_alert=row[9],
            threshold_warning=row[10],
            threshold_danger=row[11],
            fg_threshold_order_flag=order,
            fg_freshness_minutes=minutes,
            fg_freshness_status=status,
            source_row=int(row[0]),
            source_url=source_url,
            discovered_at=discovered_at,
        )
        for row, key, t, flag, order, (minutes, status) in zip(
            rows, ids, times, flags, orders, jc.fg_freshness(times), strict=True
        )
    ]
    return sorted(records, key=lambda r: r.jps_internal_id)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Discover JPS Pulau Pinang water-level stations.")
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
        print(f"raw evidence: {jc.save_raw(html, args.raw_dir, 'aras-air-data', now)}")
    jc.write_csv(records, CSV_COLUMNS, args.output)

    def count(attr: str) -> dict[str, int]:
        return dict(sorted(Counter(str(getattr(r, attr)) for r in records).items()))

    print(f"discovered_at={now.isoformat()} page_last_updated={page.page_last_updated!r}")
    print(f"stations={len(records)} fg_freshness={count('fg_freshness_status')}")
    print(f"display_id_flags={count('fg_display_station_id_flag')}")
    print(f"threshold_order={count('fg_threshold_order_flag')} districts={count('district')}")
    print(f"newest_observation={max(r.latest_observation_time for r in records)}")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
