"""Model cards and dataset cards (Phase 7 tasks 4-5).

Deterministic Markdown generators fed only by lineage, run and evaluation
records - never by live services. Every card states its evidence level
plainly, carries the non-official research disclaimer, and, where no real
validation exists, says so instead of implying performance.
"""

from __future__ import annotations

from typing import Any, Final

CARDS_SCHEMA_VERSION: Final[str] = "mlops_cards/v1"

DISCLAIMER: Final[str] = (
    "> FloodGuard Penang is an independent, non-official research and portfolio "
    "project. It is not affiliated with, endorsed by, or a service of JPS "
    "(Department of Irrigation and Drainage Malaysia), MET Malaysia, NADMA or "
    "the Penang State Government. Its risk estimates are experimental model "
    "outputs, not official flood forecasts or warnings. Do not use FloodGuard "
    "for safety decisions."
)


def _kv_table(rows: list[tuple[str, str]]) -> str:
    lines = ["| Field | Value |", "|---|---|"]
    lines.extend(f"| {key} | {value} |" for key, value in rows)
    return "\n".join(lines)


def render_model_card(
    *,
    run: dict[str, Any],
    evaluation: dict[str, Any] | None,
    lineage_digest: str,
    limitations: list[str] | None = None,
    evaluation_source: str = "none provided",
) -> str:
    """Render a model card from stored run, evaluation and lineage records."""
    evidence = str(run.get("evidence_level", "UNKNOWN"))
    no_real_validation = evidence != "REAL_PREDICTIVE_EVALUATION"
    limits = list(limitations or [])
    if no_real_validation:
        limits.append(
            "No real predictive validation exists for this model; "
            "reported metrics are software checks or local diagnostics only."
        )
    sections = [
        f"# Model Card: {run.get('model_family', 'unknown')} ({run.get('run_id', 'unknown')})",
        "",
        DISCLAIMER,
        "",
        "## Intended Use",
        "",
        "FloodGuard Penang early-warning research for Pulau Pinang, Malaysia. "
        "Experimental decision support only; not an official warning service.",
        "",
        "## Training and Lineage",
        "",
        _kv_table(
            [
                ("Task", str(run.get("task", ""))),
                ("Model family", str(run.get("model_family", ""))),
                ("Horizon (min)", str(run.get("horizon_minutes", ""))),
                ("Dataset version", str(run.get("dataset_version", ""))),
                ("Split", str(run.get("split_definition", ""))),
                ("Random seed", str(run.get("random_seed", ""))),
                ("Device", str(run.get("device", ""))),
                ("Evidence level", evidence),
                ("Lineage digest", lineage_digest),
                ("Artifact ref", str(run.get("artifact_ref", ""))),
            ]
        ),
        "",
        "## Evaluation",
        "",
        f"_Evaluation source: {evaluation_source}._",
        "",
        _kv_table(
            [(k, str(v)) for k, v in sorted((evaluation or {"status": "NOT_EVALUATED"}).items())]
        ),
        "",
        "## Limitations",
        "",
        *(f"- {item}" for item in limits),
        "",
        f"_Card schema: {CARDS_SCHEMA_VERSION}. Generated offline from stored records._",
        "",
    ]
    return "\n".join(sections)


def render_dataset_card(
    *,
    lineage: dict[str, Any],
    coverage: dict[str, Any] | None = None,
    licensing: str = "JPS bulk historical retrieval remains PERMISSION REQUIRED.",
    limitations: list[str] | None = None,
) -> str:
    """Render a dataset card from a stored dataset lineage manifest."""
    limits = list(limitations or [])
    sections = [
        f"# Dataset Card: {lineage.get('dataset_version', 'unknown')}",
        "",
        DISCLAIMER,
        "",
        "## Provenance",
        "",
        _kv_table(
            [
                ("Dataset version", str(lineage.get("dataset_version", ""))),
                ("Observations hash", str(lineage.get("observations_hash", ""))),
                ("Source", str(lineage.get("source", ""))),
                ("Station scope", str(lineage.get("station_scope", ""))),
                ("Code version", str(lineage.get("code_version", ""))),
            ]
        ),
        "",
        "## Coverage",
        "",
        _kv_table([(k, str(v)) for k, v in sorted((coverage or {"status": "UNMEASURED"}).items())]),
        "",
        "## Licensing",
        "",
        licensing,
        "",
        "## Limitations",
        "",
        *(f"- {item}" for item in limits),
        "",
        f"_Card schema: {CARDS_SCHEMA_VERSION}. Generated offline from stored records._",
        "",
    ]
    return "\n".join(sections)
