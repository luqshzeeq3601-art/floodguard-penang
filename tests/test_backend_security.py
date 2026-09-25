"""Backend security tests: config, secrets, parameterization (offline)."""

from __future__ import annotations

import pytest

from floodguard.backend.config import load_config, redacted_url

pytestmark = pytest.mark.usefixtures("no_network")


def test_config_requires_url_and_known_scheme() -> None:
    with pytest.raises(ValueError, match="not set"):
        load_config({})
    with pytest.raises(ValueError, match="unsupported database scheme"):
        load_config({"FLOODGUARD_DATABASE_URL": "mysql://u:p@h/db"})
    config = load_config({"FLOODGUARD_DATABASE_URL": "sqlite:///:memory:"})
    assert config.is_sqlite
    assert not config.is_postgres


def test_password_never_in_repr_or_logs() -> None:
    url = "postgresql+psycopg://floodguard:s3cret-pw@db:5432/floodguard"
    redacted = redacted_url(url)
    assert "s3cret-pw" not in redacted
    assert "***" in redacted
    assert "floodguard" in redacted
    config = load_config({"FLOODGUARD_DATABASE_URL": url})
    assert "s3cret-pw" not in repr(config)
    assert config.is_postgres


def test_env_example_has_placeholders_only() -> None:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "change-me-local-only" in text
    assert "FLOODGUARD_DATABASE_URL=" in text
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if "PASSWORD" in key or "URL" in key:
            assert "change-me" in value or "localhost" in value or value == "", key


def test_no_raw_sql_string_concatenation() -> None:
    import re
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1] / "src" / "floodguard" / "backend"
    # SQL shapes only (error messages mentioning "insert failed" must not match).
    fstring_sql = re.compile(
        r"""f["'].*\b(select\b.*\bfrom|insert\s+into|update\s+\w+\s+set|delete\s+from)\b""",
        re.IGNORECASE,
    )
    dynamic_text = re.compile(r"""text\(\s*(f["']|.*(\+|\.format\(|%))""")
    risky: list[str] = []
    for path in sorted(backend.glob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if fstring_sql.search(line) or dynamic_text.search(line):
                risky.append(f"{path.name}:{lineno}")
    assert risky == []


def test_no_hardcoded_credentials_in_backend() -> None:
    import re
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1] / "src" / "floodguard" / "backend"
    pattern = re.compile(r"""password\s*=\s*["'][^"*]+["']""", re.IGNORECASE)
    hits: list[str] = []
    for path in sorted(backend.glob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if pattern.search(line):
                hits.append(f"{path.name}:{lineno}")
    assert hits == []
