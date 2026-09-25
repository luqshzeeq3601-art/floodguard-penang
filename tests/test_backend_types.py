"""WGS84 point type tests: WKT helpers, WKB parsing, PG bind shape (offline)."""

from __future__ import annotations

import pytest

from floodguard.backend.types import (
    SRID_WGS84,
    Wgs84Point,
    parse_wkb_point,
    parse_wkt_point,
    wkb_point,
    wkt_point,
)

pytestmark = pytest.mark.usefixtures("no_network")


def test_wkt_round_trip() -> None:
    assert wkt_point(100.32, 5.41) == "POINT(100.32 5.41)"
    assert parse_wkt_point("POINT(100.32 5.41)") == (100.32, 5.41)
    with pytest.raises(ValueError, match="not a POINT"):
        parse_wkt_point("LINESTRING(0 0, 1 1)")


def test_wkb_point_round_trip_both_endians() -> None:
    for little_endian in (True, False):
        raw = wkb_point(100.32, 5.41, little_endian=little_endian)
        lon, lat = parse_wkb_point(raw)
        assert lon == pytest.approx(100.32)
        assert lat == pytest.approx(5.41)


def test_ewkb_with_srid_round_trip() -> None:
    raw = wkb_point(100.32, 5.41, srid=SRID_WGS84)
    lon, lat = parse_wkb_point(raw)
    assert lon == pytest.approx(100.32)
    assert lat == pytest.approx(5.41)


def test_wkb_rejects_non_point() -> None:
    with pytest.raises(ValueError, match="too short"):
        parse_wkb_point(b"\x01\x02")
    with pytest.raises(ValueError, match="not a POINT geometry"):
        parse_wkb_point(wkb_point(0.0, 0.0).replace(b"\x01\x00\x00\x00", b"\x02\x00\x00\x00", 1))


def test_postgres_bind_carries_srid() -> None:
    import types as _types

    pg = _types.SimpleNamespace(name="postgresql")
    bound = Wgs84Point().process_bind_param("POINT(100.32 5.41)", pg)
    assert bound is not None
    assert bound.srid == SRID_WGS84
    assert "POINT(100.32 5.41)" in bound.desc


def test_result_value_normalizes_to_wkt() -> None:
    import types as _types

    pg = _types.SimpleNamespace(name="postgresql")
    column = Wgs84Point()
    assert column.process_result_value("POINT(1 2)", pg) == "POINT(1 2)"
    assert column.process_result_value(wkb_point(1.0, 2.0).hex(), pg) == "POINT(1.0 2.0)"
    assert column.process_result_value("\\x" + wkb_point(1.0, 2.0).hex(), pg) == "POINT(1.0 2.0)"
    assert column.process_result_value(None, pg) is None
    with pytest.raises(ValueError, match="cannot decode"):
        column.process_result_value("not-hex!!", pg)
