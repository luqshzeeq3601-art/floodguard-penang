"""Dashboard client tests: typed states for every backend condition (offline)."""

from __future__ import annotations

import pytest

from floodguard.dashboard.client import (
    RESULT_EMPTY,
    RESULT_INVALID,
    RESULT_MALFORMED,
    RESULT_NOT_FOUND,
    RESULT_OK,
    RESULT_SERVER,
    RESULT_UNAVAILABLE,
    DashboardClient,
)

pytestmark = pytest.mark.usefixtures("no_network")


class FakeResponse:
    def __init__(self, status_code: int, payload: object = None, broken: bool = False) -> None:
        self.status_code = status_code
        self._payload = payload
        self._broken = broken

    def json(self) -> object:
        if self._broken:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self._response = response
        self.closed = False
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(
        self, url: str, params: dict[str, object] | None = None, timeout: float = 10.0
    ) -> FakeResponse:
        _ = timeout
        self.calls.append((url, params or {}))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    def close(self) -> None:
        self.closed = True


class TimeoutError(Exception):
    pass


def _client(response: FakeResponse | Exception) -> tuple[DashboardClient, FakeSession]:
    session = FakeSession(response)
    return DashboardClient("http://api:8000", 5.0, session_factory=lambda: session), session


def test_success_and_empty_states() -> None:
    client, session = _client(FakeResponse(200, [{"a": 1}]))
    result = client.list_stations()
    assert result.state == RESULT_OK
    assert result.succeeded
    assert session.closed
    assert result.data == [{"a": 1}]
    assert "/api/v1/stations" in session.calls[0][0]

    empty_client, _ = _client(FakeResponse(200, []))
    assert empty_client.list_stations().state == RESULT_EMPTY
    dict_client, _ = _client(FakeResponse(200, {"items": []}))
    assert (
        dict_client.list_observations(
            sensor_id="s", measurement_type="m", start_utc="a", end_utc="b"
        ).state
        == RESULT_EMPTY
    )


def test_unavailable_on_connection_error_and_timeout() -> None:
    client, _ = _client(ConnectionError("refused"))
    assert client.get_health().state == RESULT_UNAVAILABLE
    timeout_client, _ = _client(TimeoutError("slow"))
    assert timeout_client.get_ready().state == RESULT_UNAVAILABLE


def test_not_found_invalid_server_states() -> None:
    not_found, _ = _client(FakeResponse(404, {}))
    assert not_found.get_station("x").state == RESULT_NOT_FOUND
    invalid, _ = _client(FakeResponse(422, {}))
    assert invalid.list_stations().state == RESULT_INVALID
    server, _ = _client(FakeResponse(500, {}))
    assert server.list_alerts(sensor_id="s").state == RESULT_SERVER
    odd, _ = _client(FakeResponse(302, {}))
    assert odd.get_health().state == RESULT_SERVER


def test_malformed_body_and_shape() -> None:
    broken, _ = _client(FakeResponse(200, None, broken=True))
    assert broken.get_health().state == RESULT_MALFORMED
    wrong_shape, _ = _client(FakeResponse(200, {"a": 1}))
    assert wrong_shape.list_stations().state == RESULT_MALFORMED
    missing_items, _ = _client(FakeResponse(200, {"count": 0}))
    assert (
        missing_items.list_observations(
            sensor_id="s", measurement_type="m", start_utc="a", end_utc="b"
        ).state
        == RESULT_MALFORMED
    )


def test_predictions_and_model_endpoints() -> None:
    predictions, _ = _client(FakeResponse(200, [{"horizon_minutes": 30}]))
    result = predictions.list_predictions(sensor_id="s", horizon_minutes=30)
    assert result.state == RESULT_OK
    assert result.data[0]["horizon_minutes"] == 30
    model, _ = _client(FakeResponse(200, {"status": "NO_ELIGIBLE_MODEL"}))
    assert model.get_model_info().data["status"] == "NO_ELIGIBLE_MODEL"
