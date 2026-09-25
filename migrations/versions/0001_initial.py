"""Initial FloodGuard schema: sites, sensors, thresholds, observations.

Revision ID: 0001_initial (fixed; deterministic history).
Revises: None (first revision).
"""

from __future__ import annotations

from alembic import op

from floodguard.backend.models import SCHEMA_VERSION, Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | list[str] | None = None
depends_on: str | list[str] | None = None

# Pinned contract: this revision creates exactly backend_schema/v1. If models
# move on, add a new revision instead of editing this one; the pin fails
# loudly rather than falsifying history.
PINNED_SCHEMA_VERSION: str = "backend_schema/v1"


def upgrade() -> None:
    """Create the PostGIS extension (PostgreSQL only) and all tables."""
    if SCHEMA_VERSION != PINNED_SCHEMA_VERSION:
        raise RuntimeError(
            f"0001_initial is pinned to {PINNED_SCHEMA_VERSION}; "
            f"models report {SCHEMA_VERSION} — write a new revision"
        )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    Base.metadata.create_all(bind)


def downgrade() -> None:
    """Drop all FloodGuard tables (explicitly destructive; base only)."""
    Base.metadata.drop_all(op.get_bind())
