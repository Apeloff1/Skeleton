from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.intelligence.plan_static_analyzer import (
    ExecutionPlanSpec,
    FailurePolicy,
    PlanBudget,
    PlanStaticAnalysisError,
    PlanStepSpec,
    analyze_plan,
)
from skeleton.intelligence.strategy_registry import (
    ReasoningPolicy,
    ReasoningStrategy,
)


def _policy(**overrides) -> ReasoningPolicy:
    values = {
        "policy_id": "p1.reasoning",
        "version": 1,
        "allowed_strategies": (
            ReasoningStrategy.DIRECT,
            ReasoningStrategy.VERIFY,
        ),
        "default_strategy": ReasoningStrategy.DIRECT,
        "max_steps": 6,
        "max_tokens": 1000,
        "max_cost_units": 10.0,
        "max_wall_time_s": 60.0,
        "min_value_of_information": 0.1,
        "completion_confidence": 0.8,
        "max_uncertainty": 0.2,
        "max_stall_steps": 2,
        "require_verification_for_high_risk": True,
    }
    values.update(overrides)
    return ReasoningPolicy(**values)


def _budget(**overrides) -> PlanBudget:
    values = {
        "max_steps": 4,
        "max_tokens": 600,
        "max_cost_units": 6.0,
        "max_wall_time_s": 40.0,
        "max_retries_per_step": 2,
    }
    values.update(overrides)
    return PlanBudget(**values)


def _steps() -> tuple[PlanStepSpec, ...]:
    return (
        PlanStepSpec(
            step_id="prepare",
            depends_on=(),
            required_capabilities=("read",),
            preconditions=("operation authorized",),
            postconditions=("context ready",),
            max_tokens=100,
            max_cost_units=1.0,
            max_wall_time_s=5.0,
        ),
        PlanStepSpec(
            step_id="apply",
            depends_on=("prepare",),
            required_capabilities=("write",),
            preconditions=("context ready",),
            postconditions=("mutation committed",),
            max_tokens=200,
            max_cost_units=2.0,
            max_wall_time_s=10.0,
            failure_policy=FailurePolicy.COMPENSATE,
            side_effecting=True,
            idempotent=False,
            recovery_action="rollback.apply",
        ),
        PlanStepSpec(
            step_id="finalize",
            depends_on=("apply",),
            required_capabilities=("verify",),
            preconditions=("mutation committed",),
            postconditions=("postcondition verified",),
            max_tokens=100,
            max_cost_units=1.0,
            max_wall_time_s=5.0,
            terminal=True,
        ),
    )


def _plan(**overrides) -> ExecutionPlanSpec:
    policy = _policy()
    values = {
        "plan_id": "plan.p1.valid",
        "reasoning_policy_digest": policy.digest,
        "allowed_capabilities": ("read", "write", "verify"),
        "budget": _budget(),
        "steps": _steps(),
    }
    values.update(overrides)
    return ExecutionPlanSpec(**values)


def test_valid_plan_is_accepted_and_evidence_bearing() -> None:
    policy = _policy()
    decision = analyze_plan(_plan(), reasoning_policy=policy)

    assert decision.accepted is True
    assert decision.findings == ()
    assert decision.step_count == 3
    assert decision.terminal_count == 1
    assert decision.aggregate_tokens == 400
    assert decision.aggregate_cost_units == 4.0
    assert decision.critical_path_wall_time_s == 20.0
    evidence = decision.evidence_ref()
    assert evidence.category == "plan_static_analysis"
    assert evidence.digest == decision.decision_digest


def test_plan_digest_is_independent_of_input_step_order() -> None:
    steps = _steps()
    assert _plan(steps=steps).digest == _plan(steps=tuple(reversed(steps))).digest


def test_reasoning_policy_digest_must_match_exactly() -> None:
    decision = analyze_plan(
        _plan(reasoning_policy_digest="f" * 64),
        reasoning_policy=_policy(),
    )
    assert decision.accepted is False
    assert "policy:digest-mismatch" in decision.findings


@pytest.mark.parametrize(
    ("budget", "finding"),
    (
        (_budget(max_steps=7), "budget:steps-exceed-reasoning-policy"),
        (_budget(max_tokens=1001), "budget:tokens-exceed-reasoning-policy"),
        (_budget(max_cost_units=10.1), "budget:cost-exceeds-reasoning-policy"),
        (_budget(max_wall_time_s=60.1), "budget:wall-time-exceeds-reasoning-policy"),
    ),
)
def test_plan_budget_cannot_widen_reasoning_policy(
    budget: PlanBudget,
    finding: str,
) -> None:
    decision = analyze_plan(_plan(budget=budget), reasoning_policy=_policy())
    assert decision.accepted is False
    assert finding in decision.findings


