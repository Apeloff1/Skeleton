from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.research_evaluation import ExperimentRun
from skeleton.ai.runtime.deferred.research_evaluation_assurance import compare_experiment_runs


A = "a" * 64
B = "b" * 64


def run(
    run_id: str,
    *,
    dataset: str = A,
    metric: str = "accuracy",
    value: float = 0.5,
    seed: int = 1,
) -> ExperimentRun:
    return ExperimentRun(
        run_id,
        "experiment-1",
        dataset,
        B,
        metric,
        value,
        seed,
    )


def test_experiment_comparison_requires_matching_identity_surface() -> None:
    evidence = compare_experiment_runs(
        run("base", value=0.5),
        run("candidate", value=0.7),
    )
    assert evidence.eligible is True
    assert evidence.delta == pytest.approx(0.2)
    assert evidence.reason_code == "eligible"


def test_experiment_comparison_blocks_dataset_or_seed_mismatch() -> None:
    dataset_mismatch = compare_experiment_runs(
        run("base"),
        run("candidate", dataset="c" * 64),
    )
    assert dataset_mismatch.eligible is False
    assert dataset_mismatch.reason_code == "identity-mismatch"
    assert dataset_mismatch.delta is None

    seed_mismatch = compare_experiment_runs(
        run("base", seed=1),
        run("candidate", seed=2),
        require_same_seed=True,
    )
    assert seed_mismatch.eligible is False
    assert seed_mismatch.reason_code == "seed-mismatch"
