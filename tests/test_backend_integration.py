"""Live PostgreSQL/PostGIS integration tests (require a real server).

Skipped unless ``FLOODGUARD_TEST_DATABASE_URL`` points at an isolated,
reachable PostgreSQL database. Never touches the development database:
the URL must name a database containing ``test`` (case-insensitive).

Covers: extension availability, geometry storage, SRID, spatial index, a
representative bounding-box query, and migration round-trip on the live
server. Docker remains BLOCKED in this environment, so these skip here.
"""

from __future__ import annotations

import os
import socket

import pytest
from sqlalchemy import create_engine, inspect, text

pytestmark = [pytest.mark.usefixtures("no_network"), pytest.mark.integration]


def _test_url() -> str | None:
    url = os.environ.get("FLOODGUARD_TEST_DATABASE_URL", "").strip()
    if not url or "test" not in url.lower():
        return None
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        socket.create_connection(
            (parsed.hostname or "localhost", parsed.port or 5432), timeout=2
        ).close()
    except OSError:
        return None
    return url


TEST_URL = _test_url()
requires_postgres = pytest.mark.skipif(TEST_URL is None, reason="no reachable test PostgreSQL")


@requires_postgres
def test_postgis_extension_and_migrations() -> None:
    assert TEST_URL is not None
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    migrations = Path(__file__).resolve().parents[1] / "migrations"
    config = Config()
    config.set_main_option("script_location", str(migrations))
    config.set_main_option("sqlalchemy.url", TEST_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(TEST_URL, future=True)
    try:
        with engine.connect() as connection:
            version = connection.execute(text("SELECT PostGIS_version()")).scalar()
            assert version
            tables = set(inspect(engine).get_table_names())
            assert {"sites", "observations", "predictions"} <= tables
    finally:
        command.downgrade(config, "base")
        engine.dispose()


@requires_postgres
def test_geometry_storage_srid_and_bbox() -> None:
    assert TEST_URL is not None
    from sqlalchemy.orm import Session, sessionmaker
    from tests.backend_helpers import make_site

    from floodguard.backend.models import Site

    engine = create_engine(TEST_URL, future=True)
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    migrations = Path(__file__).resolve().parents[1] / "migrations"
    config = Config()
    config.set_main_option("script_location", str(migrations))
    config.set_main_option("sqlalchemy.url", TEST_URL)
    command.upgrade(config, "head")
    try:
        session = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)()
        session.add(make_site())
        session.commit()
        srid = session.execute(
            text("SELECT ST_SRID(geom) FROM sites WHERE fg_site_id = 'site-001'")
        ).scalar()
        assert srid is not None and int(str(srid)) == 4326
        count = session.execute(
            text("SELECT COUNT(*) FROM sites WHERE geom && ST_MakeEnvelope(100, 5, 101, 6, 4326)")
        ).scalar()
        assert count is not None and int(str(count)) == 1
        assert session.query(Site).count() == 1
        session.close()
    finally:
        command.downgrade(config, "base")
        engine.dispose()
