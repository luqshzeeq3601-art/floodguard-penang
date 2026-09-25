"""Model registry + lineage tests: gated stages, digest-linked chains."""

from __future__ import annotations

from pathlib import Path

import pytest

from floodguard.mlops import GATE_PROMOTE, validate_segment
from floodguard.mlops.lineage import (
    DatasetLineage,
    ModelLineage,
    verify_model_lineage,
    write_dataset_lineage,
    write_model_lineage,
)
from floodguard.mlops.registry import list_versions, register, transition_stage

pytestmark = pytest.mark.usefixtures("no_network")


def test_register_versions_and_stage_rules(tmp_path: Path) -> None:
    first = register(
        tmp_path,
        name="wl-plus-30m",
        run_id="r1",
        artifact_dir="a",
        artifact_digest="d1",
        evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
        reason="t",
    )
    assert (first.version, first.stage) == (1, "none")
    second = register(
        tmp_path,
        name="wl-plus-30m",
        run_id="r2",
        artifact_dir="a",
        artifact_digest="d2",
        evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
        reason="t",
    )
    assert second.version == 2
    assert [v["version"] for v in list_versions(tmp_path, "wl-plus-30m")] == [1, 2]
    staged = transition_stage(
        tmp_path, name="wl-plus-30m", version=1, to_stage="staging", reason="smoke"
    )
    assert staged.stage == "staging"
    with pytest.raises(ValueError, match="register into staging first"):
        register(
            tmp_path,
            name="other",
            run_id="r",
            artifact_dir="a",
            artifact_digest=None,
            evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
            reason="t",
            stage="production",
        )


def test_production_requires_promote_and_real_evidence(tmp_path: Path) -> None:
    register(
        tmp_path,
        name="m",
        run_id="r",
        artifact_dir="a",
        artifact_digest="d",
        evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
        reason="t",
    )
    transition_stage(tmp_path, name="m", version=1, to_stage="staging", reason="s", at="t0")
    with pytest.raises(ValueError, match="recorded PROMOTE"):
        transition_stage(
            tmp_path,
            name="m",
            version=1,
            to_stage="production",
            reason="x",
            gate_verdict=None,
            at="t1",
        )
    # Synthetic evidence can stage but never produce, even with a verdict.
    with pytest.raises(ValueError, match="REAL_PREDICTIVE_EVALUATION"):
        transition_stage(
            tmp_path,
            name="m",
            version=1,
            to_stage="production",
            reason="x",
            gate_verdict=GATE_PROMOTE,
            at="t1",
        )
    register(
        tmp_path,
        name="m2",
        run_id="r",
        artifact_dir="a",
        artifact_digest="d",
        evidence_level="REAL_PREDICTIVE_EVALUATION",
        reason="t",
    )
    transition_stage(tmp_path, name="m2", version=1, to_stage="staging", reason="s", at="t0")
    with pytest.raises(ValueError, match="recorded PROMOTE"):
        transition_stage(
            tmp_path,
            name="m2",
            version=1,
            to_stage="production",
            reason="x",
            gate_verdict=None,
            at="t1",
        )
    moved = transition_stage(
        tmp_path,
        name="m2",
        version=1,
        to_stage="production",
        reason="gate passed",
        gate_verdict=GATE_PROMOTE,
        at="t2",
    )
    assert moved.stage == "production"


def test_archived_is_terminal(tmp_path: Path) -> None:
    register(
        tmp_path,
        name="m",
        run_id="r",
        artifact_dir="a",
        artifact_digest=None,
        evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
        reason="t",
    )
    transition_stage(tmp_path, name="m", version=1, to_stage="archived", reason="retired")
    with pytest.raises(ValueError, match="terminal"):
        transition_stage(tmp_path, name="m", version=1, to_stage="staging", reason="x")


def test_lineage_chain_verifies(tmp_path: Path) -> None:
    dataset = DatasetLineage(
        dataset_version="syn-v1",
        observations_hash="abc123",
        source="SYNTHETIC_TEST_ONLY",
        station_scope=("SYN_WL_A",),
        schema_versions={"forecast_dataset": "forecast_dataset/v1"},
        code_version="test",
    )
    manifest_path = write_dataset_lineage(tmp_path, dataset)
    assert manifest_path.is_file()
    model = ModelLineage(
        run_id="run1",
        model_family="linear_ar",
        dataset_digest=dataset.digest(),
        dataset_version="syn-v1",
        artifact_digest="m1",
    )
    write_model_lineage(tmp_path, model)
    ok, _ = verify_model_lineage(tmp_path, model)
    assert ok
    tampered = ModelLineage(
        run_id="run1",
        model_family="linear_ar",
        dataset_digest="0" * 64,
        dataset_version="syn-v1",
        artifact_digest="m1",
    )
    ok2, reason = verify_model_lineage(tmp_path, tampered)
    assert not ok2
    assert "no dataset manifest matches" in reason


def test_stage_edges_enforced_and_logged(tmp_path: Path) -> None:
    register(
        tmp_path,
        name="m",
        run_id="r",
        artifact_dir="a",
        artifact_digest=None,
        evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
        reason="t",
    )
    with pytest.raises(ValueError, match="forbidden stage transition"):
        transition_stage(tmp_path, name="m", version=1, to_stage="none", reason="x")
    transition_stage(tmp_path, name="m", version=1, to_stage="staging", reason="ok", at="t0")
    with pytest.raises(ValueError, match="forbidden stage transition"):
        transition_stage(tmp_path, name="m", version=1, to_stage="none", reason="demote")
    log_lines = (
        (tmp_path / "registry" / "transitions.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(log_lines) == 1
    assert '"to_stage": "staging"' in log_lines[0]


def test_unsafe_names_rejected(tmp_path: Path) -> None:
    for bad in ("..", ".", "a/b", "a\\b", "a:b", ""):
        with pytest.raises(ValueError, match="invalid"):
            validate_segment(bad, field="model name")
        with pytest.raises(ValueError, match=r"invalid|unknown"):
            list_versions(tmp_path, bad)
    with pytest.raises(ValueError, match="invalid"):
        register(
            tmp_path,
            name="..",
            run_id="r",
            artifact_dir="a",
            artifact_digest=None,
            evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
            reason="t",
        )


def test_list_versions_skips_non_version_files(tmp_path: Path) -> None:
    register(
        tmp_path,
        name="m",
        run_id="r",
        artifact_dir="a",
        artifact_digest=None,
        evidence_level="SYNTHETIC_SOFTWARE_VALIDATION",
        reason="t",
    )
    (tmp_path / "registry" / "m" / "vfoo.json").write_text("{}", encoding="utf-8")
    assert [v["version"] for v in list_versions(tmp_path, "m")] == [1]


def test_run_id_traversal_rejected(tmp_path: Path) -> None:
    from floodguard.mlops.experiments import get_run

    with pytest.raises(ValueError, match="invalid"):
        get_run(tmp_path, "../evil")


def test_conflicting_model_lineage_rejected(tmp_path: Path) -> None:
    model = ModelLineage(
        run_id="run1",
        model_family="linear_ar",
        dataset_digest="d",
        dataset_version="v",
        artifact_digest="m1",
    )
    write_model_lineage(tmp_path, model)
    altered = ModelLineage(
        run_id="run1",
        model_family="linear_ar",
        dataset_digest="d",
        dataset_version="v",
        artifact_digest="DIFFERENT",
    )
    with pytest.raises(ValueError, match="conflicting model lineage"):
        write_model_lineage(tmp_path, altered)
