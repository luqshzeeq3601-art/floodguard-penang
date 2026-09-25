"""Alembic environment for FloodGuard Penang (Phase 8 migrations task).

Runs offline against any SQLAlchemy URL. PostgreSQL-only operations (the
PostGIS extension) execute exclusively on PostgreSQL connections; SQLite
runs skip them. Revisions are hand-written with fixed identifiers
(``0001_...``) so migration history is deterministic.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from floodguard.backend.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit migration SQL without connecting (``--sql`` mode)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations to the configured database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
