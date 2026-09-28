from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.risk_evidence import RiskBindingEvaluation
from skeleton.intelligence.plan_verifier import (
    PlanExecutionAdmission,
    PlanStaticVerifierError,
    PlanStep,
    PlanVerificationPolicy,
    SimulationDisposition,
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
        policy_id="p1-intel-05-reasoning",
        version=1,
        allowed_strategies=(
            ReasoningStrategy.DIRECT,
            ReasoningStrategy.VERIFY,
        ),
        default_strategy=ReasoningStrategy.DIRECT,
        max_steps=6,
        max_tokens=6000,
        max_cost_units=12.0,
        max_wall_time_s=120.0,
        min_value_of_information=0.1,
        completion_confidence=0.85,
        max_uncertainty=0.5,
        max_stall_steps=2,
        require_verification_for_high_risk=True,
    )


def _stopping(policy: ReasoningPolicy, *, disposition=StopDisposition.COMPLETE):
    return StoppingDecision(
        disposition=disposition,
        reason="planning-finished",
        policy_digest=policy.digest,
        history_digest="b" * 64,
        steps_remaining=2,
        tokens_remaining=1000,
        cost_remaining=2.0,
        time_remaining_s=20.0,
    )


def _verification_policy() -> PlanVerificationPolicy:
    return PlanVerificationPolicy(
        policy_id="p1-intel-05-verifier",
        version=1,
        allowed_capabilities=("repo.read", "tests.run"),
        max_steps=4,
        max_total_tokens=3000,
        max_total_cost_units=10.0,
        max_total_wall_time_s=120.0,
    )


def _plan(policy: ReasoningPolicy, *, risk=ReasoningRisk.HIGH):
    return StaticPlanDefinition(
        plan_id="qualification-plan",
        version=1,
        steps=(
            PlanStep(
                step_id="inspect",
                postconditions=("repo.inspected",),
                required_capabilities=("repo.read",),
                max_tokens=400,
                max_cost_units=1.0,
                max_wall_time_s=10.0,
            ),
            PlanStep(
                step_id="verify",
                depends_on=("inspect",),
                preconditions=("repo.inspected",),
                postconditions=("verified",),
                required_capabilities=("tests.run",),
                max_tokens=600,
                max_cost_units=1.5,
                max_wall_time_s=20.0,
                terminal=True,
            ),
        ),
        initial_facts=(),
        reasoning_policy_digest=policy.digest,
        planning_history_digest="b" * 64,
        risk=risk,
    )


def _risk(*, severity="high", resolved=True, blockers=()):
    return RiskBindingEvaluation(
        obligation_id="P1-RISK-INTEL-05-deadbeefdeadbeef",
        obligation_digest="c" * 64,
        resolved=resolved,
        blocking=True,
        severity=severity,
        disposition="evidence",
        blockers=blockers,
    )


def _fixture(*, risk=ReasoningRisk.HIGH):
    reasoning = _reasoning_policy()
    stopping = _stopping(reasoning)
    verifier = _verification_policy()
    plan = _plan(reasoning, risk=risk)
    analysis = analyze_static_plan(plan, verifier)
    simulation = simulate_static_plan(
        plan,
        analysis,
        available_capabilities=("repo.read", "tests.run"),
    )
    return reasoning, stopping, verifier, plan, analysis, simulation


def test_high_risk_plan_qualifies_only_with_resolved_risk_binding() -> None:
    reasoning, stopping, verifier, plan, analysis, simulation = _fixture()

    missing = qualify_static_plan(
        plan=plan,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=analysis,
        simulation=simulation,
        stopping=stopping,
    )
    assert missing.accepted is False
    assert "risk-binding-missing" in missing.reasons

    accepted = qualify_static_plan(
        plan=plan,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=analysis,
        simulation=simulation,
        stopping=stopping,
        risk_evaluation=_risk(),
    )
    assert accepted.accepted is True
    evidence = accepted.accepted_evidence_ref()
    assert evidence.category == "plan_verification"
    assert evidence.digest == accepted.decision_digest


def test_low_and_medium_risk_do_not_require_evid04_binding() -> None:
    for risk in (ReasoningRisk.LOW, ReasoningRisk.MEDIUM):
        reasoning, stopping, verifier, plan, analysis, simulation = _fixture(
            risk=risk
        )
        decision = qualify_static_plan(
            plan=plan,
            verification_policy=verifier,
            reasoning_policy=reasoning,
            analysis=analysis,
            simulation=simulation,
            stopping=stopping,
        )
        assert decision.accepted is True