def test_unknown_dependency_and_cycle_fail_closed() -> None:
    steps = list(_steps())
    steps[0] = replace(steps[0], depends_on=("missing",))
    decision = analyze_plan(
        _plan(steps=tuple(steps)),
        reasoning_policy=_policy(),
    )
    assert "graph:unknown-dependency:prepare:missing" in decision.findings

    steps = list(_steps())
    steps[0] = replace(steps[0], depends_on=("finalize",))
    decision = analyze_plan(
        _plan(steps=tuple(steps)),
        reasoning_policy=_policy(),
    )
    assert "graph:cycle" in decision.findings


def test_duplicate_step_identity_fails_closed() -> None:
    first = _steps()[0]
    decision = analyze_plan(
        _plan(steps=(first, first, _steps()[2])),
        reasoning_policy=_policy(),
    )
    assert "graph:duplicate-step:prepare" in decision.findings


def test_capability_widening_fails_closed() -> None:
    steps = list(_steps())
    steps[1] = replace(
        steps[1],
        required_capabilities=("admin", "write"),
    )
    decision = analyze_plan(
        _plan(steps=tuple(steps)),
        reasoning_policy=_policy(),
    )
    assert "authority:capability-widening:apply:admin" in decision.findings


def test_preconditions_and_postconditions_are_required() -> None:
    steps = list(_steps())
    steps[0] = replace(steps[0], preconditions=())
    steps[2] = replace(steps[2], postconditions=())
    decision = analyze_plan(
        _plan(steps=tuple(steps)),
        reasoning_policy=_policy(),
    )
    assert "contract:missing-preconditions:prepare" in decision.findings
    assert "contract:missing-postconditions:finalize" in decision.findings


def test_aggregate_token_and_cost_budgets_fail_closed() -> None:
    decision = analyze_plan(
        _plan(budget=_budget(max_tokens=300, max_cost_units=3.5)),
        reasoning_policy=_policy(),
    )
    assert "budget:aggregate-tokens-exceeded" in decision.findings
    assert "budget:aggregate-cost-exceeded" in decision.findings


def test_critical_path_wall_time_is_bounded() -> None:
    decision = analyze_plan(
        _plan(budget=_budget(max_wall_time_s=15.0)),
        reasoning_policy=_policy(),
    )
    assert "budget:critical-path-wall-time-exceeded" in decision.findings


def test_retry_requires_idempotency_and_bounded_attempts() -> None:
    steps = list(_steps())
    steps[0] = replace(
        steps[0],
        failure_policy=FailurePolicy.RETRY,
        max_retries=1,
        idempotent=False,
    )
    decision = analyze_plan(
        _plan(steps=tuple(steps)),
        reasoning_policy=_policy(),
    )
    assert "recovery:retry-non-idempotent:prepare" in decision.findings

    steps[0] = replace(steps[0], idempotent=True, max_retries=3)
    decision = analyze_plan(
        _plan(steps=tuple(steps)),
        reasoning_policy=_policy(),
    )
    assert "recovery:retry-budget-exceeded:prepare" in decision.findings


def test_side_effect_requires_compensation_and_recovery_action() -> None:
    steps = list(_steps())
    steps[1] = replace(
        steps[1],
        failure_policy=FailurePolicy.ABORT,
        recovery_action=None,
    )
    decision = analyze_plan(
        _plan(steps=tuple(steps)),
        reasoning_policy=_policy(),
    )
    assert "recovery:side-effect-without-compensation:apply" in decision.findings
    assert "recovery:missing-recovery-action:apply" in decision.findings


def test_terminal_nodes_must_be_sinks_and_all_sinks_terminal() -> None:
    steps = list(_steps())
    steps[1] = replace(steps[1], terminal=True)
    decision = analyze_plan(
        _plan(steps=tuple(steps)),
        reasoning_policy=_policy(),
    )
    assert "graph:terminal-has-dependent:apply" in decision.findings

    steps = list(_steps())
    steps[2] = replace(steps[2], terminal=False)
    decision = analyze_plan(
        _plan(steps=tuple(steps)),
        reasoning_policy=_policy(),
    )
    assert "graph:no-terminal-step" in decision.findings
    assert "graph:sink-not-terminal:finalize" in decision.findings


def test_rejected_analysis_cannot_emit_promotion_evidence() -> None:
    decision = analyze_plan(
        _plan(reasoning_policy_digest="f" * 64),
        reasoning_policy=_policy(),
    )
    with pytest.raises(PlanStaticAnalysisError, match="cannot become promotion evidence"):
        decision.evidence_ref()
