"""Apply FloodGuard database migrations in ONE offline run: print JSON, exit.

Reads ``FLOODGUARD_DATABASE_URL`` via ``backend.config`` (validated; password
never printed). Commands: ``upgrade`` (to head), ``downgrade`` (to base),
``current`` (applied revisions). Works against PostgreSQL/PostGIS and SQLite
(PostGIS steps are PostgreSQL-only). Requires no Docker by itself — it
connects to whatever URL is configured.

Usage (repo root):
    .\\.venv\\Scripts\\python.exe scripts\\migrate_db.py --command upgrade

Exit codes: 0 done, 2 rejected (bad config/command or migration failure).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def _alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _heads(config: Config) -> list[str]:
    return ScriptDirectory.from_config(config).get_heads()


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Apply FloodGuard DB migrations (offline).")
    ap.add_argument("--command", choices=("upgrade", "downgrade", "current"), required=True)
    ap.add_argument(
        "--confirm-destructive",
        action="store_true",
        help="required for downgrade (drops all FloodGuard tables)",
    )
    args = ap.parse_args(argv)

    from floodguard.backend.config import load_config, redacted_url

    try:
        db_config = load_config()
    except ValueError as exc:
        print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if args.command == "downgrade":
        import os

        if os.environ.get("FLOODGUARD_ENV", "").strip().lower() == "production":
            print("REJECTED: refusing downgrade with FLOODGUARD_ENV=production.", file=sys.stderr)
            return 2
        if not args.confirm_destructive:
            print(
                "REJECTED: downgrade drops all tables; re-run with --confirm-destructive.",
                file=sys.stderr,
            )
            return 2

    config = _alembic_config(db_config.url)
    report: dict[str, Any] = {
        "database": redacted_url(db_config.url),
        "command": args.command,
    }
    try:
        report["heads"] = _heads(config)
        if args.command == "upgrade":
            command.upgrade(config, "head")
            report["status"] = "UPGRADED"
        elif args.command == "downgrade":
            command.downgrade(config, "base")
            report["status"] = "DOWNGRADED"
        else:
            from alembic.runtime.migration import MigrationContext
            from sqlalchemy import create_engine

            engine = create_engine(db_config.url, future=True)
            try:
                with engine.connect() as connection:
                    context = MigrationContext.configure(connection)
                    report["current"] = list(context.get_current_heads())
            finally:
                engine.dispose()
            report["status"] = "CURRENT"
    except Exception as exc:
        # Type only: driver messages can echo connection details.
        print(f"REJECTED: {type(exc).__name__} during {args.command}.", file=sys.stderr)
        return 2
    report["heads_after"] = _heads(config)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
