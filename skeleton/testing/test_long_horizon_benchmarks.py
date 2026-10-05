from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.research_evaluation_assurance import (
    LongHorizonCheckpoint,
    ResearchEvaluationAssuranceError,
    assess_long_horizon,
)


A = "a" * 64
B = "b" * 64


def test_long_horizon_acceptance_requires_stable_authority_and_progress() -> None:
    result = assess_long_horizon(
        "benchmark-1",
        max_steps=100,
        checkpoints=(
            LongHorizonCheckpoint(10, A, B, 0.2),
            LongHorizonCheckpoint(50, B, B, 0.6, recovered=True),
            LongHorizonCheckpoint(100, A, B, 1.0),
        ),
        completed=True,
    )
    assert result.authority_stable is True
    assert result.progress_monotonic is True
    assert result.recovery_count == 1
    assert result.acceptance_eligible is True


def test_long_horizon_rejects_authority_drift_or_progress_regression() -> None:
    authority = assess_long_horizon(
        "benchmark",
        max_steps=10,
        checkpoints=(
            LongHorizonCheckpoint(1, A, A, 0.5),
            LongHorizonCheckpoint(2, B, B, 0.6),
        ),
        completed=True,
    )
    assert authority.acceptance_eligible is False
    assert authority.authority_stable is False

    progress = assess_long_horizon(
        "benchmark",
        max_steps=10,
        checkpoints=(
            LongHorizonCheckpoint(1, A, A, 0.6),
            LongHorizonCheckpoint(2, B, A, 0.5),
        ),
        completed=True,
    )
    assert progress.acceptance_eligible is False
    assert progress.progress_monotonic is False


def test_long_horizon_step_budget_is_enforced() -> None:
    with pytest.raises(ResearchEvaluationAssuranceError, match="exceeds"):
        assess_long_horizon(
            "benchmark",
            max_steps=10,
            checkpoints=(LongHorizonCheckpoint(11, A, A, 1.0),),
            completed=True,
        )
