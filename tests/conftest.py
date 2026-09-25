"""Shared fixtures for the raw-ingestion tests (offline only)."""

from __future__ import annotations

import csv
import socket
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import pytest

from floodguard.station_master import SCHEMA_VERSION, SOURCE_JPS, SensorType, sensor_id, site_id


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any attempt to resolve a host or open a socket connection."""

    def refuse(*_: Any, **__: Any) -> Any:
        raise AssertionError("network access attempted in an offline test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


SensorsCsv = Callable[[Iterable[tuple[str, SensorType]]], Path]


@pytest.fixture
def make_sensors_csv(tmp_path: Path) -> SensorsCsv:
    """SYNTHETIC station-master ``sensors.csv`` for chosen source IDs, IDs derived by the real
    ``station_master.sensor_id``/``site_id`` rules (only the columns the mapper reads; every
    ID gets its canonical site, i.e. all shared IDs are merged)."""

    def make(entries: Iterable[tuple[str, SensorType]]) -> Path:
        path = tmp_path / "sensors.csv"
        rows = [
            [
                sensor_id(SOURCE_JPS, raw.strip(), st),
                site_id(SOURCE_JPS, raw.strip()),
                st.value,
                SOURCE_JPS,
                raw,
                SCHEMA_VERSION,
            ]
            for raw, st in entries
        ]
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(
                [
                    "fg_sensor_id",
                    "fg_site_id",
                    "sensor_type",
                    "source",
                    "jps_internal_id",
                    "fg_schema_version",
                ]
            )
            w.writerows(rows)
        return path

    return make
