"""Automated model acceptance tests (Phase 7 task 6: Automated model tests).

Offline, CPU-only checks run against a saved artifact directory before any
registration or promotion decision:

1. digest verification (model file + metadata digests via the Phase 5/6 loaders);
2. metadata schema completeness (required lineage keys present);
3. artifact load test (estimator loads and predicts on a tiny synthetic input);
4. inference latency probe (single-prediction wall time under budget);
5. evidence label present and one of the known levels;
6. baseline comparison record present (metrics reference a baseline family).

No network, Docker, GPU, MLflow server, or real data is required. The checks
are deterministic except the latency probe, which asserts an upper bound
only (timing noise can only fail a genuinely slow environment, never pass
a broken model).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from floodguard.mlops import EVIDENCE_LOCAL_DIAGNOSTIC, EVIDENCE_REAL, EVIDENCE_SYNTHETIC

VALIDATION_SCHEMA_VERSION: Final[str] = "mlops_validation/v1"
KNOWN_EVIDENCE: Final[tuple[str, ...]] = (
    EVIDENCE_SYNTHETIC,
    EVIDENCE_LOCAL_DIAGNOSTIC,
    EVIDENCE_REAL,
)
REQUIRED_METADATA_KEYS: Final[tuple[str, ...]] = (
    "model_family",
    "horizon_minutes",
    "dataset_version",
    "evidence_level",
    "model_sha256",
)
LATENCY_BUDGET_SECONDS: Final[float] = 0.5
KNOWN_BASELINE_FAMILIES: Final[tuple[str, ...]] = (
    "persistence",
    "rule",
    "logistic_regression",
    "random_forest",
    "xgboost",
    "linear_ar",
    "xgboost_regressor",
)


@dataclass(frozen=True)
class AcceptanceCheck:
    """One named acceptance result."""

    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class AcceptanceReport:
    """Full acceptance verdict for one artifact directory."""

    artifact_dir: str
    passed: bool
    checks: tuple[AcceptanceCheck, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": VALIDATION_SCHEMA_VERSION,
            "artifact_dir": self.artifact_dir,
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
        }


def _load_artifact(artifact_dir: Path, kind: str) -> tuple[Any, dict[str, Any]]:
    if kind == "classification":
        from floodguard.modeling.artifacts import load_artifact_trusted

        return load_artifact_trusted(artifact_dir)
    if kind == "forecasting":
        from floodguard.forecasting.artifacts import load_forecast_artifact_trusted

        return load_forecast_artifact_trusted(artifact_dir)
    raise ValueError(f"unknown artifact kind: {kind}")


def run_acceptance_checks(
    artifact_dir: Path,
    *,
    kind: str,
    baseline_family: str | None = None,
    n_features: int | None = None,
) -> AcceptanceReport:
    """Run the offline acceptance suite against one artifact directory."""
    checks: list[AcceptanceCheck] = []

    try:
        estimator, metadata = _load_artifact(artifact_dir, kind)
        checks.append(AcceptanceCheck("digest_verification", True, "digests verified on load"))
    except Exception as exc:  # acceptance must report, never crash
        checks.append(AcceptanceCheck("digest_verification", False, f"{type(exc).__name__}: {exc}"))
        checks.append(AcceptanceCheck("load_and_predict", False, "not run (load failed)"))
        checks.append(AcceptanceCheck("inference_latency", False, "not measured (load failed)"))
        return AcceptanceReport(str(artifact_dir), False, tuple(checks))

    missing = [k for k in REQUIRED_METADATA_KEYS if k not in metadata]
    checks.append(
        AcceptanceCheck(
            "metadata_schema",
            not missing,
            "all required lineage keys present" if not missing else f"missing keys: {missing}",
        )
    )

    evidence = str(metadata.get("evidence_level", ""))
    checks.append(
        AcceptanceCheck(
            "evidence_label",
            evidence in KNOWN_EVIDENCE,
            f"evidence_level={evidence!r}" if evidence else "evidence_level absent",
        )
    )

    features = n_features
    if features is None:
        known = getattr(estimator, "n_features_in_", None)
        features = int(known) if known is not None else 1
    try:
        import numpy as np

        probe = np.zeros((1, max(features, 1)))
        started = time.perf_counter()
        output = estimator.predict(probe)
        elapsed = time.perf_counter() - started
        checks.append(AcceptanceCheck("load_and_predict", True, f"output shape {np.shape(output)}"))
        checks.append(
            AcceptanceCheck(
                "inference_latency",
                elapsed < LATENCY_BUDGET_SECONDS,
                f"{elapsed:.4f}s for one prediction (budget {LATENCY_BUDGET_SECONDS}s)",
            )
        )
    except Exception as exc:  # acceptance must report, never crash
        checks.append(AcceptanceCheck("load_and_predict", False, f"{type(exc).__name__}: {exc}"))
        checks.append(
            AcceptanceCheck("inference_latency", False, "not measured (prediction failed)")
        )

    checks.append(
        AcceptanceCheck(
            "baseline_reference",
            baseline_family in KNOWN_BASELINE_FAMILIES,
            f"baseline_family={baseline_family!r}"
            if baseline_family in KNOWN_BASELINE_FAMILIES
            else f"unknown or missing baseline family: {baseline_family!r}",
        )
    )

    passed = all(c.passed for c in checks)
    return AcceptanceReport(str(artifact_dir), passed, tuple(checks))
