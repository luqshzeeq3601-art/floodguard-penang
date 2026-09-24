"""One-shot probe of the METMalaysia weather forecast/warning feeds on the data.gov.my open API.

Discovery only: one request per feed (forecast, warning), no loop, no scheduler, no database.
Source: https://api.data.gov.my/weather/{forecast,warning} (unauthenticated JSON, CC BY 4.0,
documented limit 4 requests/min, data provided by MET Malaysia). Evidence and caveats:
``data/metadata/metmalaysia/ACCESS.md``.

Forecast rows are filtered to the Pulau Pinang location IDs listed in
``data/metadata/metmalaysia/penang_locations.csv``. Source fields are kept verbatim; the source
publishes NO forecast issue time, so ``retrieved_at`` (FloodGuard clock, +08:00) is the only
reference time and is never merged into a source field. Warnings are summarised as published and
are NOT mapped to FloodGuard risk labels.

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\probe_metmalaysia.py forecast
    .venv\\Scripts\\python.exe scripts\\probe_metmalaysia.py all --write-raw
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BASE = "https://api.data.gov.my/weather"
USER_AGENT = "FloodGuard-Penang-discovery/0.1 (research)"
MYT = ZoneInfo("Asia/Kuala_Lumpur")
REPO_ROOT = Path(__file__).resolve().parents[1]
METADATA_DIR = REPO_ROOT / "data" / "metadata" / "metmalaysia"
PENANG_CSV = METADATA_DIR / "penang_locations.csv"
TIMEOUT_S = 60
MAX_ATTEMPTS = 3
REQUEST_DELAY_S = 16.0  # 4 requests/min documented limit -> >= 15 s between requests

LOCATION_ID_RE = re.compile(r"^(St|Ds|Tn|Rc|Dv)\d{3}$")
FORECAST_TEXT_KEYS = (
    "morning_forecast",
    "afternoon_forecast",
    "night_forecast",
    "summary_forecast",
    "summary_when",
)
WARNING_TEXT_KEYS = (
    "heading_en",
    "text_en",
    "instruction_en",
    "heading_bm",
    "text_bm",
    "instruction_bm",
)


class SchemaError(ValueError):
    """Upstream payload no longer matches the verified schema."""


@dataclass(frozen=True)
class ForecastRow:
    location_id: str
    location_name: str
    forecast_date: str  # source `date`, local calendar date, no time or issue time
    texts: dict[str, str]
    min_temp_c: int | None
    max_temp_c: int | None
    retrieved_at: str


@dataclass(frozen=True)
class WarningRecord:
    issued: str  # source naive local time, verbatim
    title_en: str
    valid_from: str | None
    valid_to: str | None
    heading_en: str
    fg_valid_from_before_issued: bool
    fg_mentions_pulau_pinang: bool  # FloodGuard text match on text_en/text_bm, not a source field


def load_penang_ids(path: Path = PENANG_CSV) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as f:
        return {r["location_id"]: r["location_name"] for r in csv.DictReader(f)}


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _naive_iso(v: Any, field: str, *, nullable: bool) -> str | None:
    if v is None and nullable:
        return None
    if not isinstance(v, str):
        raise SchemaError(f"{field}: expected ISO datetime string, got {v!r}")
    try:
        t = datetime.fromisoformat(v)
    except ValueError as e:
        raise SchemaError(f"{field}: unparseable datetime {v!r}") from e
    if t.tzinfo is not None:
        raise SchemaError(f"{field}: offset present ({v!r}); verified schema is naive local time")
    return v


def _as_list(payload: Any, feed: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise SchemaError(f"{feed}: top level is {type(payload).__name__}, expected list")
    if not all(isinstance(r, dict) for r in payload):
        raise SchemaError(f"{feed}: non-object record")
    return payload


def parse_forecast(
    payload: Any, penang_ids: dict[str, str], retrieved_at: datetime
) -> list[ForecastRow]:
    """Validate every record (schema is checked nationally), return only Penang rows."""
    out = []
    for i, r in enumerate(_as_list(payload, "forecast")):
        loc = r.get("location")
        if not isinstance(loc, dict):
            raise SchemaError(f"forecast[{i}]: missing location object")
        lid, name = loc.get("location_id"), loc.get("location_name")
        if not isinstance(lid, str) or not LOCATION_ID_RE.match(lid):
            raise SchemaError(f"forecast[{i}]: bad location_id {lid!r}")
        if not isinstance(name, str):
            raise SchemaError(f"forecast[{i}]: bad location_name {name!r}")
        try:
            date.fromisoformat(r["date"])
        except (KeyError, TypeError, ValueError) as e:
            raise SchemaError(f"forecast[{i}]: bad date {r.get('date')!r}") from e
        for k in FORECAST_TEXT_KEYS:
            if not isinstance(r.get(k), str):
                raise SchemaError(f"forecast[{i}]: {k} missing or not a string")
        for k in ("min_temp", "max_temp"):
            if k not in r or not (r[k] is None or _is_int(r[k])):
                raise SchemaError(f"forecast[{i}]: {k} missing or not an integer/null")
        if lid in penang_ids:
            out.append(
                ForecastRow(
                    location_id=lid,
                    location_name=name,
                    forecast_date=r["date"],
                    texts={k: r[k] for k in FORECAST_TEXT_KEYS},
                    min_temp_c=r["min_temp"],
                    max_temp_c=r["max_temp"],
                    retrieved_at=retrieved_at.isoformat(),
                )
            )
    return sorted(out, key=lambda o: (o.location_id, o.forecast_date))


def parse_warnings(payload: Any) -> list[WarningRecord]:
    out = []
    for i, r in enumerate(_as_list(payload, "warning")):
        issue = r.get("warning_issue")
        if not isinstance(issue, dict):
            raise SchemaError(f"warning[{i}]: missing warning_issue object")
        issued = _naive_iso(issue.get("issued"), f"warning[{i}].issued", nullable=False)
        assert issued is not None
        vf = _naive_iso(r.get("valid_from"), f"warning[{i}].valid_from", nullable=True)
        vt = _naive_iso(r.get("valid_to"), f"warning[{i}].valid_to", nullable=True)
        for k in ("title_en", "title_bm"):
            if not isinstance(issue.get(k), str):
                raise SchemaError(f"warning[{i}]: warning_issue.{k} missing or not a string")
        for k in WARNING_TEXT_KEYS:
            if k not in r or not (r[k] is None or isinstance(r[k], str)):
                raise SchemaError(f"warning[{i}]: {k} missing or not a string/null")
        text = f"{r.get('text_en') or ''} {r.get('text_bm') or ''}"
        out.append(
            WarningRecord(
                issued=issued,
                title_en=issue["title_en"],
                valid_from=vf,
                valid_to=vt,
                heading_en=r.get("heading_en") or "",
                fg_valid_from_before_issued=vf is not None and vf < issued,
                fg_mentions_pulau_pinang=bool(re.search(r"pulau pinang|penang", text, re.I)),
            )
        )
    return out


def fetch(url: str) -> tuple[bytes, dict[str, str], datetime]:
    """GET with bounded retries (network error, 429, 5xx) -> (body, headers, retrieved_at)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, MAX_ATTEMPTS + 1):
        retrieved_at = datetime.now(MYT).replace(microsecond=0)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return resp.read(), dict(resp.headers), retrieved_at
        except urllib.error.HTTPError as e:
            if (e.code != 429 and e.code < 500) or attempt == MAX_ATTEMPTS:
                raise
        except urllib.error.URLError:
            if attempt == MAX_ATTEMPTS:
                raise
        time.sleep(REQUEST_DELAY_S * attempt)
    raise AssertionError("unreachable")


