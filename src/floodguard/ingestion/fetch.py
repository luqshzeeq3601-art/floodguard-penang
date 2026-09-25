"""Permission-aware network fetch boundary for raw ingestion.

Every network read goes through ``PermissionedFetcher``, which refuses unless it holds an
``AccessPermission`` for that source. JPS Public Infobanjir is PERMISSION REQUIRED
(docs/DATA_LICENSING_AND_ACCESS.md) and no permission record exists, so JPS fetching is disabled:
``load_permission`` returns a record only from an explicit local JSON file (never committed; e.g.
``data/local/permissions/jps.json``) and the CLI exposes no JPS fetch option at all. The
data.gov.my Weather API is open (CC BY 4.0, 4 requests/min), so ``OPEN_DATA_GOV_MY`` is built in;
it is used only by the explicit ``--fetch`` CLI flag, one request per run.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

USER_AGENT = "FloodGuard-Penang-ingestion/0.1 (research)"
TIMEOUT_S = 60
PERMISSION_FIELDS = ("source", "scope", "granted_by", "reference", "granted_on")


class PermissionNotGrantedError(PermissionError):
    """Network retrieval from this source has no recorded permission."""


@dataclass(frozen=True)
class AccessPermission:
    source: str
    scope: str  # must be "network_fetch"
    granted_by: str
    reference: str  # e.g. licence URL or the publisher's written reply reference
    granted_on: str


OPEN_DATA_GOV_MY = AccessPermission(
    source="DATA_GOV_MY_WEATHER_API",
    scope="network_fetch",
    granted_by="data.gov.my open-data licence",
    reference="CC BY 4.0, developer.data.gov.my/faq (checked 2026-09-24)",
    granted_on="2026-09-24",
)


def load_permission(path: Path) -> AccessPermission | None:
    """Explicit permission record from a local JSON file; None when the file does not exist."""
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or any(not isinstance(doc.get(k), str) for k in PERMISSION_FIELDS):
        raise ValueError(f"{path}: permission record needs string fields {PERMISSION_FIELDS}")
    return AccessPermission(**{k: doc[k] for k in PERMISSION_FIELDS})


@dataclass(frozen=True)
class FetchResult:
    body: bytes
    status: int
    retrieved_at: datetime  # tz-aware UTC, taken when the response body was received


class PermissionedFetcher:
    def __init__(self, source: str, permission: AccessPermission | None) -> None:
        self.source = source
        self.permission = permission

    def check(self) -> AccessPermission:
        p = self.permission
        if p is None or p.source != self.source or p.scope != "network_fetch":
            raise PermissionNotGrantedError(
                f"network fetch from {self.source} is disabled: no permission record "
                "(see docs/RAW_INGESTION_DESIGN.md, 'Permission boundary')"
            )
        return p

    def fetch(self, url: str) -> FetchResult:
        """One GET, no retries. Raises ``PermissionNotGrantedError`` before any socket use."""
        self.check()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = resp.read()
            status = resp.status
        if status != 200:
            raise OSError(f"HTTP {status} for {url}")
        return FetchResult(body, status, datetime.now(UTC))
