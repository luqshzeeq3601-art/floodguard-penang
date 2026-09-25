"""Shared Phase 3 input contract: load and verify one Phase 2 processed dataset, check canonical
rows of one measurement type, and write deterministic write-once JSON outputs.

Used by every Phase 3 analysis so each reads the same verified input the same way
(docs/RAINFALL_DISTRIBUTION_ANALYSIS.md section 2, docs/WATER_LEVEL_TREND_ANALYSIS.md section 2).
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from floodguard.ingestion.storage import Artifact, write_artifacts
from floodguard.preprocessing.timestamps import SOURCE_TIMEZONE_POLICY
from floodguard.validation.observations import OBSERVATION_TYPES
from floodguard.validation.observations import SCHEMA_VERSION as OBSERVATION_SCHEMA
from floodguard.validation.summary import SCHEMA_VERSION as SUMMARY_SCHEMA


class AnalysisContractError(ValueError):
    """The input does not satisfy the Phase 2 processed-dataset contract."""


@dataclass(frozen=True)
class ProcessedDataset:
    dataset_version: str
    observations_sha256: str
    rows: list[dict[str, Any]]
    quality_summary: dict[str, Any]
    manifest: dict[str, Any] = field(repr=False)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def select_measurement(
    rows: Iterable[Mapping[str, Any]],
    *,
    measurement_type: str,
    unit: str,
    sensor_type: str,
    value_ok: Callable[[float], bool],
    value_rule: str,
) -> tuple[list[Mapping[str, Any]], dict[str, int]]:
    """(rows of ``measurement_type``, counts of other measurement types). Every row must be an
    ``observations/v1`` row of a known type; a selected row with the wrong unit, sensor type,
    identity, time zone, usability flag or an invalid usable value, or a repeated canonical key,
    raises ``AnalysisContractError``."""
    selected: list[Mapping[str, Any]] = []
    excluded: Counter[str] = Counter()
    keys: set[tuple[str, datetime]] = set()
    for i, r in enumerate(rows):
        mt = r.get("measurement_type")
        if r.get("observation_schema_version") != OBSERVATION_SCHEMA:
            raise AnalysisContractError(f"row {i}: not an {OBSERVATION_SCHEMA} row")
        if mt not in OBSERVATION_TYPES:
            raise AnalysisContractError(f"row {i}: unknown measurement type {mt!r}")
        if mt != measurement_type:
            excluded[str(mt)] += 1
            continue
        if r.get("unit") != unit:
            raise AnalysisContractError(
                f"row {i}: {measurement_type} unit {r.get('unit')!r} != {unit}"
            )
        if r.get("sensor_type") != sensor_type:
            raise AnalysisContractError(f"row {i}: sensor type {r.get('sensor_type')!r}")
        if not r.get("fg_sensor_id") or not r.get("fg_site_id"):
            raise AnalysisContractError(f"row {i}: missing sensor/site identity")
        for t in ("observation_time_utc", "observation_time_local"):
            if not isinstance(r.get(t), str) or datetime.fromisoformat(r[t]).tzinfo is None:
                raise AnalysisContractError(f"row {i}: {t} is not a tz-aware ISO time")
        policy = SOURCE_TIMEZONE_POLICY.get(r.get("source", ""))
        local = datetime.fromisoformat(r["observation_time_local"])
        if policy is None or local.utcoffset() != policy.assumed_zone.utcoffset(local):
            raise AnalysisContractError(f"row {i}: local time not in the source policy zone")
        if datetime.fromisoformat(r["observation_time_utc"]) != local:
            raise AnalysisContractError(f"row {i}: local and UTC times are different instants")
        if not isinstance(r.get("usable"), bool):
            raise AnalysisContractError(f"row {i}: usable is not a boolean")
        v = r.get("value")
        if r["usable"] and (
            isinstance(v, bool)
            or not isinstance(v, int | float)
            or not math.isfinite(v)
            or not value_ok(float(v))
        ):
            raise AnalysisContractError(f"row {i}: usable value {v!r} invalid ({value_rule})")
        key = (r["fg_sensor_id"], local)  # the instant, whatever its text form
        if key in keys:
            raise AnalysisContractError(f"row {i}: repeated canonical key {key}")
        keys.add(key)
        selected.append(r)
    return selected, dict(sorted(excluded.items()))


def load_processed_dataset(path: Path) -> ProcessedDataset:
    """Read and verify one processed dataset (its directory or its ``dataset_manifest.json``)."""
    d = path.parent if path.name == "dataset_manifest.json" else path
    try:
        manifest = json.loads((d / "dataset_manifest.json").read_text(encoding="utf-8"))
        data = (d / "observations.jsonl").read_bytes()
        summary = json.loads((d / "quality_summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise AnalysisContractError(f"unreadable processed dataset {d}: {e}") from e
    version = manifest.get("dataset_version")
    if not isinstance(version, str) or version != d.name:
        raise AnalysisContractError(f"dataset_version {version!r} != directory {d.name!r}")
    if sha256(data) != manifest.get("observations_sha256"):
        raise AnalysisContractError("observations.jsonl does not match its manifest hash")
    failed = [c.get("name") for c in manifest.get("checks", []) if c.get("passed") is not True]
    if failed or not manifest.get("checks"):
        raise AnalysisContractError(f"dataset checks missing or failed: {failed}")
    if summary.get("summary_schema_version") != SUMMARY_SCHEMA:
        raise AnalysisContractError(f"quality summary is not {SUMMARY_SCHEMA}")
    rows = [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != manifest.get("observations_rows"):
        raise AnalysisContractError("row count does not match the manifest")
    return ProcessedDataset(version, sha256(data), rows, summary, manifest)


def read_station_master(
    station_master_dir: Path, names: tuple[str, ...]
) -> tuple[dict[str, list[dict[str, str]]], str]:
    """({file name: CSV rows}, SHA-256 over the files joined by NUL in the given order)."""
    raw = {n: (station_master_dir / n).read_bytes() for n in names}
    digest = sha256(b"\0".join(raw[n] for n in names))
    return {n: list(csv.DictReader(b.decode("utf-8-sig").splitlines())) for n, b in raw.items()}, (
        digest
    )


def check_station_master_origin(manifest: Mapping[str, Any], station_master_dir: Path) -> None:
    """Refuse a station master other than the one the dataset was built with (the manifest's
    ``station_master_origin`` is ``<file>@sha256:<hash prefix>``)."""
    origin = manifest.get("station_master_origin")
    name, sep, prefix = str(origin).partition("@sha256:")
    if not sep or not prefix or "/" in name or "\\" in name:
        raise AnalysisContractError(f"manifest station_master_origin {origin!r} is not usable")
    try:
        actual = sha256((station_master_dir / name).read_bytes())
    except OSError as e:
        raise AnalysisContractError(f"station master file {name!r} unreadable: {e}") from e
    if not actual.startswith(prefix):
        raise AnalysisContractError(f"station master {name} does not match the dataset's origin")


def load_station_metadata(station_master_dir: Path) -> tuple[dict[str, dict[str, Any]], str]:
    """(``fg_sensor_id`` -> source ID, district and basin; SHA-256 over sensors.csv + sites.csv)
    from the local station master. The hash goes into the output so its lineage is recorded."""
    tables, digest = read_station_master(station_master_dir, ("sensors.csv", "sites.csv"))
    sites = {s["fg_site_id"]: s for s in tables["sites.csv"]}
    out = {}
    for s in tables["sensors.csv"]:
        site = sites.get(s["fg_site_id"], {})
        out[s["fg_sensor_id"]] = {
            "sensor_type": s["sensor_type"],
            "jps_internal_id": s.get("jps_internal_id") or None,
            "district": site.get("district") or None,
            "main_basin": site.get("main_basin") or None,
        }
    return out, digest


def load_station_context(
    manifest: Mapping[str, Any], station_master_dir: Path
) -> tuple[dict[str, dict[str, Any]] | None, str | None]:
    """Station metadata and its hash for every Phase 3 analysis, only from the station master
    the dataset was built with (``check_station_master_origin``). No local station master
    (no ``sensors.csv``): ``(None, None)``."""
    if not (station_master_dir / "sensors.csv").is_file():
        return None, None
    check_station_master_origin(manifest, station_master_dir)
    return load_station_metadata(station_master_dir)


def to_json_bytes(document: Mapping[str, Any]) -> bytes:
    text = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    return (text + "\n").encode("utf-8")


def write_once_json(
    document: Mapping[str, Any], output_root: Path, file_name: str
) -> tuple[Path, bool]:
    """Write-once ``<output_root>/<dataset_version>/<file_name>``. Returns (path, written);
    identical existing content is a no-op, different content raises."""
    rel = PurePosixPath(document["dataset_version"], file_name)
    written = write_artifacts(output_root, [Artifact(rel, to_json_bytes(document))])
    return output_root.joinpath(*rel.parts), bool(written)
