"""Shared helpers for the JPS Public Infobanjir discovery scripts (stdlib + floodguard).

Both the rainfall and water-level state views use the same page layout (state/district
``<select>``) and the same result-table conventions (rows start at ``<td data-th='No'>``,
one ``?stationid=`` graph link per row), so fetching, page parsing, table parsing, and the
FloodGuard freshness rule live here once.
"""

from __future__ import annotations

import csv
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# Pure parsing primitives live in the package; re-exported here unchanged.
from floodguard.ingestion.adapters.jps_common import (
    MISSING_SENTINEL,
    NO_DATA_MARKER,
    ResultTableParser,
    SchemaError,
)

__all__ = ["MISSING_SENTINEL", "NO_DATA_MARKER", "ResultTableParser", "SchemaError"]

BASE = "https://publicinfobanjir.water.gov.my"
STATE_CODE = "PNG"
EXPECTED_STATE = "Pulau Pinang"
USER_AGENT = "FloodGuard-Penang-discovery/0.1 (research)"
REQUEST_DELAY_S = 2.0
MYT = ZoneInfo("Asia/Kuala_Lumpur")
REPO_ROOT = Path(__file__).resolve().parents[1]
METADATA_DIR = REPO_ROOT / "data" / "metadata" / "jps"

# FloodGuard-derived freshness rule (NOT a JPS status). Single definition; documented in
# data/metadata/jps/README.md. A row is "stale" when its latest observation is more than
# this many minutes older than the newest observation in the same response.
FG_STALE_AFTER_MINUTES = 180


@dataclass(frozen=True)
class LiveRule:
    """FloodGuard live-freshness rule for one measurement type (provisional; see
    data/metadata/jps/LIVE_ACCESS.md for the evidence behind the numbers)."""

    expected_interval_minutes: int
    allowed_lag_minutes: int
    stale_after_minutes: int


LIVE_RULES = {
    "rainfall": LiveRule(15, 15, FG_STALE_AFTER_MINUTES),
    "water_level": LiveRule(15, 15, FG_STALE_AFTER_MINUTES),
}
# Observation times more than this far after retrieval are treated as INVALID.
FG_FUTURE_TOLERANCE_MINUTES = 5


