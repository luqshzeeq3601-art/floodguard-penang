"""Complete Feature Engineering Pipeline for FloodGuard Penang.

Orchestrates offline feature table extraction, validation invariants, and write-once persistence.
Output directory structure:
    data/features/<dataset_version>/v1/
        rainfall_features.jsonl
        water_level_features.jsonl
        paired_site_features.jsonl
        feature_manifest.json

Strictly deterministic, offline, and write-once.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from floodguard.analysis.dataset import (
    ProcessedDataset,
)
from floodguard.features.rainfall import RainfallFeatureConfig
from floodguard.features.registry import REGISTRY, SCHEMA_VERSION
from floodguard.features.table import build_feature_table
from floodguard.features.water_level import WaterLevelFeatureConfig
from floodguard.features.weather import WeatherForecastRecord
from floodguard.ingestion.storage import Artifact, write_artifacts


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def to_jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True, allow_nan=False) for r in rows]
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def to_json_bytes(doc: Mapping[str, Any]) -> bytes:
    text = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    return (text + "\n").encode("utf-8")


def compute_feature_coverage_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute null vs present counts and ratios for every feature column in table."""
    if not rows:
        return {"total_rows": 0, "columns": {}}

    total = len(rows)
    col_counts: dict[str, int] = Counter()
    for r in rows:
        for k, v in r.items():
            if v is not None:
                col_counts[k] += 1

    summary: dict[str, Any] = {}
    for col in sorted(rows[0].keys()):
        present = col_counts.get(col, 0)
        summary[col] = {
            "present_count": present,
            "null_count": total - present,
            "coverage_ratio": round(present / total, 6) if total > 0 else 0.0,
        }

    return {"total_rows": total, "columns": summary}


@dataclass(frozen=True)
class FeaturePipelineResult:
    dataset_version: str
    feature_schema_version: str
    output_dir: Path
    written: list[PurePosixPath]
    manifest: dict[str, Any]


def run_feature_pipeline(
    dataset: ProcessedDataset,
    output_root: Path,
    *,
    station_metadata: Mapping[str, Mapping[str, Any]] | None = None,
    station_master_sha256: str | None = None,
    threshold_reference: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    threshold_reference_sha256: str | None = None,
    forecast_records: Sequence[WeatherForecastRecord] | None = None,
    rainfall_config: RainfallFeatureConfig | None = None,
    water_level_config: WaterLevelFeatureConfig | None = None,
) -> FeaturePipelineResult:
    """Run full feature extraction, invariant checks, and write-once persistence."""
    rf_cfg = rainfall_config or RainfallFeatureConfig()
    wl_cfg = water_level_config or WaterLevelFeatureConfig()

    tables = build_feature_table(
        dataset.rows,
        station_metadata=station_metadata,
        threshold_reference=threshold_reference,
        forecast_records=forecast_records,
        rainfall_config=rf_cfg,
        water_level_config=wl_cfg,
    )

    rf_rows = tables["rainfall_features"]
    wl_rows = tables["water_level_features"]
    paired_rows = tables["paired_site_features"]

    # Coverage summaries
    rf_cov = compute_feature_coverage_summary(rf_rows)
    wl_cov = compute_feature_coverage_summary(wl_rows)
    paired_cov = compute_feature_coverage_summary(paired_rows)

    # Convert to bytes
    rf_bytes = to_jsonl_bytes(rf_rows)
    wl_bytes = to_jsonl_bytes(wl_rows)
    paired_bytes = to_jsonl_bytes(paired_rows)

    rf_sha = sha256_bytes(rf_bytes)
    wl_sha = sha256_bytes(wl_bytes)
    paired_sha = sha256_bytes(paired_bytes)

    # Invariant checks
    checks = [
        {
            "name": "rainfall_rows_unique_keys",
            "passed": len(rf_rows)
            == len({(r["fg_sensor_id"], r["prediction_origin_utc"]) for r in rf_rows}),
            "observed_rows": len(rf_rows),
        },
        {
            "name": "water_level_rows_unique_keys",
            "passed": len(wl_rows)
            == len({(r["fg_sensor_id"], r["prediction_origin_utc"]) for r in wl_rows}),
            "observed_rows": len(wl_rows),
        },
        {
            "name": "paired_site_rows_unique_keys",
            "passed": len(paired_rows)
            == len({(r["fg_site_id"], r["prediction_origin_utc"]) for r in paired_rows}),
            "observed_rows": len(paired_rows),
        },
    ]

    manifest: dict[str, Any] = {
        "feature_schema_version": SCHEMA_VERSION,
        "dataset_version": dataset.dataset_version,
        "observations_sha256": dataset.observations_sha256,
        "station_master_sha256": station_master_sha256,
        "threshold_reference_sha256": threshold_reference_sha256,
        "configurations": {
            "rainfall": asdict(rf_cfg),
            "water_level": asdict(wl_cfg),
        },
        "artifacts": {
            "rainfall_features": {
                "file": "rainfall_features.jsonl",
                "rows": len(rf_rows),
                "sha256": rf_sha,
                "coverage_summary": rf_cov,
            },
            "water_level_features": {
                "file": "water_level_features.jsonl",
                "rows": len(wl_rows),
                "sha256": wl_sha,
                "coverage_summary": wl_cov,
            },
            "paired_site_features": {
                "file": "paired_site_features.jsonl",
                "rows": len(paired_rows),
                "sha256": paired_sha,
                "coverage_summary": paired_cov,
            },
        },
        "feature_registry": REGISTRY.to_dict(),
        "checks": checks,
    }

    manifest_bytes = to_json_bytes(manifest)

    # Write-once storage
    version_dir = PurePosixPath(dataset.dataset_version, "v1")
    artifacts = [
        Artifact(version_dir / "rainfall_features.jsonl", rf_bytes),
        Artifact(version_dir / "water_level_features.jsonl", wl_bytes),
        Artifact(version_dir / "paired_site_features.jsonl", paired_bytes),
        Artifact(version_dir / "feature_manifest.json", manifest_bytes),
    ]

    written_paths = write_artifacts(output_root, artifacts)
    target_dir = output_root.joinpath(*version_dir.parts)

    return FeaturePipelineResult(
        dataset_version=dataset.dataset_version,
        feature_schema_version=SCHEMA_VERSION,
        output_dir=target_dir,
        written=written_paths,
        manifest=manifest,
    )
