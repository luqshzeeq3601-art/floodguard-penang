"""MLOps experiment-store tests: deterministic, offline, digest-verified."""

from __future__ import annotations

import pytest

from floodguard.mlops.experiments import (
    ExperimentInput,
    deterministic_run_id,
    find_runs,
    get_run,
    log_run,
)

pytestmark = pytest.mark.usefixtures("no_network")


def _input(**overrides: object) -> ExperimentInput:
    fields: dict[str, object] = {
        "task": "forecasting",
        "model_family": "linear_ar",
        "horizon_minutes": 30,
        "dataset_version": "synthetic-forecast-v1",
        "evidence_level": "SYNTHETIC_SOFTWARE_VALIDATION",
    }
    fields.update(overrides)
    return ExperimentInput(**fields)  # type: ignore[arg-type]


def test_run_id_deterministic_and_write_once(tmp_path: object) -> None:
    from pathlib import Path

    store = Path(str(tmp_path))
    run_a = _input().to_run()
    run_b = _input().to_run()
    assert (
        run_a.run_id
        == run_b.run_id
        == deterministic_run_id(
            task="forecasting",
            model_family="linear_ar",
            horizon_minutes=30,
            dataset_version="synthetic-forecast-v1",
            params={},
            random_seed=42,
        )
    )
    first = log_run(store, run_a)
    second = log_run(store, run_b)
    assert first == second
    assert get_run(store, run_a.run_id)["run_id"] == run_a.run_id


def test_conflicting_record_rejected(tmp_path: object) -> None:
    from pathlib import Path

    store = Path(str(tmp_path))
    run = _input().to_run()
    log_run(store, run)
    (store / "experiments" / f"{run.run_id}.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        get_run(store, run.run_id)


def test_missing_digest_rejected(tmp_path: object) -> None:
    from pathlib import Path

    store = Path(str(tmp_path))
    run = _input().to_run()
    log_run(store, run)
    (store / "experiments" / f"{run.run_id}.sha256").unlink()
    with pytest.raises(ValueError, match="digest file missing"):
        get_run(store, run.run_id)


def test_find_runs_filters_and_verifies(tmp_path: object) -> None:
    from pathlib import Path

    store = Path(str(tmp_path))
    log_run(store, _input().to_run())
    log_run(store, _input(model_family="xgboost_regressor", horizon_minutes=60).to_run())
    assert len(find_runs(store, task="forecasting")) == 2
    assert len(find_runs(store, model_family="linear_ar")) == 1
    assert len(find_runs(store, horizon_minutes=60)) == 1
    assert find_runs(store, evidence_level="REAL_PREDICTIVE_EVALUATION") == []


def test_mlflow_tag_mapping_is_strings(tmp_path: object) -> None:
    from pathlib import Path

    _ = Path(str(tmp_path))
    tags = _input().to_run().to_mlflow_tags()
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in tags.items())
    assert tags["floodguard.evidence_level"] == "SYNTHETIC_SOFTWARE_VALIDATION"


def test_find_runs_skips_corrupt_files_and_audit_flags_them(tmp_path: object) -> None:
    from pathlib import Path

    from floodguard.mlops.experiments import audit_store

    store = Path(str(tmp_path))
    run = _input().to_run()
    log_run(store, run)
    (store / "experiments" / "broken.json").write_text("{not json", encoding="utf-8")
    assert [r["run_id"] for r in find_runs(store)] == [run.run_id]
    audit = audit_store(store)
    assert audit["verified"] == [f"{run.run_id}.json"]
    assert [s["file"] for s in audit["skipped"]] == ["broken.json"]


def test_non_json_params_rejected() -> None:
    with pytest.raises(ValueError, match="JSON-native"):
        _input(params={"model": object()}).to_run()


def test_model_filename_escape_rejected(tmp_path: object) -> None:
    from pathlib import Path

    from floodguard.forecasting.artifacts import load_forecast_artifact_trusted
    from floodguard.modeling.artifacts import load_artifact_trusted

    store = Path(str(tmp_path))
    with pytest.raises(ValueError, match="invalid model filename"):
        load_artifact_trusted(store, model_filename="../evil.joblib")
    with pytest.raises(ValueError, match="invalid model filename"):
        load_forecast_artifact_trusted(store, model_filename="sub/dir.joblib")