def test_intel03_policy_and_history_are_cryptographically_bound() -> None:
    reasoning, stopping, verifier, plan, analysis, simulation = _fixture()

    history_drift = replace(plan, planning_history_digest="0" * 64)
    decision = qualify_static_plan(
        plan=history_drift,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=analysis,
        simulation=simulation,
        stopping=stopping,
        risk_evaluation=_risk(),
    )
    assert decision.accepted is False
    assert "planning-history-digest-mismatch" in decision.reasons
    assert "analysis-plan-digest-mismatch" in decision.reasons

    stop_drift = replace(
        stopping,
        policy_digest="0" * 64,
    )
    decision = qualify_static_plan(
        plan=plan,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=analysis,
        simulation=simulation,
        stopping=stop_drift,
        risk_evaluation=_risk(),
    )
    assert decision.accepted is False
    assert "stopping-policy-digest-mismatch" in decision.reasons


def test_nonterminal_planning_search_cannot_qualify() -> None:
    reasoning, _, verifier, plan, analysis, simulation = _fixture()
    stopping = _stopping(
        reasoning,
        disposition=StopDisposition.CONTINUE,
    )
    decision = qualify_static_plan(
        plan=plan,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=analysis,
        simulation=simulation,
        stopping=stopping,
        risk_evaluation=_risk(),
    )

    assert decision.accepted is False
    assert "planning-search-not-complete" in decision.reasons


def test_rejected_static_or_simulation_result_cannot_qualify() -> None:
    reasoning, stopping, verifier, plan, analysis, simulation = _fixture()

    bad_analysis = replace(
        analysis,
        accepted=False,
        reasons=("forced-static-rejection",),
    )
    decision = qualify_static_plan(
        plan=plan,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=bad_analysis,
        simulation=simulation,
        stopping=stopping,
        risk_evaluation=_risk(),
    )
    assert decision.accepted is False
    assert "static-analysis-rejected" in decision.reasons
    assert "simulation-analysis-digest-mismatch" in decision.reasons

    bad_simulation = replace(
        simulation,
        accepted=False,
        disposition=SimulationDisposition.UNSAFE_FAILURE,
        reasons=("unsafe-failure:verify",),
        recovered=False,
    )
    decision = qualify_static_plan(
        plan=plan,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=analysis,
        simulation=bad_simulation,
        stopping=stopping,
        risk_evaluation=_risk(),
    )
    assert decision.accepted is False
    assert "simulation-rejected" in decision.reasons
    assert "simulation-unsafe-failure" in decision.reasons


def test_underclassified_or_unresolved_high_risk_binding_blocks() -> None:
    reasoning, stopping, verifier, plan, analysis, simulation = _fixture()

    under = qualify_static_plan(
        plan=plan,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=analysis,
        simulation=simulation,
        stopping=stopping,
        risk_evaluation=_risk(severity="medium"),
    )
    assert under.accepted is False
    assert "high-risk-classification-mismatch" in under.reasons

    unresolved = qualify_static_plan(
        plan=plan,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=analysis,
        simulation=simulation,
        stopping=stopping,
        risk_evaluation=_risk(
            resolved=False,
            blockers=("binding review is overdue",),
        ),
    )
    assert unresolved.accepted is False
    assert "risk-binding-unresolved" in unresolved.reasons


def test_rejected_qualification_cannot_materialize_promotion_evidence() -> None:
    reasoning, stopping, verifier, plan, analysis, simulation = _fixture()
    decision = qualify_static_plan(
        plan=plan,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=analysis,
        simulation=simulation,
        stopping=stopping,
    )
    assert decision.accepted is False
    with pytest.raises(PlanStaticVerifierError, match="cannot become promotion"):
        decision.accepted_evidence_ref()



def _privileged_fixture():
    reasoning = _reasoning_policy()
    stopping = _stopping(reasoning)
    verifier = PlanVerificationPolicy(
        policy_id="p1-intel-05-privileged",
        version=1,
        allowed_capabilities=(
            "repo.read",
            "repo.write",
            "tests.run",
        ),
        max_steps=4,
        max_total_tokens=3000,
        max_total_cost_units=10.0,
        max_total_wall_time_s=120.0,
    )
    plan = StaticPlanDefinition(
        plan_id="privileged-plan",
        version=1,
        steps=(
            PlanStep(
                step_id="inspect",
                postconditions=("repo.inspected",),
                required_capabilities=("repo.read",),
            ),
            PlanStep(
                step_id="apply",
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
                depends_on=("apply",),
                preconditions=("change.applied",),
                postconditions=("tests.green",),
                required_capabilities=("tests.run",),
                terminal=True,
            ),
        ),
        initial_facts=(),
        reasoning_policy_digest=reasoning.digest,
        planning_history_digest=stopping.history_digest,
        risk=ReasoningRisk.HIGH,
    )
    analysis = analyze_static_plan(plan, verifier)
    simulation = simulate_static_plan(
        plan,
        analysis,
        available_capabilities=(
            "repo.read",
            "repo.write",
            "tests.run",
        ),
    )
    qualification = qualify_static_plan(
        plan=plan,
        verification_policy=verifier,
        reasoning_policy=reasoning,
        analysis=analysis,
        simulation=simulation,
        stopping=stopping,
        risk_evaluation=_risk(),
    )
    return verifier, plan, qualification


