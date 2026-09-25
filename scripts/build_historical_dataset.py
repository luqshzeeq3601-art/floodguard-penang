"""Build the Phase 2 historical dataset from the raw store in ONE offline run, print a report, exit.

raw (read-only, hashes checked) -> interim component layers (timestamps, station_ids, units) ->
interim/quality/v1 (validated) -> processed/observations/v1/<dataset_version>/ (canonical table,
quality summary, dataset manifest). Every output is write-once; rerunning with the same inputs is
a no-op. No network, no loop, no scheduler. Design: docs/HISTORICAL_PIPELINE.md.

Outputs derived from JPS data are PERMISSION REQUIRED and stay local (git-ignored).

Usage (repo root):
    .venv\\Scripts\\python.exe scripts\\build_historical_dataset.py

Exit codes: 0 built or already present, 1 data-quality check failed (nothing processed written),
2 rejected (unusable inputs, raw integrity or join failure).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from floodguard.ingestion import manifest
from floodguard.ingestion.station_mapping import (
    DEFAULT_SENSORS_CSV,
    SensorMapper,
    StationMappingError,
)
from floodguard.validation.build import DataQualityCheckError, RawIntegrityError, run_build
from floodguard.validation.quality_flags import PipelineJoinError

ROOT = Path(__file__).resolve().parents[1]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the historical dataset (offline, one run).")
    ap.add_argument("--raw-root", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--interim-root", type=Path, default=ROOT / "data" / "interim")
    ap.add_argument("--processed-root", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--station-master", type=Path, default=ROOT / DEFAULT_SENSORS_CSV)
    args = ap.parse_args(argv)
    try:
        mapper = SensorMapper.from_csv(args.station_master)
        result = run_build(args.raw_root, args.interim_root, args.processed_root, mapper)
    except DataQualityCheckError as e:
        print(f"CHECKS FAILED: {e}", file=sys.stderr)
        return 1
    except (
        OSError,
        ValueError,
        KeyError,
        StationMappingError,
        manifest.ManifestError,
        RawIntegrityError,
        PipelineJoinError,
    ) as e:  # OSError includes ImmutableArtifactError (existing output differs)
        print(f"REJECTED: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    canonical = result.report["canonical"]
    print(
        json.dumps(
            {
                "dataset_version": result.dataset_version,
                "output_dir": str(result.output_dir),
                "files_written": len(result.written),
                "validated_rows": result.report["validated"]["rows"],
                "validated_usable": result.report["validated"]["usable"],
                "canonical_rows": canonical["rows"],
                "canonical_usable": canonical["usable"],
                "duplicate_status": canonical["duplicate_status"],
                "excluded_quality_rows": canonical["excluded_quality_rows"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
