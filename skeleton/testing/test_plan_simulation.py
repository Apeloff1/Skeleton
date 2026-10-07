from __future__ import annotations

from dataclasses import replace

from skeleton.intelligence.plan_verifier import (
    PlanStep,
    PlanVerificationPolicy,
    SimulationDisposition,
    StaticPlanDefinition,
    analyze_static_plan,
    simulate_static_plan,
)
from skeleton.intelligence.strategy_registry import ReasoningRisk


def _policy() -> PlanVerificationPolicy:
    return PlanVerificationPolicy(
        policy_id="simulation-policy",
        version=1,
        allowed_capabilities=("repo.read", "repo.write", "tests.run"),
        max_steps=8,
        max_total_tokens=8000,
        max_total_cost_units=20.0,
        max_total_wall_time_s=300.0,
    )


def _plan() -> StaticPlanDefinition:
    return StaticPlanDefinition(
        plan_id="simulation-plan",
        version=1,
        steps=(
            PlanStep(
                step_id="inspect",
                postconditions=("repo.inspected",),
                required_capabilities=("repo.read",),
            ),
            PlanStep(
                step_id="write",
                depends_on=("inspect",),
                preconditions=("repo.inspected",),
                postconditions=("change.applied",),
                required_capabilities=("repo.write",),
                side_effect=True,
                recovery_plan_digest="1" * 64,
                rollback_test_digest="2" * 64,
            ),
            PlanStep(
                step_id="verify",
                depends_on=("write",),
                preconditions=("change.applied",),
                postconditions=("tests.green",),
                required_capabilities=("tests.run",),
                terminal=True,
            ),
        ),
        initial_facts=(),
        reasoning_policy_digest="a" * 64,
        planning_history_digest="b" * 64,
        risk=ReasoningRisk.HIGH,
    )


def test_clean_simulation_reaches_terminal_facts() -> None:
    plan = _plan()
    analysis = analyze_static_plan(plan, _policy())
    simulation = simulate_static_plan(
        plan,
        analysis,
        available_capabilities=("repo.read", "repo.write", "tests.run"),
    )

    assert analysis.accepted is True
    assert simulation.accepted is True
    assert simulation.disposition is SimulationDisposition.COMPLETE
    assert simulation.executed_step_ids == ("inspect", "write", "verify")
    assert "tests.green" in simulation.final_facts


def test_failure_in_reversible_side_effect_is_recovered() -> None:
    plan = _plan()
    analysis = analyze_static_plan(plan, _policy())
    simulation = simulate_static_plan(
        plan,
        analysis,
        available_capabilities=("repo.read", "repo.write", "tests.run"),
        injected_failure_step_id="write",
    )

    assert simulation.accepted is True
    assert simulation.disposition is SimulationDisposition.RECOVERED_FAILURE
    assert simulation.recovered is True
    assert simulation.executed_step_ids == ("inspect", "write")
    assert "change.applied" not in simulation.final_facts


def test_failure_in_nonrecoverable_step_is_unsafe() -> None:
    plan = _plan()
    analysis = analyze_static_plan(plan, _policy())
    simulation = simulate_static_plan(
        plan,
        analysis,
        available_capabilities=("repo.read", "repo.write", "tests.run"),
        injected_failure_step_id="verify",
    )

    assert simulation.accepted is False
    assert simulation.disposition is SimulationDisposition.UNSAFE_FAILURE
    assert "unsafe-failure:verify" in simulation.reasons


def test_runtime_capability_drift_blocks_even_after_static_acceptance() -> None:
    plan = _plan()
    analysis = analyze_static_plan(plan, _policy())
    simulation = simulate_static_plan(
        plan,
        analysis,
        available_capabilities=("repo.read", "tests.run"),
    )

    assert simulation.accepted is False
    assert simulation.disposition is SimulationDisposition.BLOCKED
    assert "runtime-capability-missing:write:repo.write" in simulation.reasons


def test_stale_analysis_digest_is_rejected() -> None:
    plan = _plan()
    analysis = analyze_static_plan(plan, _policy())
    stale = replace(analysis, plan_digest="0" * 64)

    simulation = simulate_static_plan(
        plan,
        stale,
        available_capabilities=("repo.read", "repo.write", "tests.run"),
    )

    assert simulation.accepted is False
    assert "analysis-plan-digest-mismatch" in simulation.reasons