def test_privileged_step_requires_exact_qualified_execution_admission() -> None:
    verifier, plan, qualification = _privileged_fixture()
    assert qualification.accepted is True

    admission = admit_plan_execution(
        plan=plan,
        verification_policy=verifier,
        qualification=qualification,
        requested_step_ids=("apply",),
        completed_step_ids=("inspect",),
    )

    assert isinstance(admission, PlanExecutionAdmission)
    assert admission.accepted is True
    assert admission.privileged_step_ids == ("apply",)
    assert admission.required_capabilities == ("repo.write",)
    require_privileged_execution_admission(
        admission,
        plan=plan,
        step_id="apply",
    )
    evidence = admission.accepted_evidence_ref()
    assert evidence.category == "plan_execution_admission"


def test_rejected_plan_cannot_admit_privileged_execution() -> None:
    verifier, plan, qualification = _privileged_fixture()
    rejected = replace(
        qualification,
        accepted=False,
        reasons=("forced-rejection",),
    )
    admission = admit_plan_execution(
        plan=plan,
        verification_policy=verifier,
        qualification=rejected,
        requested_step_ids=("apply",),
        completed_step_ids=("inspect",),
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
            step_id="apply",
        )


def test_execution_admission_is_bound_to_exact_plan_and_policy() -> None:
    verifier, plan, qualification = _privileged_fixture()
    drifted_plan = replace(
        plan,
        plan_id="privileged-plan-v2",
    )
    admission = admit_plan_execution(
        plan=drifted_plan,
        verification_policy=verifier,
        qualification=qualification,
        requested_step_ids=("apply",),
        completed_step_ids=("inspect",),
    )
    assert admission.accepted is False
    assert "qualification-plan-digest-mismatch" in admission.reasons

    drifted_policy = replace(
        verifier,
        max_total_tokens=verifier.max_total_tokens + 1,
    )
    admission = admit_plan_execution(
        plan=plan,
        verification_policy=drifted_policy,
        qualification=qualification,
        requested_step_ids=("apply",),
        completed_step_ids=("inspect",),
    )
    assert admission.accepted is False
    assert "qualification-policy-digest-mismatch" in admission.reasons


def test_under_specified_privileged_step_fails_admission() -> None:
    verifier, plan, qualification = _privileged_fixture()
    under_specified = replace(
        plan.steps[1],
        postconditions=(),
    )
    weakened = replace(
        plan,
        steps=(
            plan.steps[0],
            under_specified,
            plan.steps[2],
        ),
    )
    admission = admit_plan_execution(
        plan=weakened,
        verification_policy=verifier,
        qualification=qualification,
        requested_step_ids=("apply",),
        completed_step_ids=("inspect",),
    )
    assert admission.accepted is False
    assert (
        "privileged-step-postcondition-missing:apply"
        in admission.reasons
    )


def test_step_outside_admission_cannot_execute() -> None:
    verifier, plan, qualification = _privileged_fixture()
    admission = admit_plan_execution(
        plan=plan,
        verification_policy=verifier,
        qualification=qualification,
        requested_step_ids=("apply",),
        completed_step_ids=("inspect",),
    )

    with pytest.raises(
        PlanStaticVerifierError,
        match="outside execution admission",
    ):
        require_privileged_execution_admission(
            admission,
            plan=plan,
            step_id="verify",
        )



def test_privileged_execution_admission_requires_dependency_closure() -> None:
    verifier, plan, qualification = _privileged_fixture()
    admission = admit_plan_execution(
        plan=plan,
        verification_policy=verifier,
        qualification=qualification,
        requested_step_ids=("apply",),
    )

    assert admission.accepted is False
    assert (
        "execution-dependency-missing:apply:inspect"
        in admission.reasons
    )
