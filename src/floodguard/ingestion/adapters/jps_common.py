"""Pure JPS Public Infobanjir parsing primitives shared by the discovery scripts and ingestion.

Moved verbatim from ``scripts/_jps_common.py`` / ``scripts/probe_jps_history.py`` (which re-import
them), plus ``ResultTableParser.row_lines`` for row provenance. No I/O, no network.
"""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

from floodguard.ingestion.contracts import SchemaError

__all__ = [
    "HISTORY_TIME_FORMAT",
    "HISTORY_VALUE_KEYS",
    "MISSING_SENTINEL",
    "NO_DATA_MARKER",
    "NO_RESULT_MARKER",
    "ResultTableParser",
    "SchemaError",
]

MISSING_SENTINEL = "-9999"
NO_DATA_MARKER = "Tiada Data"  # listing body when a filter matches nothing
NO_RESULT_MARKER = "No result"  # history body for ranges without stored data
HISTORY_TIME_FORMAT = "%d/%m/%Y %H:%M"
# Keys every history value row carries (data/metadata/jps/HISTORICAL_AVAILABILITY.md).
HISTORY_VALUE_KEYS: dict[str, tuple[str, ...]] = {
    "rainfall": ("dt", "raw", "clean", "chourly", "cdaily", "tdaily", "cyearly", "c15min"),
    "water_level": ("dt", "clean", "raw", "ecm", "final", "severity"),
}


class ResultTableParser(HTMLParser):
    """Header texts, data rows (split on the ``data-th='No'`` cell) and per-row graph id.

    Rows are delimited by their first cell because the rainfall fragment omits opening
    ``<tr>`` tags. ``link_marker`` selects the graph link (e.g. ``rf-graph``, ``wl-graph``).
    ``row_lines`` holds the 1-based source line of each row's first cell.
    """

    def __init__(self, link_marker: str) -> None:
        super().__init__(convert_charrefs=True)
        self.link_marker = link_marker
        self.headers: list[str] = []
        self.rows: list[list[str]] = []
        self.link_ids: list[str | None] = []
        self.row_lines: list[int] = []
        self._in_th = False
        self._in_td = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "th":
            self._in_th, self._buf = True, []
        elif tag == "td":
            if a.get("data-th") == "No":
                self.rows.append([])
                self.link_ids.append(None)
                self.row_lines.append(self.getpos()[0])
            self._in_td, self._buf = True, []
        elif tag == "a" and self._in_td and self.rows:
            href = a.get("href") or ""
            if self.link_marker in href:
                ids = parse_qs(urlparse(href).query, keep_blank_values=True).get("stationid")
                self.link_ids[-1] = ids[0] if ids else ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "th" and self._in_th:
            self.headers.append(" ".join("".join(self._buf).split()))
            self._in_th = False
        elif tag == "td" and self._in_td:
            if self.rows:
                self.rows[-1].append("".join(self._buf).strip())
            self._in_td = False

    def handle_data(self, data: str) -> None:
        if self._in_th or self._in_td:
            self._buf.append(data)
