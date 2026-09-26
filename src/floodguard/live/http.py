"""Controlled HTTP client for live polling (Phase 10).

Single HTTP layer: connect/read timeout, User-Agent, bounded response size.
Only configured source endpoints are fetched; arbitrary user-controlled URLs are
rejected (SSRF prevention). Retries cover transient failures only with bounded
attempts and documented backoff; tests inject timing.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from floodguard.ingestion.fetch import (
    USER_AGENT,
    AccessPermission,
    FetchResult,
    PermissionNotGrantedError,
)

# Configured source endpoints only (no arbitrary URLs).
JPS_RAINFALL_LISTING_URL: Final[str] = (
    "https://publicinfobanjir.water.gov.my/wp-content/themes/shapely/agency/"
    "searchresultrainfall.php?state=PNG&district=ALL&station=ALL&loginStatus=0&language=0"
)
JPS_WATER_LEVEL_LISTING_URL: Final[str] = (
    "https://publicinfobanjir.water.gov.my/index.php/aras-air/data-paras-air/"
    "aras-air-data/?state=PNG&district=ALL&station=ALL"
)
DATAGOVMY_FORECAST_URL: Final[str] = "https://api.data.gov.my/weather/forecast"

ALLOWED_URLS: Final[frozenset[str]] = frozenset(
    {JPS_RAINFALL_LISTING_URL, JPS_WATER_LEVEL_LISTING_URL, DATAGOVMY_FORECAST_URL}
)

# Retryable HTTP statuses: rate-limit + transient server errors only.
RETRYABLE_STATUS: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})

SleepFn = Callable[[float], None]


class UrlNotAllowedError(ValueError):
    """URL is not a configured source endpoint."""


class TransientHttpError(OSError):
    """Retryable HTTP status (429/5xx); carries the status for categorization."""

    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"HTTP {status} for {url}")
        self.status = status
        self.url = url


@dataclass(frozen=True)
class HttpConfig:
    timeout_seconds: float = 30.0
    max_response_bytes: int = 2_000_000
    max_retries: int = 3
    backoff_base_seconds: float = 2.0


def check_url_allowed(url: str) -> str:
    """Reject anything that is not a configured source endpoint."""
    if url not in ALLOWED_URLS:
        raise UrlNotAllowedError(f"refusing non-configured URL (SSRF guard): {url!r}")
    return url


def _backoff(attempt: int, base: float) -> float:
    # Documented exponential backoff: base * 2**(attempt-1), attempt is 1-based.
    return base * (2.0 ** (attempt - 1))


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, TransientHttpError):
        return exc.status in RETRYABLE_STATUS
    if isinstance(exc, urllib.error.HTTPError):
        return int(exc.code) in RETRYABLE_STATUS
    # Network-level failures (timeout, refused, reset) are transient.
    name = type(exc).__name__
    return name in ("URLError", "TimeoutError", "ConnectionError") or isinstance(exc, TimeoutError)


@dataclass(frozen=True)
class ControlledFetcher:
    """Permission-gated fetcher with bounded retry (transport injectable)."""

    source: str
    permission: AccessPermission | None
    http: HttpConfig = HttpConfig()

    def _check_permission(self) -> None:
        p = self.permission
        if p is None or p.source != self.source or p.scope != "network_fetch":
            raise PermissionNotGrantedError(
                f"network fetch from {self.source} is disabled: no permission record "
                "(JPS polling is PERMISSION REQUIRED)"
            )

    def fetch(
        self,
        url: str,
        *,
        transport: Callable[[str, float], FetchResult] | None = None,
        sleep: SleepFn | None = None,
    ) -> FetchResult:
        """One URL, bounded retries for transient failures only.

        Permission is checked before any socket use. Permanent failures
        (permission refusal, disallowed URL, non-retryable HTTP, schema issues
        downstream) are never retried by this layer.
        """
        self._check_permission()
        check_url_allowed(url)
        sleeper: SleepFn = sleep or time.sleep
        last_error: Exception | None = None
        attempts = max(self.http.max_retries + 1, 1)
        for attempt in range(1, attempts + 1):
            try:
                if transport is not None:
                    return transport(url, self.http.timeout_seconds)
                return _urllib_get(url, self.http.timeout_seconds, self.http.max_response_bytes)
            except PermissionNotGrantedError:
                raise
            except UrlNotAllowedError:
                raise
            except Exception as exc:
                if not _is_transient(exc):
                    raise
                last_error = exc
                if attempt < attempts:
                    sleeper(_backoff(attempt, self.http.backoff_base_seconds))
        assert last_error is not None
        raise last_error


def _urllib_get(url: str, timeout: float, max_bytes: int) -> FetchResult:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = int(getattr(resp, "status", 200))
            if status != 200:
                if status in RETRYABLE_STATUS:
                    raise TransientHttpError(status, url)
                raise OSError(f"HTTP {status} for {url}")
            body = resp.read(max_bytes + 1)
    except urllib.error.HTTPError:
        raise
    except TimeoutError:
        raise
    except OSError as exc:
        raise urllib.error.URLError(str(exc)) from exc
    if len(body) > max_bytes:
        raise OSError(f"response exceeds {max_bytes} bytes for {url}")
    return FetchResult(bytes(body), 200, datetime.now(UTC))
