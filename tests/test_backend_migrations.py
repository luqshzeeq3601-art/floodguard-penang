"""Migration tests: chain linearity, upgrade/downgrade, PG SQL generation (offline)."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.schema import CreateTable

from floodguard.backend.models import Base

pytestmark = pytest.mark.usefixtures("no_network")

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _load_revision(name: str) -> object:
    spec = importlib.util.spec_from_file_location(name, MIGRATIONS_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_chain_is_linear_with_fixed_ids() -> None:
    modules = [_load_revision(path.stem) for path in sorted(MIGRATIONS_DIR.glob("*.py"))]
    assert len(modules) >= 1
    revisions = [m.revision for m in modules]  # type: ignore[attr-defined]
    assert len(set(revisions)) == len(revisions)
    assert revisions[0] == "0001_initial"
    downs = [m.down_revision for m in modules]  # type: ignore[attr-defined]
    assert downs[0] is None
    for module, down in zip(modules[1:], downs[1:], strict=True):
        assert down in revisions
        _ = module


def test_initial_revision_pinned_to_schema_version() -> None:
    module = _load_revision("0001_initial")
    from floodguard.backend.models import SCHEMA_VERSION

    assert module.PINNED_SCHEMA_VERSION == SCHEMA_VERSION  # type: ignore[attr-defined]


def test_migrate_script_guards_downgrade(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "migrate_db_mod", Path(__file__).resolve().parents[1] / "scripts" / "migrate_db.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run_cli: Any = module.main
    url = f"sqlite:///{tmp_path / 'guard.db'}"
    monkeypatch.setenv("FLOODGUARD_DATABASE_URL", url)
    assert run_cli(["--command", "upgrade"]) == 0
    # Downgrade without confirmation is refused and keeps the schema.
    assert run_cli(["--command", "downgrade"]) == 2
    from sqlalchemy import create_engine, inspect

    assert "sites" in inspect(create_engine(url, future=True)).get_table_names()
    assert run_cli(["--command", "downgrade", "--confirm-destructive"]) == 0
    assert "sites" not in inspect(create_engine(url, future=True)).get_table_names()
    # Production environment refuses downgrade outright.
    assert run_cli(["--command", "upgrade"]) == 0
    monkeypatch.setenv("FLOODGUARD_ENV", "production")
    assert run_cli(["--command", "downgrade", "--confirm-destructive"]) == 2


def test_upgrade_head_and_downgrade_base_on_sqlite(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    url = f"sqlite:///{tmp_path / 'mig.db'}"
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR.parent))
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    engine = create_engine(url, future=True)
    tables = set(inspect(engine).get_table_names())
    assert {
        "sites",
        "sensors",
        "sensor_thresholds",
        "observations",
        "predictions",
        "alerts",
        "ingest_batches",
        "alembic_version",
    } <= tables
    command.downgrade(config, "base")
    remaining = set(inspect(create_engine(url, future=True)).get_table_names())
    assert "sites" not in remaining
    assert "observations" not in remaining


def test_postgres_ddl_contains_postgis_and_constraints() -> None:
    from sqlalchemy.dialects.postgresql.base import PGDialect
    from sqlalchemy.schema import CreateIndex

    dialect: Any = PGDialect()  # type: ignore[no-untyped-call]
    sites_ddl = str(CreateTable(Base.metadata.tables["sites"]).compile(dialect=dialect))
    assert "geometry(POINT,4326)" in sites_ddl
    assert "USING gist" in " ".join(
        str(CreateIndex(index).compile(dialect=dialect))
        for index in Base.metadata.tables["sites"].indexes
    )
    obs_ddl = str(CreateTable(Base.metadata.tables["observations"]).compile(dialect=dialect))
    assert "TIMESTAMP WITH TIME ZONE" in obs_ddl
    assert "PRIMARY KEY" in obs_ddl
