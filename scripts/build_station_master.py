"""Build the FloodGuard station master locally from on-disk JPS metadata (no network).

Inputs (tracked): the rainfall and water-level inventories, the official map-feed coordinate
CSV, and the national-vs-Penang threshold comparison table in GIS_FLOOD_DATASETS.md.
Outputs: sites.csv, sensors.csv, thresholds.csv under data/local/station_master/ (git-ignored:
JPS content is PERMISSION REQUIRED, see docs/DATA_LICENSING_AND_ACCESS.md). Only aggregate
counts are printed. Design: docs/STATION_MASTER_DESIGN.md.

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\build_station_master.py
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import fields
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from floodguard.station_master import (
    CoordinateEvidence,
    Flag,
    SensorEvidence,
    SensorRecord,
    SensorType,
    SiteRecord,
    StationMaster,
    StationMasterError,
    ThresholdEvidence,
    ThresholdRecord,
    ThresholdSource,
    ThresholdType,
    build_station_master,
    build_thresholds,
    normalise_source_id,
)

ROOT = Path(__file__).resolve().parents[1]
RAINFALL_CSV = ROOT / "data/metadata/jps/penang_rainfall_stations.csv"
WATER_LEVEL_CSV = ROOT / "data/metadata/jps/penang_water_level_stations.csv"
COORDINATES_CSV = ROOT / "data/metadata/gis/penang_station_coordinates_jps.csv"
PENANG_THRESHOLD_DOC = ROOT / "data/metadata/gis/GIS_FLOOD_DATASETS.md"
DEFAULT_OUTPUT_DIR = ROOT / "data/local/station_master"

# Penang portal comparison (GIS_FLOOD_DATASETS.md section 5): single probe, logged in
# data/metadata/gis/raw/probe_log_20260924.tsv at 2026-09-24T04:15:59Z.
PENANG_PORTAL_URL = "https://infobanjirjps.penang.gov.my/WaterLevel/LatestData/All"
PENANG_PORTAL_CAPTURED_AT = datetime.fromisoformat("2026-09-24T12:15:59+08:00")
# Row: | <jps_internal_id> (<display>) | A / W / D (national) | A / W / D (Penang) ...
_NUM = r"(-?\d+(?:\.\d+)?)"
_TRIPLE = rf"{_NUM} / {_NUM} / {_NUM}"
PENANG_ROW = re.compile(rf"^\| (\S+) \((\S+)\) \| {_TRIPLE} \| {_TRIPLE}", re.MULTILINE)
AWD = (ThresholdType.WASPADA, ThresholdType.AMARAN, ThresholdType.BAHAYA)
NATIONAL_COLUMNS = {
    ThresholdType.NORMAL: "threshold_normal",
    ThresholdType.WASPADA: "threshold_alert",
    ThresholdType.AMARAN: "threshold_warning",
    ThresholdType.BAHAYA: "threshold_danger",
}
SENSOR_CODES = {"RF": SensorType.RAINFALL, "WL": SensorType.WATER_LEVEL}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_sensor_evidence(path: Path, sensor_type: SensorType) -> list[SensorEvidence]:
    wl = sensor_type is SensorType.WATER_LEVEL
    return [
        SensorEvidence(
            sensor_type=sensor_type,
            jps_internal_id=r["jps_internal_id"],
            jps_display_station_id=r["jps_display_station_id"],
            station_name=r["station_name"],
            state=r["state"],
            district=r["district"],
            main_basin=r["main_basin"] if wl else None,
            sub_basin=r["sub_river_basin"] if wl else None,
            source_url=r["source_url"],
            discovered_at=datetime.fromisoformat(r["discovered_at"]),
        )
        for r in _rows(path)
    ]


def load_coordinates(path: Path) -> list[CoordinateEvidence]:
    return [
        CoordinateEvidence(
            jps_internal_id=r["jps_internal_id"],
            station_name=r["source_station_name"],
            state=r["source_state"],
            district=r["source_district"],
            main_basin=r["source_main_basin"],
            sub_basin=r["source_sub_basin"],
            sensor_types=frozenset(
                SENSOR_CODES[c.strip()] for c in r["source_sensor_types"].split(",")
            ),
            latitude=r["latitude"],
            longitude=r["longitude"],
            crs_declared="not declared" not in r["coordinate_crs_note"],
            source_url=r["source_url"],
            retrieved_at=datetime.fromisoformat(r["retrieved_at"]),
        )
        for r in _rows(path)
    ]


def national_thresholds(path: Path) -> list[ThresholdEvidence]:
    return [
        ThresholdEvidence(
            jps_internal_id=r["jps_internal_id"],
            threshold_type=t,
            value_raw=r[col],
            source=ThresholdSource.JPS_NATIONAL_LISTING,
            source_url=r["source_url"],
            captured_at=datetime.fromisoformat(r["discovered_at"]),
            provenance=f"{path.name} column {col}",
        )
        for r in _rows(path)
        for t, col in NATIONAL_COLUMNS.items()
    ]


def penang_thresholds(
    doc_text: str, national: Sequence[ThresholdEvidence], doc_name: str
) -> list[ThresholdEvidence]:
    """Penang-portal A/W/D values from the tracked comparison table (Normal is not parsed).

    The table's national columns must equal the national listing, else the doc is stale.
    """
    listed = {
        (normalise_source_id(e.jps_internal_id), e.threshold_type): Decimal(e.value_raw)
        for e in national
    }
    out: list[ThresholdEvidence] = []
    for m in PENANG_ROW.finditer(doc_text):
        key, nat, pen = m.group(1), m.groups()[2:5], m.groups()[5:8]
        for t, n_raw, p_raw in zip(AWD, nat, pen, strict=True):
            if (key, t) in listed and listed[(key, t)] != Decimal(n_raw):
                raise StationMasterError(f"{doc_name}: national {key} {t} disagrees with listing")
            out.append(
                ThresholdEvidence(
                    jps_internal_id=key,
                    threshold_type=t,
                    value_raw=p_raw,
                    source=ThresholdSource.JPS_PENANG_PORTAL,
                    source_url=PENANG_PORTAL_URL,
                    captured_at=PENANG_PORTAL_CAPTURED_AT,
                    provenance=f"{doc_name} section 5 comparison table",
                )
            )
    return out


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return "|".join(str(v) for v in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def write_csv(path: Path, record_type: type, records: Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [f.name for f in fields(record_type)]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        w.writerows([_cell(getattr(r, c)) for c in cols] for r in records)


def write_outputs(
    out_dir: Path, master: StationMaster, thresholds: Sequence[ThresholdRecord]
) -> None:
    write_csv(out_dir / "sites.csv", SiteRecord, master.sites)
    write_csv(out_dir / "sensors.csv", SensorRecord, master.sensors)
    write_csv(out_dir / "thresholds.csv", ThresholdRecord, thresholds)


def build(
    rainfall: Path, water_level: Path, coordinates: Path, penang_doc: Path | None
) -> tuple[StationMaster, tuple[ThresholdRecord, ...]]:
    sensors = load_sensor_evidence(rainfall, SensorType.RAINFALL) + load_sensor_evidence(
        water_level, SensorType.WATER_LEVEL
    )
    master = build_station_master(sensors, load_coordinates(coordinates))
    evidence = national_thresholds(water_level)
    if penang_doc is not None:
        doc_text = penang_doc.read_text(encoding="utf-8")
        penang = penang_thresholds(doc_text, evidence, penang_doc.name)
        if not penang:
            raise StationMasterError(f"no threshold comparison rows found in {penang_doc}")
        evidence += penang
    return master, build_thresholds(master, evidence)


def summary(master: StationMaster, thresholds: Sequence[ThresholdRecord]) -> dict[str, Any]:
    types_by_site: dict[str, set[SensorType]] = {}
    for s in master.sensors:
        types_by_site.setdefault(s.fg_site_id, set()).add(s.sensor_type)
    flags = Counter(f for rec in master.sites for f in rec.fg_quality_flags)
    flags.update(f for rec in master.sensors for f in rec.fg_quality_flags)
    conflicts = {
        t.fg_sensor_id
        for t in thresholds
        if Flag.THRESHOLD_PROVENANCE_CONFLICT in t.fg_quality_flags
    }
    return {
        "sites": len(master.sites),
        "sensors_rainfall": sum(s.sensor_type is SensorType.RAINFALL for s in master.sensors),
        "sensors_water_level": sum(s.sensor_type is SensorType.WATER_LEVEL for s in master.sensors),
        "sites_multi_sensor": sum(len(t) > 1 for t in types_by_site.values()),
        "sites_rainfall_only": sum(t == {SensorType.RAINFALL} for t in types_by_site.values()),
        "sites_water_level_only": sum(
            t == {SensorType.WATER_LEVEL} for t in types_by_site.values()
        ),
        "flags": {str(k): v for k, v in sorted(flags.items())},
        "thresholds": len(thresholds),
        "thresholds_by_source_type": dict(
            sorted(Counter(f"{t.threshold_source}:{t.threshold_type}" for t in thresholds).items())
        ),
        "thresholds_label_eligible": sum(t.fg_label_eligible for t in thresholds),
        "sensors_with_threshold_conflict": len(conflicts),
        "ambiguous_source_keys": sorted(
            {
                s.fg_source_site_key
                for s in master.sites
                if Flag.AMBIGUOUS_SITE_MAPPING in s.fg_quality_flags
            }
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    p.add_argument("--rainfall", type=Path, default=RAINFALL_CSV)
    p.add_argument("--water-level", type=Path, default=WATER_LEVEL_CSV)
    p.add_argument("--coordinates", type=Path, default=COORDINATES_CSV)
    p.add_argument("--penang-threshold-doc", type=Path, default=PENANG_THRESHOLD_DOC)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    a = p.parse_args(argv)
    try:
        master, thresholds = build(a.rainfall, a.water_level, a.coordinates, a.penang_threshold_doc)
    except StationMasterError as exc:
        print(f"STATION MASTER ERROR: {exc}", file=sys.stderr)
        return 2
    write_outputs(a.output_dir, master, thresholds)
    for k, v in summary(master, thresholds).items():
        print(f"{k}: {v}")
    print(f"written: {a.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
