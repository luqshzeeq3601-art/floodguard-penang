"""One-shot probe of the two structured GIS sources verified for FloodGuard Penang.

Discovery only: no loop, no scheduler, no database, no geometry download, no CRS transformation.
Evidence and caveats: ``data/metadata/gis/GIS_FLOOD_DATASETS.md``.

``stations``
    One GET of the JPS Public Infobanjir map feed ``latestreadingstrendabc.json`` (national,
    ~1.3 MB, the file the official /main/ Leaflet map reads). Joins its ``a`` key to the
    ``jps_internal_id`` of the two committed Penang inventories and writes the officially
    published coordinates verbatim (strings, never rounded or reprojected) to
    ``data/metadata/gis/penang_station_coordinates_jps.csv``. The feed declares no CRS; the page
    passes ``[c, d]`` to ``L.marker`` (Leaflet lat/lng), so WGS84 lat/lon is inferred, not declared.

``flood-history``
    Penang GeoHub (pegis.penang.gov.my, ArcGIS Enterprise) hosted service ``Sejarah_Banjir``:
    one ``/layers`` request (schemas), one count request, then one ``groupBy tarikh`` statistics
    request per layer that has a ``tarikh`` field. Only counts and date distributions are read
    (``returnGeometry`` is never requested).
    Writes ``data/metadata/gis/pegis_sejarah_banjir_layers.csv``.
    Date fields are ArcGIS epoch-ms values; they are reported as the UTC calendar date of the value
    (all observed values are 00:00 UTC), no timezone is asserted for the flood itself.

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\probe_gis_sources.py stations
    .venv\\Scripts\\python.exe scripts\\probe_gis_sources.py flood-history
Exit codes: 0 ok, 2 schema change, 3 network/HTTP failure.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

USER_AGENT = "FloodGuard-Penang-discovery/0.1 (research)"
MYT = ZoneInfo("Asia/Kuala_Lumpur")
REPO_ROOT = Path(__file__).resolve().parents[1]
JPS_DIR = REPO_ROOT / "data" / "metadata" / "jps"
GIS_DIR = REPO_ROOT / "data" / "metadata" / "gis"
RF_CSV = JPS_DIR / "penang_rainfall_stations.csv"
WL_CSV = JPS_DIR / "penang_water_level_stations.csv"
STATIONS_OUT = GIS_DIR / "penang_station_coordinates_jps.csv"
LAYERS_OUT = GIS_DIR / "pegis_sejarah_banjir_layers.csv"

JPS_FEED_URL = (
    "https://publicinfobanjir.water.gov.my/wp-content/themes/enlighten/data/"
    "latestreadingstrendabc.json"
)
PEGIS_SERVICE_URL = (
    "https://pegis.penang.gov.my/arcgis/rest/services/Hosted/Sejarah_Banjir/FeatureServer"
)
TIMEOUT_S = 60
MAX_ATTEMPTS = 3
REQUEST_DELAY_S = 5.0

# Verified keys of a feed record (field meanings are undocumented; only these are used).
JPS_REQUIRED_KEYS = ("a", "b", "c", "d", "e", "f", "g", "h", "i")
PENANG_STATE = "PULAU PINANG"
# Loose sanity box around Pulau Pinang (incl. Seberang Perai); a check, never a transformation.
PENANG_LAT = (5.0, 5.8)
PENANG_LON = (100.0, 100.7)
# Source typo tolerated: layer 7 is published as "Kawasan Banjr Tahun 1999".
LAYER_NAME_RE = re.compile(r"^(Lokasi|Kawasan) Banj(?:i)?r Tahun (\d{4})$")
GEOMETRY_TYPES = {"esriGeometryPoint", "esriGeometryPolygon"}

STATION_COLUMNS = (
    "jps_internal_id",
    "in_rainfall_inventory",
    "in_water_level_inventory",
    "source_station_name",
    "source_state",
    "source_district",
    "source_main_basin",
    "source_sub_basin",
    "source_sensor_types",
    "latitude",
    "longitude",
    "coordinate_crs_note",
    "source_url",
    "source_last_modified",
    "retrieved_at",
)
CRS_NOTE = "not declared; WGS84 lat/lon inferred from official Leaflet L.marker([c,d])"
LAYER_COLUMNS = (
    "layer_id",
    "layer_name",
    "fg_year_from_name",
    "geometry_type",
    "feature_count",
    "tarikh_field_type",
    "fg_dated_count",
    "fg_undated_count",
    "fg_distinct_dates",
    "fg_min_date",
    "fg_max_date",
    "source_url",
    "retrieved_at",
)


class SchemaError(ValueError):
    """Upstream payload no longer matches the verified schema."""


Fetcher = Callable[[str], tuple[bytes, dict[str, str], datetime]]


def fetch(url: str) -> tuple[bytes, dict[str, str], datetime]:
    """GET with bounded retries (network error, 429, 5xx) -> (body, headers, retrieved_at)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, MAX_ATTEMPTS + 1):
        retrieved_at = datetime.now(MYT).replace(microsecond=0)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                return resp.read(), dict(resp.headers), retrieved_at
        except urllib.error.HTTPError as e:
            if (e.code != 429 and e.code < 500) or attempt == MAX_ATTEMPTS:
                raise
        except urllib.error.URLError:
            if attempt == MAX_ATTEMPTS:
                raise
        time.sleep(REQUEST_DELAY_S * attempt)
    raise AssertionError("unreachable")


