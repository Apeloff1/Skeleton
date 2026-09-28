from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.intelligence.plan_verifier import (
    PlanStaticVerifierError,
    PlanStep,
    PlanVerificationPolicy,
    StaticPlanDefinition,
    admit_plan_execution,
    analyze_static_plan,
    qualify_static_plan,
    require_privileged_execution_admission,
    simulate_static_plan,
)
from skeleton.intelligence.strategy_registry import (
    ReasoningPolicy,
    ReasoningRisk,
    ReasoningStrategy,
    StopDisposition,
    StoppingDecision,
)


def _reasoning_policy() -> ReasoningPolicy:
    return ReasoningPolicy(
        policy_id="p1-plan-admission",
        version=1,
        allowed_strategies=(
            ReasoningStrategy.DIRECT,
            ReasoningStrategy.VERIFY,
        ),
        default_strategy=ReasoningStrategy.DIRECT,
        max_steps=4,
        max_tokens=4000,
        max_cost_units=8.0,
        max_wall_time_s=60.0,
        min_value_of_information=0.1,
        completion_confidence=0.85,
        max_uncertainty=0.5,
        max_stall_steps=2,
        require_verification_for_high_risk=True,
    )


def _verification_policy() -> PlanVerificationPolicy:
    return PlanVerificationPolicy(
        policy_id="p1-plan-admission-verifier",
        version=1,
        allowed_capabilities=("repo.read", "repo.write"),
        max_steps=4,
        max_total_tokens=4000,
        max_total_cost_units=8.0,
        max_total_wall_time_s=60.0,
        privileged_capabilities=("repo.write",),
    )


def _plan(*, postconditions=("repo.updated",)) -> StaticPlanDefinition:
    reasoning = _reasoning_policy()
    return StaticPlanDefinition(
        plan_id="privileged-plan",
        version=1,
        steps=(
            PlanStep(
                step_id="write",
                postconditions=postconditions,
                required_capabilities=("repo.write",),
                max_tokens=100,
                max_cost_units=1.0,
                max_wall_time_s=5.0,
                terminal=True,
                side_effect=True,
                recovery_plan_digest="a" * 64,
                rollback_test_digest="b" * 64,
            ),
        ),
        initial_facts=(),
        reasoning_policy_digest=reasoning.digest,
        planning_history_digest="c" * 64,
        risk=ReasoningRisk.LOW,
    )


def _qualified(plan: StaticPlanDefinition):
    reasoning = _reasoning_policy()
    verifier = _verification_policy()
    analysis = analyze_static_plan(plan, verifier)
    simulation = simulate_static_plan(
        plan,
        analysis,
        available_capabilities=("repo.read", "repo.write"),
    )
    stopping = StoppingDecision(
        disposition=StopDisposition.COMPLETE,
        reason="plan-finished",
        policy_digest=reasoning.digest,
        history_digest=plan.planning_history_digest,
        steps_remaining=1,
        tokens_remaining=100,
        cost_remaining=1.0,
        time_remaining_s=5.0,
    )
    qualification = qualify_static_plan(
        plan=plan,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=analysis,
        simulation=simulation,
        stopping=stopping,
    )
    return verifier, qualification


def test_privileged_step_requires_exact_qualified_admission() -> None:
    plan = _plan()
    verifier, qualification = _qualified(plan)
    assert qualification.accepted is True

    admission = admit_plan_execution(
        plan=plan,
        verification_policy=verifier,
        qualification=qualification,
        planner_id="planner:intel-05",
        planner_digest="5" * 64,
        verifier_id="verifier:intel-05",
        verifier_digest="6" * 64,
        requested_step_ids=("write",),
    )

    assert admission.accepted is True
    assert admission.privileged_step_ids == ("write",)
    assert admission.required_capabilities == ("repo.write",)
    require_privileged_execution_admission(
        admission,
        plan=plan,
        step_id="write",
    )
    evidence = admission.accepted_evidence_ref()
    assert evidence.category == "plan_execution_admission"
    assert evidence.digest == admission.decision_digest


