"""Register a saved artifact as an experiment run + registry version (offline).

Reads a Phase 5 (classification) or Phase 6 (forecasting) artifact directory,
verifies digests via its trusted loader, writes an experiment run record and
a registry version (stage ``none`` by default, ``staging`` with ``--stage``).

Usage (repo root):
    .\\.venv\\Scripts\\python.exe scripts\\register_model.py --artifact DIR
        --kind forecasting --name wl-plus-30m

No network, no Docker, no MLflow server. CPU only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from floodguard.mlops.experiments import ExperimentInput, log_run
from floodguard.mlops.registry import register


def _read_artifact(artifact: Path, kind: str) -> tuple[Any, dict[str, Any]]:
    if kind == "classification":
        from floodguard.modeling.artifacts import load_artifact_trusted

        return load_artifact_trusted(artifact)
    if kind == "forecasting":
        from floodguard.forecasting.artifacts import load_forecast_artifact_trusted

        return load_forecast_artifact_trusted(artifact)
    raise ValueError(f"unknown kind: {kind}")


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Register a saved artifact (offline).")
    ap.add_argument("--artifact", type=Path, required=True)
    ap.add_argument("--kind", choices=("classification", "forecasting"), required=True)
    ap.add_argument("--name", required=True, help="registry model name")
    ap.add_argument("--store-root", type=Path, default=Path("artifacts/mlops"))
    ap.add_argument("--stage", choices=("none", "staging"), default="none")
    ap.add_argument("--task", choices=("classification", "forecasting", "baseline"), default=None)
    ap.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("."),
        help="allowed root for --artifact (pickle trust boundary)",
    )
    ap.add_argument(
        "--i-attest-real-evaluation",
        type=Path,
        default=None,
        help="required when the artifact claims REAL_PREDICTIVE_EVALUATION evidence",
    )
    args = ap.parse_args(argv)

    from floodguard.mlops import resolve_within_root, validate_segment

    try:
        validate_segment(args.name, field="model name")
        artifact_dir = resolve_within_root(
            str(args.artifact), root=str(args.artifact_root), field="artifact"
        )
        _, metadata = _read_artifact(Path(artifact_dir), args.kind)
    except (OSError, ValueError) as exc:
        print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    expected_schema = "forecast_artifacts/v1" if args.kind == "forecasting" else "artifacts/v1"
    if str(metadata.get("schema_version")) != expected_schema:
        print(
            f"REJECTED: artifact schema {metadata.get('schema_version')!r} "
            f"does not match --kind {args.kind}.",
            file=sys.stderr,
        )
        return 2

    evidence = str(metadata.get("evidence_level", "SYNTHETIC_SOFTWARE_VALIDATION"))
    if evidence == "REAL_PREDICTIVE_EVALUATION" and args.i_attest_real_evaluation is None:
        print(
            "REJECTED: REAL evidence requires --i-attest-real-evaluation <evaluation-record>.",
            file=sys.stderr,
        )
        return 2
    if args.i_attest_real_evaluation is not None and not args.i_attest_real_evaluation.is_file():
        print("REJECTED: attested evaluation record is not a file.", file=sys.stderr)
        return 2

    try:
        from pathlib import Path as _Path

        relative_dir = str(_Path(artifact_dir).relative_to(_Path(".").resolve()))
    except ValueError:
        relative_dir = artifact_dir

    task = args.task or args.kind
    try:
        run_input = ExperimentInput(
            task=task,
            model_family=str(metadata.get("model_family", "unknown")),
            horizon_minutes=int(metadata.get("horizon_minutes", 0)),
            dataset_version=str(metadata.get("dataset_version", "unknown")),
            schema_versions={
                "artifact": str(metadata.get("schema_version", "unknown")),
                "sequence": str(
                    metadata.get("sequence_schema_version", metadata.get("schema_version", ""))
                ),
            },
            split_definition=str(
                metadata.get("split_definition", metadata.get("train_partition", ""))
            ),
            random_seed=int(metadata.get("random_seed", 42)),
            device=str(metadata.get("device", "cpu")),
            library_versions=dict(metadata.get("library_versions", {})),
            params={"model_architecture": metadata.get("model_architecture", {})},
            metrics={},
            tags={"registered_from": relative_dir},
            artifact_ref={
                "dir": relative_dir,
                "model_sha256": metadata.get("model_sha256"),
            },
            evidence_level=evidence,
        )
        run = run_input.to_run()
    except (ValueError, TypeError) as exc:
        print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    run_path = log_run(args.store_root, run)
    version = register(
        args.store_root,
        name=args.name,
        run_id=run.run_id,
        artifact_dir=relative_dir,
        artifact_digest=metadata.get("model_sha256"),
        evidence_level=run.evidence_level,
        reason=f"registered from {relative_dir}",
        stage=args.stage,
    )
    print(
        json.dumps(
            {
                "status": "REGISTERED",
                "run_id": run.run_id,
                "run_path": str(run_path),
                "model": version.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
