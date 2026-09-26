"""Environment configuration for live ingestion (Phase 10).

Safe defaults keep real JPS polling OFF. Actual permitted frequency must follow
JPS authorization/source constraints; the provisional 5-minute assumption is not
a production rule. Interval is configurable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

DEFAULT_POLL_INTERVAL_SECONDS: Final[float] = 300.0
MIN_POLL_INTERVAL_SECONDS: Final[float] = 60.0
DEFAULT_HTTP_TIMEOUT_SECONDS: Final[float] = 30.0
DEFAULT_MAX_RETRIES: Final[int] = 3
DEFAULT_MAX_RESPONSE_BYTES: Final[int] = 2_000_000

ENV_JPS_ENABLED: Final[str] = "FLOODGUARD_LIVE_JPS_ENABLED"
ENV_DATAGOVMY_ENABLED: Final[str] = "FLOODGUARD_LIVE_DATAGOVMY_ENABLED"
ENV_POLL_INTERVAL: Final[str] = "FLOODGUARD_LIVE_POLL_INTERVAL_SECONDS"
ENV_HTTP_TIMEOUT: Final[str] = "FLOODGUARD_LIVE_HTTP_TIMEOUT_SECONDS"
ENV_MAX_RETRIES: Final[str] = "FLOODGUARD_LIVE_MAX_RETRIES"
ENV_RAW_ROOT: Final[str] = "FLOODGUARD_LIVE_RAW_ROOT"
ENV_PERMISSION_FILE: Final[str] = "FLOODGUARD_LIVE_PERMISSION_FILE"
ENV_RUN_STORE: Final[str] = "FLOODGUARD_LIVE_RUN_STORE"


def _truthy(text: str) -> bool:
    return text.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class LiveIngestionConfig:
    """Validated live-ingestion settings (no secrets, no URLs)."""

    jps_enabled: bool = False
    datagovmy_enabled: bool = False
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS
    http_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    raw_root: Path = Path("data/live/raw")
    permission_file: Path = Path("data/local/permissions/jps.json")
    run_store: Path = Path("data/live/runs.jsonl")

    def __post_init__(self) -> None:
        if not self.poll_interval_seconds >= MIN_POLL_INTERVAL_SECONDS:
            raise ValueError(
                f"poll interval must be >= {MIN_POLL_INTERVAL_SECONDS}s "
                "(no busy-loop; permitted frequency follows JPS authorization)"
            )
        if not self.http_timeout_seconds > 0:
            raise ValueError("HTTP timeout must be positive")
        if not 0 <= self.max_retries <= 5:
            raise ValueError("max retries must be 0..5")
        if not self.max_response_bytes > 0:
            raise ValueError("max response bytes must be positive")


def load_config(environ: dict[str, str] | None = None) -> LiveIngestionConfig:
    """Load live-ingestion config; JPS stays OFF unless explicitly enabled."""
    env = environ if environ is not None else dict(os.environ)
    interval_raw = (env.get(ENV_POLL_INTERVAL) or "").strip()
    timeout_raw = (env.get(ENV_HTTP_TIMEOUT) or "").strip()
    retries_raw = (env.get(ENV_MAX_RETRIES) or "").strip()
    try:
        interval = float(interval_raw) if interval_raw else DEFAULT_POLL_INTERVAL_SECONDS
    except ValueError:
        raise ValueError(f"{ENV_POLL_INTERVAL} must be a number: {interval_raw!r}") from None
    try:
        timeout = float(timeout_raw) if timeout_raw else DEFAULT_HTTP_TIMEOUT_SECONDS
    except ValueError:
        raise ValueError(f"{ENV_HTTP_TIMEOUT} must be a number: {timeout_raw!r}") from None
    try:
        retries = int(retries_raw) if retries_raw else DEFAULT_MAX_RETRIES
    except ValueError:
        raise ValueError(f"{ENV_MAX_RETRIES} must be an integer: {retries_raw!r}") from None
    raw_root = Path(env.get(ENV_RAW_ROOT, "data/live/raw"))
    permission_file = Path(env.get(ENV_PERMISSION_FILE, "data/local/permissions/jps.json"))
    run_store = Path(env.get(ENV_RUN_STORE, "data/live/runs.jsonl"))
    return LiveIngestionConfig(
        jps_enabled=_truthy(env.get(ENV_JPS_ENABLED, "0")),
        datagovmy_enabled=_truthy(env.get(ENV_DATAGOVMY_ENABLED, "0")),
        poll_interval_seconds=interval,
        http_timeout_seconds=timeout,
        max_retries=retries,
        raw_root=raw_root,
        permission_file=permission_file,
        run_store=run_store,
    )