def test_rejected_plan_cannot_gain_privileged_admission() -> None:
    plan = _plan()
    verifier, qualification = _qualified(plan)
    rejected = replace(
        qualification,
        accepted=False,
        reasons=("forced-rejection",),
    )

    admission = admit_plan_execution(
        plan=plan,
        verification_policy=verifier,
        qualification=rejected,
        planner_id="planner:intel-05",
        planner_digest="5" * 64,
        verifier_id="verifier:intel-05",
        verifier_digest="6" * 64,
        requested_step_ids=("write",),
    )

    assert admission.accepted is False
    assert "plan-qualification-rejected" in admission.reasons
    with pytest.raises(
        PlanStaticVerifierError,
        match="admission rejected",
    ):
        require_privileged_execution_admission(
            admission,
            plan=plan,
            step_id="write",
        )


def test_under_specified_privileged_step_is_not_admitted() -> None:
    plan = _plan(postconditions=())
    verifier, qualification = _qualified(plan)
    assert qualification.accepted is True

    admission = admit_plan_execution(
        plan=plan,
        verification_policy=verifier,
        qualification=qualification,
        planner_id="planner:intel-05",
        planner_digest="5" * 64,
        verifier_id="verifier:intel-05",
        verifier_digest="6" * 64,
        requested_step_ids=("write",),
    )

    assert admission.accepted is False
    assert (
        "privileged-step-postcondition-missing:write"
        in admission.reasons
    )


def test_execution_admission_is_step_scoped() -> None:
    reasoning = _reasoning_policy()
    verifier = _verification_policy()
    plan = StaticPlanDefinition(
        plan_id="scoped-plan",
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
                postconditions=("repo.updated",),
                required_capabilities=("repo.write",),
                terminal=True,
                side_effect=True,
                recovery_plan_digest="a" * 64,
                rollback_test_digest="b" * 64,
            ),
        ),
        initial_facts=(),
        reasoning_policy_digest=reasoning.digest,
        planning_history_digest="c" * 64,
        risk=ReasoningRisk.LOW,
    )
    analysis = analyze_static_plan(plan, verifier)
    simulation = simulate_static_plan(
        plan,
        analysis,
        available_capabilities=("repo.read", "repo.write"),
    )
    stopping = StoppingDecision(
        disposition=StopDisposition.COMPLETE,
        reason="plan-finished",
        policy_digest=reasoning.digest,
        history_digest=plan.planning_history_digest,
        steps_remaining=1,
        tokens_remaining=100,
        cost_remaining=1.0,
        time_remaining_s=5.0,
    )
    qualification = qualify_static_plan(
        plan=plan,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=analysis,
        simulation=simulation,
        stopping=stopping,
    )
    admission = admit_plan_execution(
        plan=plan,
        verification_policy=verifier,
        qualification=qualification,
        planner_id="planner:intel-05",
        planner_digest="5" * 64,
        verifier_id="verifier:intel-05",
        verifier_digest="6" * 64,
        requested_step_ids=("inspect",),
    )

    with pytest.raises(
        PlanStaticVerifierError,
        match="outside execution admission",
    ):
        require_privileged_execution_admission(
            admission,
            plan=plan,
            step_id="write",
        )


def test_stale_plan_digest_cannot_reuse_admission() -> None:
    plan = _plan()
    verifier, qualification = _qualified(plan)
    admission = admit_plan_execution(
        plan=plan,
        verification_policy=verifier,
        qualification=qualification,
        planner_id="planner:intel-05",
        planner_digest="5" * 64,
        verifier_id="verifier:intel-05",
        verifier_digest="6" * 64,
        requested_step_ids=("write",),
    )
    changed = StaticPlanDefinition(
        plan_id=plan.plan_id,
        version=2,
        steps=plan.steps,
        initial_facts=plan.initial_facts,
        reasoning_policy_digest=plan.reasoning_policy_digest,
        planning_history_digest=plan.planning_history_digest,
        risk=plan.risk,
    )

    with pytest.raises(
        PlanStaticVerifierError,
        match="plan mismatch",
    ):
        require_privileged_execution_admission(
            admission,
            plan=changed,
            step_id="write",
        )
