"""Probe JPS Public Infobanjir station history for ONE station and ONE small window.

Feasibility tool, not a downloader: a single GET per run, window capped (default 7 days,
``--allow-wide`` raises the cap to 31 days). Uses the same date-range endpoints the official
``rf-graph`` / ``wl-graph`` pages call. Times are the source's local display times
(``DD/MM/YYYY HH:mm``, no declared timezone).

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\probe_jps_history.py rainfall 27608 2026-09-16 2026-09-17
    .venv\\Scripts\\python.exe scripts\\probe_jps_history.py water_level 27608 \\
        2026-09-16 2026-09-17 --save-raw data\\metadata\\jps\\raw
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import _jps_common as jc
from _jps_common import SchemaError

SOURCE_TIME_FORMAT = "%d/%m/%Y %H:%M"
DEFAULT_MAX_DAYS = 7
WIDE_MAX_DAYS = 31
MISSING_SENTINEL = jc.MISSING_SENTINEL
NO_RESULT_MARKER = "No result"
NO_RESULT_KEY = "fg_no_result"
_T0000 = time(0, 0)
_T0005 = time(0, 5)
STATION_RE = re.compile(r"^ ?[A-Za-z0-9_]{1,32}$")  # observed jps_internal_id shapes


@dataclass(frozen=True)
class Sensor:
    endpoint: str
    extra_param: bool  # rf-graph JS sends extra=, wl-graph date-range JS does not
    value_keys: tuple[str, ...]
    primary: str  # field the official page plots


SENSORS = {
    "rainfall": Sensor(
        "/wp-content/themes/enlighten/query/searchresultrainfalldthourlylead.php",
        True,
        ("dt", "raw", "clean", "chourly", "cdaily", "tdaily", "cyearly", "c15min"),
        "clean",
    ),
    "water_level": Sensor(
        "/wp-content/themes/enlighten/query/searchresultwaterleveldtlead.php",
        False,
        ("dt", "clean", "raw", "ecm", "final", "severity"),
        "final",
    ),
}


class RequestError(ValueError):
    """Probe arguments rejected before any request is made."""


def build_url(sensor: str, station: str, start: datetime, end: datetime, datafreq: int) -> str:
    s = SENSORS[sensor]
    params: dict[str, str] = {"extra": ""} if s.extra_param else {}
    params |= {
        "station": station,
        "from": start.strftime(SOURCE_TIME_FORMAT),
        "to": end.strftime(SOURCE_TIME_FORMAT),
        "datafreq": str(datafreq),
    }
    return f"{jc.BASE}{s.endpoint}?{urlencode(params)}"


def validate_request(station: str, start: datetime, end: datetime, max_days: int) -> None:
    if not STATION_RE.match(station):
        raise RequestError(f"station {station!r} does not look like a jps_internal_id")
    if end <= start:
        raise RequestError("end must be after start")
    if end - start > timedelta(days=max_days):
        raise RequestError(f"window {end - start} exceeds {max_days} days (see --allow-wide)")


def parse_history(text: str, sensor: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    """JSON body -> (info, rows), values kept as source strings (null -> '').

    The server answers ranges without stored data with a non-JSON body containing
    "No result"; that is returned as zero rows and ``info[NO_RESULT_KEY] == "true"``.
    """
    try:
        doc = json.loads(text, parse_float=str, parse_int=str)
    except json.JSONDecodeError as e:
        if NO_RESULT_MARKER in text:  # observed server reply for ranges with no stored data
            return {NO_RESULT_KEY: "true"}, []
        raise SchemaError(f"response is not JSON: {text.strip()[:80]!r}") from e
    if not isinstance(doc, dict) or not isinstance(doc.get("info"), dict):
        raise SchemaError("response lacks an 'info' object")
    values = doc.get("values", [])
    if not isinstance(values, list):
        raise SchemaError("'values' is not a list")
    keys = SENSORS[sensor].value_keys
    rows: list[dict[str, str]] = []
    for i, v in enumerate(values):
        if not isinstance(v, dict) or not set(keys) <= set(v):
            missing = sorted(set(keys) - set(v)) if isinstance(v, dict) else keys
            raise SchemaError(f"value {i}: missing keys {missing}")
        row = {k: "" if v[k] is None else str(v[k]) for k in v}
        try:
            datetime.strptime(row["dt"], SOURCE_TIME_FORMAT)  # noqa: DTZ007
        except ValueError as e:
            raise SchemaError(f"value {i}: unparseable dt {row['dt']!r}") from e
        rows.append(row)
    info = {k: "" if v is None else str(v) for k, v in doc["info"].items()}
    return info, rows


def _is_missing(value: str) -> bool:
    return value in ("", MISSING_SENTINEL)


def summarize(info: dict[str, str], rows: list[dict[str, str]], sensor: str) -> dict[str, Any]:
    """Measured cadence/missingness facts; never fills or repairs values."""
    s = SENSORS[sensor]
    times = [datetime.strptime(r["dt"], SOURCE_TIME_FORMAT) for r in rows]  # noqa: DTZ007
    diffs = [int((b - a).total_seconds() // 60) for a, b in pairwise(times)]
    steps = Counter(d for d in diffs if d > 0)
    dominant = steps.most_common(1)[0][0] if steps else None
    primary = [r[s.primary] for r in rows]
    n_missing = sum(_is_missing(v) for v in primary)
    gap_i = max(range(len(diffs)), key=diffs.__getitem__) if diffs else None
    out: dict[str, Any] = {
        "sensor": sensor,
        "info": info,
        "info_count_matches_rows": info.get("count") == str(len(rows)),
        "rows": len(rows),
        "first_dt": rows[0]["dt"] if rows else None,
        "last_dt": rows[-1]["dt"] if rows else None,
        "dominant_interval_min": dominant,
        "interval_counts_min": dict(sorted(steps.items())),
        "irregular_interval_pct": (
            round(100 * sum(d != dominant for d in diffs) / len(diffs), 2) if diffs else None
        ),
        "duplicate_timestamps": len(times) - len(set(times)),
        "out_of_order": sum(d < 0 for d in diffs),
        "largest_gap_min": diffs[gap_i] if gap_i is not None else None,
        "largest_gap_after": rows[gap_i]["dt"] if gap_i is not None else None,
        "days_with_observations": len(
            {t.date() for t, v in zip(times, primary, strict=True) if not _is_missing(v)}
        ),
        "primary_field": s.primary,
        "primary_missing": n_missing,
        "primary_missing_pct": round(100 * n_missing / len(rows), 2) if rows else None,
        "sentinel_counts": {
            k: {
                "-9999": sum(r[k] == MISSING_SENTINEL for r in rows),
                "blank_or_null": sum(r[k] == "" for r in rows),
            }
            for k in s.value_keys
            if k != "dt"
        },
        "extra_keys": sorted({k for r in rows for k in r} - set(s.value_keys)),
    }
    if sensor == "rainfall":
        out["primary_zero"] = sum(_is_number(v) and float(v) == 0 for v in primary)
        out |= _rainfall_semantics(rows, times)
    else:
        out["severity_counts"] = dict(sorted(Counter(r["severity"] for r in rows).items()))
    return out


def _is_number(v: str) -> bool:
    try:
        float(v)
    except ValueError:
        return False
    return True


def _rainfall_semantics(rows: list[dict[str, str]], times: list[datetime]) -> dict[str, Any]:
    """Consistency counts ("matches/checked") used as evidence for field meanings.

    Only consecutive rows 5 min apart with numeric, non-sentinel values are checked.
    """

    def num(r: dict[str, str], k: str) -> float | None:
        v = r[k]
        return float(v) if _is_number(v) and v != MISSING_SENTINEL else None

    checks = {k: [0, 0] for k in ("raw_eq_cyearly_step", "clean_eq_cyearly_step")}
    checks |= {"clean_eq_raw_sum_15min": [0, 0], "cdaily_eq_prev_plus_raw": [0, 0]}

    def tick(name: str, ok: bool) -> None:
        checks[name][0] += ok
        checks[name][1] += 1

    for i in range(1, len(rows)):
        a, b = rows[i - 1], rows[i]
        if times[i] - times[i - 1] != timedelta(minutes=5):
            continue
        ya, yb, rb, cb = num(a, "cyearly"), num(b, "cyearly"), num(b, "raw"), num(b, "clean")
        if ya is not None and yb is not None and rb is not None and cb is not None:
            tick("raw_eq_cyearly_step", abs(yb - ya - rb) < 1e-6)
            tick("clean_eq_cyearly_step", abs(yb - ya - cb) < 1e-6)
        da, db = num(a, "cdaily"), num(b, "cdaily")
        if da is not None and db is not None and rb is not None and times[i].time() != _T0005:
            tick("cdaily_eq_prev_plus_raw", abs(db - da - rb) < 1e-6)
        if i >= 2 and times[i] - times[i - 2] == timedelta(minutes=10) and cb is not None:
            raws = [num(rows[k], "raw") for k in (i - 2, i - 1, i)]
            if all(x is not None for x in raws):
                tick("clean_eq_raw_sum_15min", abs(sum(x or 0 for x in raws) - cb) < 1e-6)
    return {
        "semantics_checks": {k: f"{m}/{n}" for k, (m, n) in checks.items()},
        "cdaily_at_0000": sorted(
            {r["cdaily"] for r, t in zip(rows, times, strict=True) if t.time() == _T0000}
        ),
        "cdaily_at_0005": sorted(
            {r["cdaily"] for r, t in zip(rows, times, strict=True) if t.time() == _T0005}
        ),
        "raw_nonzero": sum(_is_number(r["raw"]) and float(r["raw"]) > 0 for r in rows),
    }


def _parse_arg_time(text: str) -> datetime:
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)  # noqa: DTZ007 - source-local, no offset
        except ValueError:
            pass
    raise RequestError(f"bad time {text!r}; use YYYY-MM-DD or YYYY-MM-DDTHH:MM")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Probe one small JPS history window.")
    ap.add_argument("sensor", choices=sorted(SENSORS))
    ap.add_argument("station", help="jps_internal_id (graph-link stationid)")
    ap.add_argument("start", help="YYYY-MM-DD[THH:MM], source local time")
    ap.add_argument("end", help="YYYY-MM-DD[THH:MM], source local time")
    ap.add_argument("--datafreq", type=int, choices=(5, 15, 60), default=5)
    ap.add_argument("--allow-wide", action="store_true", help=f"cap {WIDE_MAX_DAYS} days")
    ap.add_argument("--save-raw", type=Path, metavar="DIR")
    ap.add_argument("--json", type=Path, metavar="PATH", help="also write the summary here")
    args = ap.parse_args(argv)

    try:
        start, end = _parse_arg_time(args.start), _parse_arg_time(args.end)
        validate_request(
            args.station, start, end, WIDE_MAX_DAYS if args.allow_wide else DEFAULT_MAX_DAYS
        )
    except RequestError as e:
        print(f"REQUEST REJECTED: {e}", file=sys.stderr)
        return 4
    url = build_url(args.sensor, args.station, start, end, args.datafreq)
    fetched_at = jc.now_myt()
    try:
        text = jc.fetch(url)
        info, rows = parse_history(text, args.sensor)
    except SchemaError as e:
        print(f"SCHEMA CHANGE: {e}", file=sys.stderr)
        return 2
    except OSError as e:  # includes HTTP 403/429: stop, do not retry
        print(f"FETCH FAILED: {e}", file=sys.stderr)
        return 3

    summary = {
        "url": url,
        "fetched_at": fetched_at.isoformat(),
        **summarize(info, rows, args.sensor),
    }
    if args.save_raw:
        stem = f"history_{args.sensor}_{args.station.strip()}_{start:%Y%m%d}-{end:%Y%m%d}"
        summary["raw_file"] = str(jc.save_raw(text, args.save_raw, stem, fetched_at, ".json"))
    out = json.dumps(summary, ensure_ascii=False)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(out + "\n", encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