def _raw_name(feed: str, at: datetime) -> str:
    suffix = "_PNG_trimmed" if feed == "forecast" else ""
    return f"{feed}{suffix}_{at.strftime('%Y%m%dT%H%M%S%z')}.json"


def run(feeds: list[str], write_raw: bool) -> int:
    penang = load_penang_ids()
    for n, feed in enumerate(feeds):
        if n:
            time.sleep(REQUEST_DELAY_S)
        url = f"{BASE}/{feed}"
        body, headers, at = fetch(url)
        payload = json.loads(body)
        print(f"{feed}: GET {url} retrieved_at={at.isoformat()} bytes={len(body)}")
        print(f"  Date={headers.get('Date')} Content-Type={headers.get('Content-Type')}")
        if feed == "forecast":
            rows = parse_forecast(payload, penang, at)
            got = {r.location_id for r in rows}
            dates = sorted({r.forecast_date for r in rows})
            print(f"  records={len(payload)} penang_rows={len(rows)} penang_ids={len(got)}")
            print(f"  forecast_dates={dates[0] if dates else None}..{dates[-1] if dates else None}")
            print(f"  missing_penang_ids={sorted(set(penang) - got)} issue_time=NOT_PUBLISHED")
            kept: Any = [r for r in payload if r["location"]["location_id"] in penang]
        else:
            warns = parse_warnings(payload)
            print(f"  records={len(warns)}")
            for w in warns:
                print(
                    f"  issued={w.issued} valid={w.valid_from}..{w.valid_to} "
                    f"title_en={w.title_en!r} mentions_pulau_pinang={w.fg_mentions_pulau_pinang}"
                    f" valid_from_before_issued={w.fg_valid_from_before_issued}"
                )
            kept = payload
        if write_raw:
            out = METADATA_DIR / "raw" / _raw_name(feed, at)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(kept, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"  wrote {out.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("feed", choices=("forecast", "warning", "all"))
    ap.add_argument(
        "--write-raw", action="store_true", help="save Penang-trimmed forecast / full warning JSON"
    )
    args = ap.parse_args(argv)
    feeds = ["forecast", "warning"] if args.feed == "all" else [args.feed]
    try:
        return run(feeds, args.write_raw)
    except SchemaError as e:
        print(f"SCHEMA ERROR: {e}", file=sys.stderr)
        return 2
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"FETCH ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
