from __future__ import annotations

import pytest

from skeleton.ai.runtime.observability.latency_budget import (
    LatencyAssessment,
    LatencyBudget,
    LatencyBudgetError,
    LatencyObservation,
    LatencyStage,
    assess_latency,
)


def _budget() -> LatencyBudget:
    return LatencyBudget(
        budget_id="assistant-chat-prod",
        operation_class="assistant.chat",
        environment_id="prod-cpu",
        p95_ms=500.0,
        p99_ms=800.0,
        stages=(
            LatencyStage("admission", 50.0),
            LatencyStage("inference", 600.0),
            LatencyStage("render", 100.0),
        ),
    )


def _observation(
    *,
    p95: float = 450.0,
    p99: float = 700.0,
    retry_count: int = 0,
    stages: dict[str, float] | None = None,
) -> LatencyObservation:
    return LatencyObservation(
        observation_id="obs-1",
        operation_class="assistant.chat",
        environment_id="prod-cpu",
        p95_ms=p95,
        p99_ms=p99,
        stage_ms=stages or {
            "admission": 40.0,
            "inference": 550.0,
            "render": 80.0,
        },
        retry_count=retry_count,
    )


def test_latency_budget_accepts_matching_observation() -> None:
    budget = _budget()
    observation = _observation()

    result = assess_latency(
        budget=budget,
        observation=observation,
    )

    assert result.exhausted is False
    assert result.reasons == ()
    assert result.retry_override is False
    assert result.budget_digest == budget.digest
    assert result.observation_digest == observation.digest


def test_latency_budget_reports_percentile_breaches() -> None:
    result = assess_latency(
        budget=_budget(),
        observation=_observation(p95=550.0, p99=900.0),
    )

    assert result.exhausted is True
    assert result.reasons == (
        "p95-budget-exceeded",
        "p99-budget-exceeded",
    )


def test_latency_budget_reports_stage_breach() -> None:
    result = assess_latency(
        budget=_budget(),
        observation=_observation(
            stages={
                "admission": 40.0,
                "inference": 650.0,
                "render": 80.0,
            }
        ),
    )

    assert result.exhausted is True
    assert result.reasons == (
        "stage-budget-exceeded:inference",
    )


def test_retries_never_hide_tail_latency_breach() -> None:
    result = assess_latency(
        budget=_budget(),
        observation=_observation(
            p95=550.0,
            p99=900.0,
            retry_count=3,
        ),
    )

    assert result.exhausted is True
    assert result.retry_count == 3
    assert "p99-budget-exceeded" in result.reasons
    assert result.retry_override is False


def test_latency_budget_rejects_stage_oversubscription() -> None:
    with pytest.raises(
        LatencyBudgetError,
        match="cannot oversubscribe p99",
    ):
        LatencyBudget(
            budget_id="oversubscribed",
            operation_class="assistant.chat",
            environment_id="prod-cpu",
            p95_ms=500.0,
            p99_ms=800.0,
            stages=(
                LatencyStage("admission", 200.0),
                LatencyStage("inference", 700.0),
            ),
        )


def test_latency_budget_rejects_duplicate_stage_ids() -> None:
    with pytest.raises(
        LatencyBudgetError,
        match="stage IDs must be unique",
    ):
        LatencyBudget(
            budget_id="duplicate-stage",
            operation_class="assistant.chat",
            environment_id="prod-cpu",
            p95_ms=500.0,
            p99_ms=800.0,
            stages=(
                LatencyStage("inference", 300.0),
                LatencyStage("inference", 300.0),
            ),
        )


def test_latency_observation_requires_exact_stage_coverage() -> None:
    missing = assess_latency(
        budget=_budget(),
        observation=_observation(
            stages={
                "admission": 40.0,
                "inference": 550.0,
            }
        ),
    )
    assert missing.exhausted is True
    assert missing.reasons == ("missing-stages:render",)

    extra = assess_latency(
        budget=_budget(),
        observation=_observation(
            stages={
                "admission": 40.0,
                "inference": 550.0,
                "render": 80.0,
                "cache": 5.0,
            }
        ),
    )
    assert extra.exhausted is True
    assert extra.reasons == ("unknown-stages:cache",)


def test_latency_observation_must_match_budget_identity() -> None:
    wrong = LatencyObservation(
        observation_id="wrong-env",
        operation_class="assistant.chat",
        environment_id="staging-cpu",
        p95_ms=450.0,
        p99_ms=700.0,
        stage_ms={
            "admission": 40.0,
            "inference": 550.0,
            "render": 80.0,
        },
    )

    with pytest.raises(
        LatencyBudgetError,
        match="operation/environment identity",
    ):
        assess_latency(
            budget=_budget(),
            observation=wrong,
        )


def test_p99_cannot_be_below_p95() -> None:
    with pytest.raises(
        LatencyBudgetError,
        match="p99 budget cannot be below p95",
    ):
        LatencyBudget(
            budget_id="bad-percentiles",
            operation_class="assistant.chat",
            environment_id="prod-cpu",
            p95_ms=900.0,
            p99_ms=800.0,
            stages=(LatencyStage("inference", 700.0),),
        )

    with pytest.raises(
        LatencyBudgetError,
        match="observed p99 cannot be below observed p95",
    ):
        LatencyObservation(
            observation_id="bad-observation",
            operation_class="assistant.chat",
            environment_id="prod-cpu",
            p95_ms=900.0,
            p99_ms=800.0,
            stage_ms={"inference": 700.0},
        )


def test_latency_assessment_cannot_claim_retry_override() -> None:
    with pytest.raises(
        LatencyBudgetError,
        match="retries cannot override latency violations",
    ):
        LatencyAssessment(
            budget_digest="a" * 64,
            observation_digest="b" * 64,
            exhausted=True,
            reasons=("p99-budget-exceeded",),
            retry_count=2,
            retry_override=True,
        )


def test_latency_assessment_rejects_forged_exhausted_flag() -> None:
    with pytest.raises(
        LatencyBudgetError,
        match="exhausted state must match violation reasons",
    ):
        LatencyAssessment(
            budget_digest="a" * 64,
            observation_digest="b" * 64,
            exhausted=False,
            reasons=("p99-budget-exceeded",),
            retry_count=0,
        )


def test_latency_values_reject_nan_and_negative() -> None:
    with pytest.raises(
        LatencyBudgetError,
        match="finite and positive",
    ):
        LatencyStage("inference", float("nan"))

    with pytest.raises(
        LatencyBudgetError,
        match="finite and non-negative",
    ):
        _observation(p95=-1.0, p99=1.0)
