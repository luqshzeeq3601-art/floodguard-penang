"""Run the promotion gate for one candidate and optionally transition stage.

Reads a JSON candidate bundle (see ``floodguard.mlops.promotion``), prints
the PROMOTE/BLOCK verdict, and — only with ``--apply`` on PROMOTE — moves
the registry version to ``production``. Anything else leaves the registry
untouched.

Usage (repo root):
    .\\.venv\\Scripts\\python.exe scripts\\promote_model.py --candidate candidate.json [--apply]

No network, no Docker, no MLflow server. CPU only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from floodguard.mlops import GATE_PROMOTE
from floodguard.mlops.promotion import PromotionInput, decide_promotion
from floodguard.mlops.registry import transition_stage


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the promotion gate (offline).")
    ap.add_argument("--candidate", type=Path, required=True, help="promotion input JSON")
    ap.add_argument("--apply", action="store_true", help="transition to production on PROMOTE")
    ap.add_argument("--store-root", type=Path, default=Path("artifacts/mlops"))
    ap.add_argument("--name", default=None, help="registry model name (required with --apply)")
    ap.add_argument(
        "--version", type=int, default=None, help="registry version (required with --apply)"
    )
    ap.add_argument("--reason", default="promotion gate PROMOTE", help="transition reason")
    args = ap.parse_args(argv)

    try:
        bundle = json.loads(args.candidate.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    candidate = PromotionInput(
        run_id=str(bundle.get("run_id", "")),
        model_family=str(bundle.get("model_family", "")),
        task=str(bundle.get("task", "forecasting")),
        evidence_level=str(bundle.get("evidence_level", "")),
        acceptance_passed=bool(bundle.get("acceptance_passed", False)),
        acceptance_detail=str(bundle.get("acceptance_detail", "")),
        baseline_comparison=str(bundle.get("baseline_comparison", "absent")),
        baseline_metrics_reviewed=tuple(bundle.get("baseline_metrics_reviewed", [])),
        eligibility_status=str(bundle.get("eligibility_status", "unknown")),
        leakage_audit_ref=str(bundle.get("leakage_audit_ref", "")),
        model_card_ref=str(bundle.get("model_card_ref", "")),
    )
    # Fail closed on unverifiable references before deciding: refs must exist
    # as files, otherwise a crafted bundle could cite phantom evidence.
    ref_problems = [
        label
        for label, ref in (
            ("leakage_audit_ref", candidate.leakage_audit_ref),
            ("model_card_ref", candidate.model_card_ref),
        )
        if ref and not Path(ref).is_file()
    ]
    if ref_problems:
        print(
            json.dumps(
                {
                    "gate": {
                        "schema_version": "mlops_promotion/v1",
                        "verdict": "BLOCK",
                        "reasons": [
                            f"unverifiable reference (file missing): {label}"
                            for label in ref_problems
                        ],
                        "run_id": candidate.run_id,
                    },
                    "applied": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    verdict = decide_promotion(candidate)
    output: dict[str, object] = {"gate": verdict.to_dict(), "applied": False}

    if verdict.verdict == GATE_PROMOTE and args.apply:
        if args.name is None or args.version is None:
            print("REJECTED: --name and --version are required with --apply.", file=sys.stderr)
            return 2
        try:
            from floodguard.mlops.registry import list_versions

            records = list_versions(args.store_root, args.name)
            matches = [r for r in records if r.get("version") == args.version]
            if not matches:
                raise ValueError(f"unknown model version: {args.name} v{args.version}")
            if str(matches[0].get("run_id")) != candidate.run_id:
                raise ValueError(
                    "candidate run_id does not match the registry version; refusing to apply"
                )
            moved = transition_stage(
                args.store_root,
                name=args.name,
                version=args.version,
                to_stage="production",
                reason=args.reason,
                gate_verdict=GATE_PROMOTE,
            )
        except (OSError, ValueError) as exc:
            print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        output["applied"] = True
        output["model"] = moved.to_dict()

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
