"""Dashboard configuration from environment (no secrets, no hardcoding).

- ``FLOODGUARD_API_URL``: FastAPI base URL (e.g. ``http://localhost:8000``).
- ``FLOODGUARD_API_TIMEOUT_SECONDS``: per-request timeout (default 10 s).
- Validation happens at startup; passwords/tokens never appear here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlparse

from floodguard.dashboard import DEFAULT_TIMEOUT_SECONDS

API_URL_ENV: Final[str] = "FLOODGUARD_API_URL"
API_TIMEOUT_ENV: Final[str] = "FLOODGUARD_API_TIMEOUT_SECONDS"
ALLOWED_SCHEMES: Final[tuple[str, ...]] = ("http", "https")


@dataclass(frozen=True)
class DashboardConfig:
    """Validated dashboard configuration (no secrets)."""

    api_base_url: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        scheme = urlparse(self.api_base_url).scheme
        if scheme not in ALLOWED_SCHEMES:
            raise ValueError(f"API URL must be http(s): {self.api_base_url!r}")
        if not self.timeout_seconds > 0:
            raise ValueError("timeout must be positive")


def load_config(environ: dict[str, str] | None = None) -> DashboardConfig:
    """Load dashboard config; missing URL falls back to localhost default."""
    env = environ if environ is not None else dict(os.environ)
    base_url = (env.get(API_URL_ENV) or "http://localhost:8000").strip().rstrip("/")
    timeout_raw = (env.get(API_TIMEOUT_ENV) or "").strip()
    try:
        timeout = float(timeout_raw) if timeout_raw else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        raise ValueError(f"{API_TIMEOUT_ENV} must be a number: {timeout_raw!r}") from None
    return DashboardConfig(api_base_url=base_url, timeout_seconds=timeout)
