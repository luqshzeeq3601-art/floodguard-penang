"""Live monitoring API tests (Phase 10, Task 2 endpoint; offline SQLite)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from floodguard.backend.api import create_app
from floodguard.dashboard.client import DashboardClient
from tests.backend_helpers import make_sensor, make_site, make_threshold

pytestmark = [
    pytest.mark.filterwarnings("ignore::DeprecationWarning"),
    pytest.mark.usefixtures("loopback_only"),
]


def _client(metrics: dict[str, object] | None = None) -> TestClient:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from floodguard.backend.models import Base

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
    seed = factory()
    seed.add(make_site())
    seed.add(make_sensor())
    seed.add(make_threshold())
    seed.commit()
    seed.close()
    provider = (lambda: dict(metrics or {})) if metrics is not None else None
    return TestClient(create_app(factory, ingestion_metrics_provider=provider))


def test_monitoring_endpoint_reports_factual_metrics() -> None:
    client = _client(
        {
            "poll_attempts": 4,
            "successful_polls": 3,
            "failed_polls": 1,
            "records_received": 40,
            "canonical_records_inserted": 30,
        }
    )
    response = client.get("/api/v1/monitoring/ingestion")
    assert response.status_code == 200
    body = response.json()
    assert body["poll_attempts"] == 4
    assert body["canonical_records_inserted"] == 30
    assert "no freshness" in body["notice"].lower()
    assert "healthy" not in str(body).lower()


def test_monitoring_endpoint_without_provider_is_empty_not_error() -> None:
    response = _client().get("/api/v1/monitoring/ingestion")
    assert response.status_code == 200
    assert response.json()["poll_attempts"] == 0


def test_dashboard_client_reads_monitoring() -> None:
    from floodguard.dashboard.client import RESULT_OK

    seen: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> object:
            return {"poll_attempts": 2, "successful_polls": 2}

    class FakeSession:
        def get(self, url: str, params: object = None, timeout: object = None) -> FakeResponse:
            seen["url"] = url
            return FakeResponse()

        def close(self) -> None:
            pass

    client = DashboardClient("http://localhost:8000", session_factory=FakeSession)
    result = client.get_ingestion_metrics()
    assert result.state == RESULT_OK
    assert result.data["poll_attempts"] == 2
    assert str(seen["url"]).endswith("/api/v1/monitoring/ingestion")