def load_inventory_ids(path: Path) -> list[str]:
    """``jps_internal_id`` values verbatim (one rainfall ID carries a leading space)."""
    with path.open(encoding="utf-8", newline="") as f:
        return [r["jps_internal_id"] for r in csv.DictReader(f)]


def _in_range(text: str, bounds: tuple[float, float], field: str, sid: str) -> None:
    try:
        v = float(text)
    except ValueError as e:
        raise SchemaError(f"station {sid!r}: {field} {text!r} is not numeric") from e
    if not bounds[0] <= v <= bounds[1]:
        raise SchemaError(f"station {sid!r}: {field} {text!r} outside Penang box {bounds}")


def parse_station_feed(payload: Any) -> dict[str, dict[str, str]]:
    """Validate every national record and index it by ``a`` (must be unique)."""
    if not isinstance(payload, list) or not payload:
        raise SchemaError("feed top level is not a non-empty list")
    out: dict[str, dict[str, str]] = {}
    for n, r in enumerate(payload):
        if not isinstance(r, dict):
            raise SchemaError(f"feed[{n}] is not an object")
        for k in JPS_REQUIRED_KEYS:
            if not isinstance(r.get(k), str):
                raise SchemaError(f"feed[{n}]: key {k!r} missing or not a string")
        if r["a"] in out:
            raise SchemaError(f"feed[{n}]: duplicate station key {r['a']!r}")
        out[r["a"]] = r
    return out


def build_station_rows(
    feed: dict[str, dict[str, str]],
    rf_ids: list[str],
    wl_ids: list[str],
    *,
    last_modified: str,
    retrieved_at: datetime,
) -> list[dict[str, str]]:
    """One row per unique inventory ID; every inventory ID must be present in the feed."""
    ids = sorted(set(rf_ids) | set(wl_ids))
    missing = [i for i in ids if i not in feed]
    if missing:
        raise SchemaError(f"inventory IDs absent from feed: {missing}")
    rows = []
    for sid in ids:
        r = feed[sid]
        if r["f"].strip() != PENANG_STATE:
            raise SchemaError(f"station {sid!r}: state {r['f']!r} is not {PENANG_STATE}")
        _in_range(r["c"], PENANG_LAT, "latitude (c)", sid)
        _in_range(r["d"], PENANG_LON, "longitude (d)", sid)
        rows.append(
            {
                "jps_internal_id": sid,
                "in_rainfall_inventory": str(sid in rf_ids).lower(),
                "in_water_level_inventory": str(sid in wl_ids).lower(),
                "source_station_name": r["b"],
                "source_state": r["f"],
                "source_district": r["e"],
                "source_main_basin": r["h"],
                "source_sub_basin": r["g"],
                "source_sensor_types": r["i"],
                "latitude": r["c"],
                "longitude": r["d"],
                "coordinate_crs_note": CRS_NOTE,
                "source_url": JPS_FEED_URL,
                "source_last_modified": last_modified,
                "retrieved_at": retrieved_at.isoformat(),
            }
        )
    return rows


def parse_layers(payload: Any) -> list[dict[str, Any]]:
    """``/FeatureServer/layers`` -> [{id, name, year, geometry_type, tarikh_type}]."""
    layers = payload.get("layers") if isinstance(payload, dict) else None
    if not isinstance(layers, list) or not layers:
        raise SchemaError("layers response has no 'layers' list")
    out = []
    for lyr in layers:
        name, gtype, fields = lyr.get("name"), lyr.get("geometryType"), lyr.get("fields")
        m = LAYER_NAME_RE.match(name.strip()) if isinstance(name, str) else None
        if m is None:
            raise SchemaError(f"layer {lyr.get('id')!r}: unexpected name {name!r}")
        if gtype not in GEOMETRY_TYPES or not isinstance(fields, list):
            raise SchemaError(f"layer {lyr.get('id')!r}: geometry {gtype!r} or fields invalid")
        types = {f.get("name"): f.get("type") for f in fields if isinstance(f, dict)}
        tarikh = types.get("tarikh")
        out.append(
            {
                "id": lyr["id"],
                "name": name,
                "year": m.group(2),
                "geometry_type": gtype,
                "tarikh_type": (tarikh or "").replace("esriFieldType", ""),
            }
        )
    return sorted(out, key=lambda x: x["id"])


def parse_counts(payload: Any) -> dict[int, int]:
    layers = payload.get("layers") if isinstance(payload, dict) else None
    if not isinstance(layers, list):
        raise SchemaError("count response has no 'layers' list")
    return {int(x["id"]): int(x["count"]) for x in layers}


