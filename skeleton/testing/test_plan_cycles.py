from __future__ import annotations

from skeleton.intelligence.plan_verifier import (
    PlanStep,
    PlanVerificationPolicy,
    StaticPlanDefinition,
    analyze_static_plan,
)
from skeleton.intelligence.strategy_registry import ReasoningRisk


def _policy() -> PlanVerificationPolicy:
    return PlanVerificationPolicy(
        policy_id="cycle-policy",
        version=1,
        allowed_capabilities=("repo.read",),
        max_steps=8,
        max_total_tokens=100,
        max_total_cost_units=10.0,
        max_total_wall_time_s=100.0,
    )


def _plan(steps: tuple[PlanStep, ...]) -> StaticPlanDefinition:
    return StaticPlanDefinition(
        plan_id="cycle-plan",
        version=1,
        steps=steps,
        initial_facts=(),
        reasoning_policy_digest="a" * 64,
        planning_history_digest="b" * 64,
        risk=ReasoningRisk.MEDIUM,
    )


def test_two_node_cycle_is_rejected_deterministically() -> None:
    decision = analyze_static_plan(
        _plan(
            (
                PlanStep(
                    step_id="a",
                    depends_on=("b",),
                    required_capabilities=("repo.read",),
                    terminal=True,
                ),
                PlanStep(
                    step_id="b",
                    depends_on=("a",),
                    required_capabilities=("repo.read",),
                    terminal=True,
                ),
            )
        ),
        _policy(),
    )

    assert decision.accepted is False
    assert "cycle-detected:a,b" in decision.reasons
    assert decision.topological_order == ()


def test_missing_dependency_is_named_exactly() -> None:
    decision = analyze_static_plan(
        _plan(
            (
                PlanStep(
                    step_id="execute",
                    depends_on=("missing",),
                    required_capabilities=("repo.read",),
                    terminal=True,
                ),
            )
        ),
        _policy(),
    )

    assert decision.accepted is False
    assert "missing-dependency:execute:missing" in decision.reasons


def test_disconnected_roots_are_allowed_when_every_leaf_is_terminal() -> None:
    decision = analyze_static_plan(
        _plan(
            (
                PlanStep(
                    step_id="left",
                    required_capabilities=("repo.read",),
                    terminal=True,
                ),
                PlanStep(
                    step_id="right",
                    required_capabilities=("repo.read",),
                    terminal=True,
                ),
            )
        ),
        _policy(),
    )

    assert decision.accepted is True
    assert decision.root_step_ids == ("left", "right")
    assert decision.leaf_step_ids == ("left", "right")
