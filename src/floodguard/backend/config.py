"""Database configuration from environment (no secrets in code or logs).

- ``FLOODGUARD_DATABASE_URL`` is the only credential path (SQLAlchemy URL).
  Allowed schemes: ``postgresql``, ``postgresql+psycopg`` (production-like),
  ``sqlite`` (tests / local throwaway only).
- Validation happens at startup (:func:`load_config` raises ``ValueError``
  on missing/unsupported URLs).
- Passwords are never logged: :func:`redacted_url` masks them, and the
  config object hides the password in ``repr``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final
from urllib.parse import urlparse

DATABASE_URL_ENV: Final[str] = "FLOODGUARD_DATABASE_URL"
ALLOWED_SCHEMES: Final[tuple[str, ...]] = ("postgresql", "postgresql+psycopg", "sqlite")


@dataclass(frozen=True)
class DatabaseConfig:
    """Validated database configuration (password excluded from repr)."""

    url: str
    echo: bool = False

    def __repr__(self) -> str:
        return f"DatabaseConfig(url={redacted_url(self.url)!r}, echo={self.echo})"

    @property
    def is_postgres(self) -> bool:
        return urlparse(self.url).scheme in ("postgresql", "postgresql+psycopg")

    @property
    def is_sqlite(self) -> bool:
        return urlparse(self.url).scheme == "sqlite"


def redacted_url(url: str) -> str:
    """Mask any password embedded in a database URL."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return "<unparseable-url>"
    if not parsed.password:
        return url
    netloc = parsed.hostname or ""
    if parsed.username:
        netloc = f"{parsed.username}:***@{netloc}"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return parsed._replace(netloc=netloc).geturl()


def load_config(environ: dict[str, str] | None = None) -> DatabaseConfig:
    """Load and validate configuration from the environment mapping."""
    env = environ if environ is not None else dict(os.environ)
    url = (env.get(DATABASE_URL_ENV) or "").strip()
    if not url:
        raise ValueError(f"{DATABASE_URL_ENV} is not set")
    scheme = urlparse(url).scheme
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"unsupported database scheme: {scheme!r}")
    echo = env.get("FLOODGUARD_SQL_ECHO", "").strip().lower() in ("1", "true", "yes")
    return DatabaseConfig(url=url, echo=echo)