def summarise_dates(payload: Any, field_type: str) -> dict[str, str]:
    """Summarise a ``groupBy tarikh`` statistics response (field ``n`` = feature count)."""
    feats = payload.get("features") if isinstance(payload, dict) else None
    if not isinstance(feats, list):
        raise SchemaError(f"statistics response invalid: {str(payload)[:200]}")
    dated: dict[str, int] = {}
    undated = 0
    for f in feats:
        v, n = f["attributes"]["tarikh"], int(f["attributes"]["n"])
        if v is None or (isinstance(v, str) and not v.strip()):
            undated += n
        elif field_type == "Date":
            day = datetime.fromtimestamp(v / 1000, UTC).date().isoformat()
            dated[day] = dated.get(day, 0) + n
        else:
            dated[str(v)] = dated.get(str(v), 0) + n  # free text, verbatim, never parsed
    ordered = sorted(dated) if field_type == "Date" else []
    return {
        "fg_dated_count": str(sum(dated.values())),
        "fg_undated_count": str(undated),
        "fg_distinct_dates": str(len(dated)),
        "fg_min_date": ordered[0] if ordered else "",
        "fg_max_date": ordered[-1] if ordered else "",
    }


def _get_json(url: str, fetcher: Fetcher) -> tuple[Any, dict[str, str], datetime]:
    body, headers, at = fetcher(url)
    payload = json.loads(body.decode("utf-8-sig"))
    if isinstance(payload, dict) and "error" in payload:
        raise SchemaError(f"service error for {url}: {payload['error']}")
    return payload, headers, at


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def run_stations(fetcher: Fetcher = fetch, output: Path = STATIONS_OUT) -> int:
    payload, headers, at = _get_json(JPS_FEED_URL, fetcher)
    feed = parse_station_feed(payload)
    rf, wl = load_inventory_ids(RF_CSV), load_inventory_ids(WL_CSV)
    rows = build_station_rows(
        feed, rf, wl, last_modified=headers.get("Last-Modified", ""), retrieved_at=at
    )
    penang = sum(1 for r in feed.values() if r["f"].strip() == PENANG_STATE)
    print(f"stations: records={len(feed)} penang_records={penang} retrieved_at={at.isoformat()}")
    print(
        f"  rainfall {len(rf)}/{len(rf)} and water level {len(wl)}/{len(wl)} IDs have coordinates"
    )
    print(f"  unique inventory IDs={len(rows)} Last-Modified={headers.get('Last-Modified')}")
    _write_csv(output, STATION_COLUMNS, rows)
    print(f"  wrote {output}")
    return 0


def run_flood_history(fetcher: Fetcher = fetch, output: Path = LAYERS_OUT) -> int:
    layers_payload, _, at = _get_json(f"{PEGIS_SERVICE_URL}/layers?f=json", fetcher)
    layers = parse_layers(layers_payload)
    time.sleep(REQUEST_DELAY_S)
    defs = urllib.parse.quote(json.dumps({str(x["id"]): "1=1" for x in layers}))
    counts = parse_counts(
        _get_json(
            f"{PEGIS_SERVICE_URL}/query?layerDefs={defs}&returnCountOnly=true&f=json", fetcher
        )[0]
    )
    stats = urllib.parse.quote(
        json.dumps(
            [
                {
                    "statisticType": "count",
                    "onStatisticField": "objectid",
                    "outStatisticFieldName": "n",
                }
            ]
        )
    )
    rows = []
    for x in layers:
        summary = dict.fromkeys(LAYER_COLUMNS[6:11], "")
        if x["tarikh_type"]:
            time.sleep(REQUEST_DELAY_S)
            url = (
                f"{PEGIS_SERVICE_URL}/{x['id']}/query?where=1%3D1&groupByFieldsForStatistics="
                f"tarikh&outStatistics={stats}&f=json"
            )
            summary = summarise_dates(_get_json(url, fetcher)[0], x["tarikh_type"])
        rows.append(
            {
                "layer_id": str(x["id"]),
                "layer_name": x["name"],
                "fg_year_from_name": x["year"],
                "geometry_type": x["geometry_type"],
                "feature_count": str(counts.get(x["id"], "")),
                "tarikh_field_type": x["tarikh_type"],
                **summary,
                "source_url": f"{PEGIS_SERVICE_URL}/{x['id']}",
                "retrieved_at": at.isoformat(),
            }
        )
        print(f"  layer {x['id']:>2} {x['name']}: {rows[-1]['feature_count']} features")
    _write_csv(output, LAYER_COLUMNS, rows)
    print(f"flood-history: layers={len(rows)} wrote {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("source", choices=("stations", "flood-history"))
    ap.add_argument("--output", type=Path, help="override the output CSV path")
    args = ap.parse_args(argv)
    try:
        if args.source == "stations":
            return run_stations(output=args.output or STATIONS_OUT)
        return run_flood_history(output=args.output or LAYERS_OUT)
    except SchemaError as e:
        print(f"SCHEMA CHANGE: {e}", file=sys.stderr)
        return 2
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"FETCH ERROR: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
