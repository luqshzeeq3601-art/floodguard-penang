"""PostGIS-aware column types with unit-test portability.

``Wgs84Point`` stores WGS84 lon/lat points: real PostGIS
``geometry(POINT,4326)`` on PostgreSQL, plain WKT ``TEXT`` elsewhere so the
same models create cleanly on SQLite for offline unit tests (no SpatiaLite
required). Values in Python are WKT strings (``"POINT(lon lat)"``) or
``(lon, lat)`` tuples; the repository layer is the only writer.

On PostgreSQL, binds carry the SRID explicitly (EWKT ``SRID=4326;...`` via
``ST_GeomFromEWKT``), so stored geometries never land as SRID 0 against the
``geometry(POINT,4326)`` typmod. Reads parse 2D POINT WKB/EWKB back to WKT
without third-party geometry libraries.

SRID 4326 is documented as inferred (the JPS feed declares no CRS), matching
``fg_crs_assumption = EPSG:4326 (inferred)`` in the station master.
"""

from __future__ import annotations

import struct
from typing import Any, Final

from geoalchemy2 import WKTElement
from sqlalchemy.types import Text, TypeDecorator

SRID_WGS84: Final[int] = 4326


def wkt_point(lon: float, lat: float) -> str:
    """Render a WKT point (lon first, degrees)."""
    return f"POINT({lon} {lat})"


def parse_wkt_point(wkt: str) -> tuple[float, float]:
    """Parse ``POINT(lon lat)`` back to floats; raises ``ValueError``."""
    text = wkt.strip()
    if not text.startswith("POINT(") or not text.endswith(")"):
        raise ValueError(f"not a POINT WKT: {wkt!r}")
    parts = text[len("POINT(") : -1].split()
    if len(parts) != 2:
        raise ValueError(f"not a POINT WKT: {wkt!r}")
    try:
        return float(parts[0]), float(parts[1])
    except ValueError:
        raise ValueError(f"not a POINT WKT: {wkt!r}") from None


def parse_wkb_point(data: bytes) -> tuple[float, float]:
    """Parse 2D POINT WKB/EWKB bytes to ``(lon, lat)``; raises ``ValueError``."""
    if len(data) < 5:
        raise ValueError("WKB too short for a POINT header")
    endian = ">" if data[0] == 0 else "<" if data[0] == 1 else None
    if endian is None:
        raise ValueError(f"unknown WKB byte order: {data[0]}")
    offset = 1
    geom_type = struct.unpack(endian + "I", data[offset : offset + 4])[0]
    offset += 4
    has_srid = bool(geom_type & 0x80000000)
    geom_type &= ~0x80000000
    if geom_type != 1:
        raise ValueError(f"not a POINT geometry (type {geom_type})")
    if has_srid:
        offset += 4
    if len(data) < offset + 16:
        raise ValueError("WKB too short for POINT coordinates")
    lon = struct.unpack(endian + "d", data[offset : offset + 8])[0]
    lat = struct.unpack(endian + "d", data[offset + 8 : offset + 16])[0]
    return lon, lat


def wkb_point(
    lon: float, lat: float, *, srid: int | None = None, little_endian: bool = True
) -> bytes:
    """Encode 2D POINT WKB (EWKB with SRID when given); test helper."""
    endian: Final[str] = "<" if little_endian else ">"
    order = b"\x01" if little_endian else b"\x00"
    geom_type = 1 | (0x80000000 if srid is not None else 0)
    header = order + struct.pack(endian + "I", geom_type)
    if srid is not None:
        header += struct.pack(endian + "I", srid)
    return header + struct.pack(endian + "d", lon) + struct.pack(endian + "d", lat)


class Wgs84Point(TypeDecorator[str]):
    """WGS84 point: PostGIS geometry on PG, WKT text elsewhere."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            from geoalchemy2 import Geometry

            return Geometry("POINT", srid=SRID_WGS84)
        return Text()

    def process_bind_param(self, value: Any | None, dialect: Any) -> Any | None:
        if value is None:
            return None
        if isinstance(value, (tuple, list)) and len(value) == 2:
            wkt = wkt_point(float(value[0]), float(value[1]))
        elif isinstance(value, str):
            parse_wkt_point(value)  # validate shape early
            wkt = value
        else:
            raise ValueError(f"cannot bind {value!r} as WGS84 point")
        if dialect.name == "postgresql":
            # EWKT carries SRID 4326 so ST_GeomFromEWKT never stores SRID 0.
            return WKTElement(wkt, srid=SRID_WGS84, extended=True)
        return wkt

    def process_result_value(self, value: Any | None, dialect: Any) -> Any | None:
        if value is None:
            return None
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("POINT("):
                return text
            # PostgreSQL hex output may carry a \x/0x prefix; strip it first.
            for prefix in ("\\x", "\\X", "0x", "0X"):
                if text.startswith(prefix):
                    text = text[len(prefix) :]
                    break
            try:
                raw = bytes.fromhex(text)
            except ValueError:
                raise ValueError("cannot decode geometry value") from None
            lon, lat = parse_wkb_point(raw)
            return wkt_point(lon, lat)
        if isinstance(value, (bytes, bytearray)):
            lon, lat = parse_wkb_point(bytes(value))
            return wkt_point(lon, lat)
        desc = getattr(value, "desc", None)  # geoalchemy2 WKTElement
        if isinstance(desc, str):
            return desc
        data = getattr(value, "data", None)  # geoalchemy2 WKBElement
        if isinstance(data, (bytes, bytearray)):
            lon, lat = parse_wkb_point(bytes(data))
            return wkt_point(lon, lat)
        if isinstance(data, str):
            lon, lat = parse_wkb_point(bytes.fromhex(data))
            return wkt_point(lon, lat)
        return str(value)