def fg_age_minutes(observation_time: datetime | None, retrieved_at: datetime) -> int | None:
    """retrieved_at - observation_time in whole minutes (floor).

    ASSUMPTION: the source's naive display time is Asia/Kuala_Lumpur. JPS does not declare a
    timezone; captures are consistent with it (data/metadata/jps/HISTORICAL_AVAILABILITY.md).
    """
    if observation_time is None:
        return None
    delta = retrieved_at - observation_time.replace(tzinfo=MYT)
    return int(delta.total_seconds() // 60)


def fg_live_status(age_minutes: int | None, value_ok: bool, rule: LiveRule) -> str:
    """FRESH / DELAYED / STALE / NO_DATA / INVALID (FloodGuard-derived, not a JPS status)."""
    if age_minutes is None or age_minutes < -FG_FUTURE_TOLERANCE_MINUTES:
        return "INVALID"
    if not value_ok:
        return "NO_DATA"
    if age_minutes <= rule.expected_interval_minutes + rule.allowed_lag_minutes:
        return "FRESH"
    if age_minutes <= rule.stale_after_minutes:
        return "DELAYED"
    return "STALE"


@dataclass(frozen=True)
class StatePage:
    state_label: str
    districts: tuple[str, ...]
    page_last_updated: str | None


class _StatePageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.state_label: str | None = None
        self.districts: list[str] = []
        self._select: str | None = None
        self._option: dict[str, str | None] | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "select":
            self._select = a.get("id")
        elif tag == "option" and self._select in ("state", "district"):
            self._option, self._buf = a, []

    def handle_endtag(self, tag: str) -> None:
        if tag == "select":
            self._select = None
        elif tag == "option" and self._option is not None:
            text = "".join(self._buf).strip()
            if self._select == "state" and "selected" in self._option:
                self.state_label = text
            elif self._select == "district" and self._option.get("value") not in (None, "", "ALL"):
                self.districts.append(self._option.get("value") or "")
            self._option = None

    def handle_data(self, data: str) -> None:
        if self._option is not None:
            self._buf.append(data)


def parse_state_page(html: str) -> StatePage:
    """Selected state label, official district list and footer time from a state view page."""
    p = _StatePageParser()
    p.feed(html)
    if p.state_label is None or not p.districts:
        raise SchemaError("state page: selected state or district <select> options not found")
    m = re.search(r"Kemaskini Terakhir:\s*([0-9/]+ [0-9:]+)", html)
    return StatePage(p.state_label, tuple(p.districts), m.group(1) if m else None)


def parse_result_table(
    html: str,
    page: StatePage,
    *,
    link_marker: str,
    required_headers: tuple[str, ...],
    cells_per_row: int,
    district_col: int,
) -> tuple[list[list[str]], list[str]]:
    """Validate the common table contract; return (rows, jps_internal_ids)."""
    p = ResultTableParser(link_marker)
    p.feed(html)
    missing = [h for h in required_headers if not any(h in x for x in p.headers)]
    if missing:
        raise SchemaError(f"result table: expected headers not found: {missing}")
    if not p.rows:
        if NO_DATA_MARKER in html:  # observed reply for unknown state/station filters
            raise SchemaError(f"result table: source returned '{NO_DATA_MARKER}' (no stations)")
        raise SchemaError("result table: no station rows found")
    if page.state_label != EXPECTED_STATE:
        raise SchemaError(f"state page selected {page.state_label!r}, expected {EXPECTED_STATE!r}")
    ids: list[str] = []
    for i, (row, link_id) in enumerate(zip(p.rows, p.link_ids, strict=True), 1):
        if len(row) != cells_per_row:
            raise SchemaError(f"row {i}: {len(row)} cells, expected {cells_per_row}")
        if not row[2]:
            raise SchemaError(f"row {i}: empty station name")
        if row[district_col] not in page.districts:
            raise SchemaError(f"row {i}: district {row[district_col]!r} not in official list")
        if not link_id:
            raise SchemaError(f"row {i}: {link_marker} stationid link missing")
        ids.append(link_id)
    dup = sorted(k for k, n in Counter(ids).items() if n > 1)
    if dup:
        raise SchemaError(f"duplicate {link_marker} station ids: {dup}")
    return p.rows, ids


def parse_source_time(text: str, fmt: str, row: int) -> datetime:
    """Parse a JPS display time. Naive on purpose: the source declares no timezone."""
    try:
        return datetime.strptime(text, fmt)  # noqa: DTZ007
    except ValueError as e:
        raise SchemaError(f"row {row}: unparseable time {text!r}") from e


def fg_freshness(times: list[datetime]) -> list[tuple[int, str]]:
    """(minutes behind newest row in the response, 'reporting' | 'stale') per row."""
    newest = max(times)
    out = []
    for t in times:
        minutes = int((newest - t).total_seconds() // 60)
        out.append((minutes, "stale" if minutes > FG_STALE_AFTER_MINUTES else "reporting"))
    return out


def fg_display_id_flags(display_ids: list[str]) -> list[str]:
    counts = Counter(display_ids)

    def flag(s: str) -> str:
        if not s:
            return "missing"
        if s.lower() == "no data":
            return "no_data_text"
        return "duplicate" if counts[s] > 1 else "ok"

    return [flag(s) for s in display_ids]


def now_myt() -> datetime:
    return datetime.now(UTC).astimezone(MYT).replace(microsecond=0)


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: str


def fetch_response(url: str, extra_headers: dict[str, str] | None = None) -> HttpResponse:
    """One polite GET that returns status/headers/body for any HTTP status (incl. 304/4xx)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(extra_headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, headers, body = resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        status, headers, body = e.code, dict(e.headers), e.read()
    finally:
        time.sleep(REQUEST_DELAY_S)
    return HttpResponse(status, headers, body.decode("utf-8"))


def fetch(url: str) -> str:
    r = fetch_response(url)
    if r.status != 200:
        raise OSError(f"HTTP {r.status} for {url}")
    return r.body


def write_csv(records: list[Any], columns: tuple[str, ...], path: Path) -> None:
    """Write dataclass records in the given column order (caller sorts)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows(asdict(r) for r in records)


def save_raw(html: str, raw_dir: Path, stem: str, at: datetime, suffix: str = ".html") -> Path:
    path = raw_dir / f"{stem}_{STATE_CODE}_{at:%Y%m%dT%H%M%S%z}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8", newline="")  # no newline translation: as received
    return path
