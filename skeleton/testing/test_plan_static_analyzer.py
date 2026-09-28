from __future__ import annotations

import pytest

from skeleton.intelligence.plan_verifier import (
    PlanStaticVerifierError,
    PlanStep,
    PlanVerificationPolicy,
    StaticPlanDefinition,
    analyze_static_plan,
)
from skeleton.intelligence.strategy_registry import ReasoningRisk


def _policy(**overrides):
    values = {
        "policy_id": "p1-intel-05-test",
        "version": 1,
        "allowed_capabilities": ("repo.read", "tests.run", "repo.write"),
        "max_steps": 8,
        "max_total_tokens": 8000,
        "max_total_cost_units": 20.0,
        "max_total_wall_time_s": 300.0,
        "require_terminal_leaves": True,
        "allow_irreversible": False,
    }
    values.update(overrides)
    return PlanVerificationPolicy(**values)


def _plan(*, steps=None):
    return StaticPlanDefinition(
        plan_id="plan-1",
        version=1,
        steps=steps or (
            PlanStep(
                step_id="inspect",
                postconditions=("repo.inspected",),
                required_capabilities=("repo.read",),
                max_tokens=500,
                max_cost_units=1.0,
                max_wall_time_s=20.0,
            ),
            PlanStep(
                step_id="test",
                depends_on=("inspect",),
                preconditions=("repo.inspected",),
                postconditions=("tests.green",),
                required_capabilities=("tests.run",),
                max_tokens=1000,
                max_cost_units=2.0,
                max_wall_time_s=60.0,
            ),
            PlanStep(
                step_id="finish",
                depends_on=("test",),
                preconditions=("tests.green",),
                postconditions=("plan.complete",),
                required_capabilities=("repo.read",),
                max_tokens=100,
                max_cost_units=0.5,
                max_wall_time_s=5.0,
                terminal=True,
            ),
        ),
        initial_facts=("request.valid",),
        reasoning_policy_digest="a" * 64,
        planning_history_digest="b" * 64,
        risk=ReasoningRisk.MEDIUM,
    )


def test_accepts_deterministic_dag_and_dataflow() -> None:
    plan = _plan()
    decision = analyze_static_plan(plan, _policy())

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.topological_order == ("inspect", "test", "finish")
    assert decision.root_step_ids == ("inspect",)
    assert decision.leaf_step_ids == ("finish",)
    assert decision.terminal_step_ids == ("finish",)
    assert "plan.complete" in decision.produced_facts
    assert decision.required_capabilities == ("repo.read", "tests.run")


def test_precondition_must_come_from_initial_facts_or_dependency_ancestry() -> None:
    plan = _plan(
        steps=(
            PlanStep(
                step_id="a",
                postconditions=("a.ready",),
                required_capabilities=("repo.read",),
            ),
            PlanStep(
                step_id="b",
                postconditions=("shared.fact",),
                required_capabilities=("repo.read",),
            ),
            PlanStep(
                step_id="c",
                depends_on=("a",),
                preconditions=("shared.fact",),
                postconditions=("done",),
                required_capabilities=("repo.read",),
                terminal=True,
            ),
            PlanStep(
                step_id="b-terminal",
                depends_on=("b",),
                preconditions=("shared.fact",),
                postconditions=("b.done",),
                required_capabilities=("repo.read",),
                terminal=True,
            ),
        )
    )

    decision = analyze_static_plan(plan, _policy())
    assert decision.accepted is False
    assert "unsatisfied-preconditions:c:shared.fact" in decision.reasons


def test_capability_and_budget_overreach_fail_closed() -> None:
    plan = _plan(
        steps=(
            PlanStep(
                step_id="danger",
                required_capabilities=("secrets.read",),
                max_tokens=9000,
                max_cost_units=30.0,
                max_wall_time_s=400.0,
                terminal=True,
            ),
        )
    )
    decision = analyze_static_plan(plan, _policy())

    assert decision.accepted is False
    assert "capability-not-allowed:secrets.read" in decision.reasons
    assert "token-budget-exceeded" in decision.reasons
    assert "cost-budget-exceeded" in decision.reasons
    assert "wall-time-budget-exceeded" in decision.reasons


def test_terminal_contract_requires_every_leaf_to_be_terminal() -> None:
    plan = _plan(
        steps=(
            PlanStep(
                step_id="root",
                required_capabilities=("repo.read",),
            ),
            PlanStep(
                step_id="good",
                depends_on=("root",),
                required_capabilities=("repo.read",),
                terminal=True,
            ),
            PlanStep(
                step_id="forgotten",
                depends_on=("root",),
                required_capabilities=("repo.read",),
            ),
        )
    )
    decision = analyze_static_plan(plan, _policy())

    assert decision.accepted is False
    assert "nonterminal-leaves:forgotten" in decision.reasons


def test_terminal_step_cannot_have_dependents() -> None:
    plan = _plan(
        steps=(
            PlanStep(
                step_id="premature",
                required_capabilities=("repo.read",),
                terminal=True,
            ),
            PlanStep(
                step_id="after",
                depends_on=("premature",),
                required_capabilities=("repo.read",),
                terminal=True,
            ),
        )
    )
    decision = analyze_static_plan(plan, _policy())

    assert decision.accepted is False
    assert "terminal-step-has-dependents:premature" in decision.reasons


def test_irreversible_steps_require_explicit_policy_allowance() -> None:
    step = PlanStep(
        step_id="destroy",
        required_capabilities=("repo.write",),
        side_effect=True,
        irreversible=True,
        terminal=True,
    )
    plan = _plan(steps=(step,))

    blocked = analyze_static_plan(plan, _policy())
    assert blocked.accepted is False
    assert "irreversible-step-blocked:destroy" in blocked.reasons

    allowed = analyze_static_plan(
        plan,
        _policy(allow_irreversible=True),
    )
    assert allowed.accepted is True


def test_reversible_side_effect_requires_recovery_and_rollback_evidence() -> None:
    with pytest.raises(PlanStaticVerifierError, match="recovery_plan_digest"):
        PlanStep(
            step_id="write",
            side_effect=True,
            recovery_plan_digest=None,
            rollback_test_digest="1" * 64,
        )
    with pytest.raises(PlanStaticVerifierError, match="rollback_test_digest"):
        PlanStep(
            step_id="write",
            side_effect=True,
            recovery_plan_digest="1" * 64,
            rollback_test_digest=None,
        )


def test_plan_digest_is_independent_of_step_tuple_order() -> None:
    first = _plan()
    second = StaticPlanDefinition(
        plan_id=first.plan_id,
        version=first.version,
        steps=tuple(reversed(first.steps)),
        initial_facts=first.initial_facts,
        reasoning_policy_digest=first.reasoning_policy_digest,
        planning_history_digest=first.planning_history_digest,
        risk=first.risk,
    )
    assert first.digest == second.digest
