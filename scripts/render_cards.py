"""Render model/dataset cards from stored MLOps records (offline).

Reads an experiment run JSON (and optional evaluation JSON + dataset lineage
JSON) from the local store and writes deterministic Markdown cards.

Usage (repo root):
    .\\.venv\\Scripts\\python.exe scripts\\render_cards.py --run RUN_ID
        [--evaluation eval.json] [--out-dir cards/]

No network, no Docker, no MLflow server. CPU only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from floodguard.mlops.cards import render_dataset_card, render_model_card
from floodguard.mlops.experiments import get_run


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render model/dataset cards (offline).")
    ap.add_argument("--store-root", type=Path, default=Path("artifacts/mlops"))
    ap.add_argument("--run", required=True, help="experiment run_id")
    ap.add_argument("--evaluation", type=Path, default=None, help="evaluation JSON (optional)")
    ap.add_argument(
        "--dataset-lineage", type=Path, default=None, help="dataset lineage JSON (optional)"
    )
    ap.add_argument("--out-dir", type=Path, default=Path("artifacts/mlops/cards"))
    args = ap.parse_args(argv)

    from floodguard.mlops import validate_segment

    try:
        validate_segment(args.run, field="run id")
        run = get_run(args.store_root, args.run)
    except (OSError, ValueError) as exc:
        print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    evaluation: dict[str, object] | None = None
    evaluation_source = "none provided"
    if args.evaluation is not None:
        try:
            evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
            evaluation_source = f"UNVERIFIED external file: {args.evaluation}"
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2

    args.out_dir.mkdir(parents=True, exist_ok=True)
    model_card = render_model_card(
        run=run,
        evaluation=evaluation,
        lineage_digest=str(run.get("artifact_ref", {}).get("model_sha256", "unrecorded")),
        limitations=None,
        evaluation_source=evaluation_source,
    )
    model_path = args.out_dir / f"model-card-{args.run}.md"
    model_path.write_text(model_card, encoding="utf-8")

    written: dict[str, str] = {"model_card": str(model_path)}
    if args.dataset_lineage is not None:
        try:
            lineage = json.loads(args.dataset_lineage.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"REJECTED: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        dataset_version = str(lineage.get("dataset_version", "v"))
        validate_segment(dataset_version, field="dataset version")
        dataset_card = render_dataset_card(lineage=lineage, coverage=None)
        dataset_path = args.out_dir / f"dataset-card-{dataset_version}.md"
        dataset_path.write_text(dataset_card, encoding="utf-8")
        written["dataset_card"] = str(dataset_path)

    print(json.dumps({"status": "CARDS_RENDERED", **written}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
