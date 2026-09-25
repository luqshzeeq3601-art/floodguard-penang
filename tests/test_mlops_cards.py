"""Model/dataset card tests: deterministic output, honest evidence framing."""

from __future__ import annotations

import pytest

from floodguard.mlops.cards import DISCLAIMER, render_dataset_card, render_model_card

pytestmark = pytest.mark.usefixtures("no_network")


def _run(evidence: str = "SYNTHETIC_SOFTWARE_VALIDATION") -> dict[str, object]:
    return {
        "run_id": "abc123",
        "task": "forecasting",
        "model_family": "linear_ar",
        "horizon_minutes": 30,
        "dataset_version": "syn-v1",
        "split_definition": "s",
        "random_seed": 42,
        "device": "cpu",
        "evidence_level": evidence,
        "artifact_ref": {"model_sha256": "d" * 64},
    }


def test_model_card_states_no_real_validation() -> None:
    card = render_model_card(run=_run(), evaluation={"mae_m": 0.01}, lineage_digest="d")
    assert DISCLAIMER.split(".")[0] in card
    assert "No real predictive validation exists" in card
    assert "SYNTHETIC_SOFTWARE_VALIDATION" in card
    # Deterministic: identical inputs give identical cards.
    assert render_model_card(run=_run(), evaluation={"mae_m": 0.01}, lineage_digest="d") == card


def test_model_card_real_evidence_omits_warning() -> None:
    card = render_model_card(
        run=_run("REAL_PREDICTIVE_EVALUATION"), evaluation={}, lineage_digest="d"
    )
    assert "No real predictive validation exists" not in card
    assert "REAL_PREDICTIVE_EVALUATION" in card


def test_dataset_card_carries_licensing_and_provenance() -> None:
    lineage = {
        "dataset_version": "syn-v1",
        "observations_hash": "abc",
        "source": "SYNTHETIC_TEST_ONLY",
        "station_scope": ["SYN_WL_A"],
        "code_version": "test",
    }
    card = render_dataset_card(lineage=lineage, limitations=["tiny synthetic sample"])
    assert "PERMISSION REQUIRED" in card
    assert "syn-v1" in card
    assert "tiny synthetic sample" in card
    assert DISCLAIMER.split(".")[0] in card
