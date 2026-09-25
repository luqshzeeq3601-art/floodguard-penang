"""One offline run: raw store -> component layers -> validated (quality) -> processed observations.

Design: docs/HISTORICAL_PIPELINE.md. Reads every SUCCEEDED raw batch (payload, records and
quarantine hashes checked against the manifest first; the raw store is only read), runs the
existing component layers with their own functions, writes their outputs where their scripts would
(same relative paths, same bytes), adds the quality layer, then builds the canonical observation
table, runs the data-quality checks and writes a versioned processed dataset. Every file is
write-once (``floodguard.ingestion.storage``), so a rerun over the same inputs is a no-op and
different content at an existing path is refused.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from floodguard.ingestion import manifest, storage
from floodguard.ingestion.contracts import BatchStatus
from floodguard.ingestion.hashing import canonical_json, jsonl_bytes, sha256_hex
from floodguard.ingestion.station_mapping import SensorMapper
from floodguard.preprocessing import station_ids, timestamps, units
from floodguard.validation import observations, quality_flags, summary
from floodguard.validation.checks import CheckResult, run_checks

PIPELINE_VERSION = "historical_pipeline/v1"
COMPONENT_VERSIONS = {
    "timestamps": timestamps.SCHEMA_VERSION,
    "station_ids": station_ids.SCHEMA_VERSION,
    "units": units.SCHEMA_VERSION,
    "unit_policy": units.POLICY_VERSION,
    "quality": quality_flags.SCHEMA_VERSION,
    "observations": observations.SCHEMA_VERSION,
    "summary": summary.SCHEMA_VERSION,
}
LAYER_DIRS = {  # interim sub-directory, as used by the per-layer scripts
    "timestamps": PurePosixPath("timestamps/v1"),
    "station_ids": PurePosixPath("station_ids/v1"),
    "units": PurePosixPath("units/v1"),
    "quality": PurePosixPath("quality/v1"),
}
KINDS = (  # raw suffix, manifest path key, manifest hash key, output infix
    (".records.jsonl", "records_path", "records_sha256", ""),
    (".quarantine.jsonl", "quarantine_path", "quarantine_sha256", ".quarantine"),
)
LICENCE_NOTE = (
    "Derived from JPS Public Infobanjir data: PERMISSION REQUIRED (docs/DATA_LICENSING_AND_ACCESS"
    ".md). Local use only; do not commit or redistribute. data.gov.my rows: CC BY 4.0, "
    "attribution required."
)


class RawIntegrityError(RuntimeError):
    """A raw file does not match its manifest hash (the raw store changed or is incomplete)."""


class DataQualityCheckError(RuntimeError):
    """The canonical table violates a data-quality invariant; nothing processed is written."""

    def __init__(self, failures: Sequence[CheckResult]) -> None:
        super().__init__("; ".join(f"{c.name}: {c.detail}" for c in failures))
        self.failures = list(failures)


@dataclass
class BuildResult:
    dataset_version: str
    output_dir: PurePosixPath
    written: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)


def _read_verified(raw_root: Path, rel: str, expected_sha: str | None) -> bytes:
    data = storage.fs_path(raw_root / rel).read_bytes()
    if sha256_hex(data) != expected_sha:
        raise RawIntegrityError(f"{rel} does not match its manifest hash")
    return data


def succeeded_batches(raw_root: Path) -> list[dict[str, Any]]:
    """SUCCEEDED manifest entries in a stable order independent of ingestion order."""
    entries = [
        e for e in manifest.read_entries(raw_root) if e.get("status") == BatchStatus.SUCCEEDED
    ]
    return sorted(
        entries,
        key=lambda e: (e["source"], e["dataset"], e["partition"] or "", e["payload_sha256"]),
    )


def _json(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def run_build(
    raw_root: Path,
    interim_root: Path,
    processed_root: Path,
    mapper: SensorMapper,
    *,
    on_batch: Callable[[str], None] | None = None,
) -> BuildResult:
    raw_root = raw_root.resolve()
    for out in (interim_root, processed_root):
        if out.resolve().is_relative_to(raw_root) or raw_root.is_relative_to(out.resolve()):
            raise ValueError("output roots must lie outside the raw root (raw data is immutable)")
    batches = succeeded_batches(raw_root)
    all_quality: list[dict[str, Any]] = []
    written: list[str] = []
    for entry in batches:
        _read_verified(raw_root, entry["payload_path"], entry["payload_sha256"])
        for suffix, path_key, hash_key, infix in KINDS:
            rel = PurePosixPath(entry[path_key])
            data = _read_verified(raw_root, str(rel), entry[hash_key])
            records = [json.loads(x) for x in data.decode("utf-8").splitlines()]
            quarantined = bool(infix)
            ts_rows = [] if quarantined else [timestamps.normalize_record(r) for r in records]
            sid_rows = (
                [station_ids.normalize_record(r, mapper) for r in records]
                if entry["source"] in mapper.sources
                else []
            )
            unit_rows = [u for r in records for u in units.validate_record(r)]
            q_rows = quality_flags.flag_batch(
                records,
                quarantined=quarantined,
                timestamp_rows=ts_rows,
                station_rows=sid_rows,
                unit_rows=unit_rows,
            )
            stem = rel.name.removesuffix(suffix)
            artifacts = [(LAYER_DIRS["units"], f"{stem}{infix}.units.jsonl", unit_rows)]
            artifacts.append((LAYER_DIRS["quality"], f"{stem}{infix}.quality.jsonl", q_rows))
            if not quarantined:
                artifacts.append((LAYER_DIRS["timestamps"], f"{stem}.timestamps.jsonl", ts_rows))
            if sid_rows:
                artifacts.append(
                    (LAYER_DIRS["station_ids"], f"{stem}{infix}.station_ids.jsonl", sid_rows)
                )
            for layer_dir, name, rows in artifacts:
                target = layer_dir / rel.with_name(name)
                written += map(
                    str,
                    storage.write_artifacts(
                        interim_root, [storage.Artifact(target, jsonl_bytes(rows))]
                    ),
                )
            all_quality += q_rows
        if on_batch:
            on_batch(entry["batch_id"])

    obs, excluded = observations.build_observations(all_quality)
    checks = run_checks(obs, all_quality)
    failures = [c for c in checks if not c.passed]
    if failures:
        raise DataQualityCheckError(failures)
    report = summary.quality_summary(all_quality, obs, excluded)
    inputs = [
        {
            k: e[k]
            for k in (
                "batch_id",
                "source",
                "dataset",
                "partition",
                "retrieved_at",
                "payload_sha256",
                "records_sha256",
                "quarantine_sha256",
            )
        }
        for e in batches
    ]
    version_basis = {
        "pipeline": PIPELINE_VERSION,
        "components": COMPONENT_VERSIONS,
        "station_master_origin": mapper.origin,
        "inputs": inputs,
    }
    version = sha256_hex(canonical_json(version_basis).encode("utf-8"))[:16]
    obs_bytes = jsonl_bytes(obs)
    out_dir = PurePosixPath("observations/v1") / version
    dataset_manifest = {
        **version_basis,
        "dataset_version": version,
        "licence": LICENCE_NOTE,
        "timezone_interpretation": (
            "JPS and data.gov.my publish no timezone; Asia/Kuala_Lumpur is ASSUMED "
            "(docs/TIMESTAMP_POLICY.md). observation_time_utc depends on that assumption."
        ),
        "thresholds": "not included; history thresholds are CURRENT_NOT_HISTORICAL (units layer)",
        "observations_sha256": sha256_hex(obs_bytes),
        "observations_rows": len(obs),
        "checks": [c.as_dict() for c in checks],
    }
    written += map(
        str,
        storage.write_artifacts(
            processed_root,
            [
                storage.Artifact(out_dir / "observations.jsonl", obs_bytes),
                storage.Artifact(out_dir / "quality_summary.json", _json(report)),
                storage.Artifact(out_dir / "dataset_manifest.json", _json(dataset_manifest)),
            ],
        ),
    )
    return BuildResult(version, out_dir, written, report)
