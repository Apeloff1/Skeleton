from __future__ import annotations

import hashlib

import pytest

from skeleton.agents.autonomy_control import (
    AutonomyAuthorization,
    AutonomyControlError,
    AutonomyLevel,
    AutonomyPolicy,
    AutonomySignal,
    AutonomyState,
    TransitionDisposition,
    evaluate_autonomy_transition,
)
from skeleton.agents.delegation_qualification import AgentDelegationDecision
from skeleton.contracts.canonical import EvidenceRef, canonical_json_bytes


NOW = 1_800_000_000.0


def _ref(source: str, char: str) -> EvidenceRef:
    return EvidenceRef(
        source=source,
        digest=char * 64,
        category="autonomy_authorization",
    )


def _delegation(*, accepted: bool = True) -> AgentDelegationDecision:
    return AgentDelegationDecision(
        accepted=accepted,
        reasons=() if accepted else ("delegation-rejected",),
        parent_authority_digest="a" * 64,
        child_authority_digest="b" * 64,
        handoff_digest="c" * 64,
        lease_fence_digest="d" * 64,
        live_lease_digest="e" * 64,
        observed_at=NOW - 10.0,
    )


def _state(
    delegation: AgentDelegationDecision,
    *,
    level: AutonomyLevel = AutonomyLevel.DELEGATED,
    delegation_digest: str | None = None,
) -> AutonomyState:
    return AutonomyState(
        operation_id="operation-1",
        execution_id="execution-1",
        agent_id="agent-1",
        level=level,
        delegation_digest=delegation_digest or delegation.decision_digest,
        version=3,
    )


def _authorization(
    state: AutonomyState,
    delegation: AgentDelegationDecision,
    *,
    to_level: AutonomyLevel = AutonomyLevel.AUTONOMOUS,
    expires_at: float = NOW + 300.0,
    independent: bool = True,
    operation_id: str | None = None,
    execution_id: str | None = None,
    agent_id: str | None = None,
    delegation_digest: str | None = None,
) -> AutonomyAuthorization:
    return AutonomyAuthorization(
        operation_id=operation_id or state.operation_id,
        execution_id=execution_id or state.execution_id,
        agent_id=agent_id or state.agent_id,
        from_level=state.level,
        to_level=to_level,
        delegation_digest=delegation_digest or delegation.decision_digest,
        issuer_id="human:operator-1",
        issuer_digest="f" * 64,
        expires_at=expires_at,
        evidence_refs=(_ref("approval://operator-1", "1"),),
        independent=independent,
    )


def _evaluate(
    *,
    level: AutonomyLevel = AutonomyLevel.DELEGATED,
    requested: AutonomyLevel | None = None,
    signal: AutonomySignal | None = None,
    accepted_delegation: bool = True,
    authorization: AutonomyAuthorization | None = None,
    state_delegation_digest: str | None = None,
    policy: AutonomyPolicy | None = None,
    observed_at: float = NOW,
):
    delegation = _delegation(accepted=accepted_delegation)
    state = _state(
        delegation,
        level=level,
        delegation_digest=state_delegation_digest,
    )
    return evaluate_autonomy_transition(
        state=state,
        requested_level=level if requested is None else requested,
        signal=signal or AutonomySignal(),
        delegation=delegation,
        observed_at=observed_at,
        authorization=authorization,
        policy=policy,
    )


def test_stable_level_holds_without_authority_change() -> None:
    decision = _evaluate()

    assert decision.accepted is True
    assert decision.disposition is TransitionDisposition.HOLD
    assert decision.from_level is AutonomyLevel.DELEGATED
    assert decision.next_level is AutonomyLevel.DELEGATED
    assert decision.reasons == ()


def test_manual_deescalation_never_requires_escalation_authorization() -> None:
    decision = _evaluate(requested=AutonomyLevel.SUGGEST)

    assert decision.accepted is True
    assert decision.disposition is TransitionDisposition.APPLY
    assert decision.next_level is AutonomyLevel.SUGGEST
    assert decision.authorization_digest is None


@pytest.mark.parametrize(
    ("signal", "expected", "reason"),
    (
        (
            AutonomySignal(uncertainty=0.55),
            AutonomyLevel.ASSISTED,
            "elevated-uncertainty",
        ),
        (
            AutonomySignal(uncertainty=0.90),
            AutonomyLevel.SUGGEST,
            "high-uncertainty",
        ),
        (
            AutonomySignal(failure_count=1),
            AutonomyLevel.ASSISTED,
            "execution-failure",
        ),
        (
            AutonomySignal(failure_count=2),
            AutonomyLevel.SUGGEST,
            "repeated-failure",
        ),
        (
            AutonomySignal(verification_failed=True),
            AutonomyLevel.ASSISTED,
            "verification-failed",
        ),
        (
            AutonomySignal(environment_degraded=True),
            AutonomyLevel.ASSISTED,
            "environment-degraded",
        ),
        (
            AutonomySignal(policy_violation=True),
            AutonomyLevel.OBSERVE,
            "policy-violation",
        ),
        (
            AutonomySignal(human_interrupt=True),
            AutonomyLevel.OBSERVE,
            "human-interrupt",
        ),
    ),
)
def test_adverse_signals_force_deescalation(
    signal: AutonomySignal,
    expected: AutonomyLevel,
    reason: str,
) -> None:
    decision = _evaluate(
        requested=AutonomyLevel.AUTONOMOUS,
        signal=signal,
    )

    assert decision.accepted is True
    assert decision.disposition is TransitionDisposition.FORCED_DEESCALATION
    assert decision.next_level is expected
    assert reason in decision.reasons


def test_invalid_delegation_forces_existing_authority_to_observe() -> None:
    decision = _evaluate(
        accepted_delegation=False,
        requested=AutonomyLevel.AUTONOMOUS,
    )

    assert decision.accepted is True
    assert decision.disposition is TransitionDisposition.FORCED_DEESCALATION
    assert decision.next_level is AutonomyLevel.OBSERVE
    assert "delegation-invalid" in decision.reasons


def test_state_delegation_mismatch_forces_existing_authority_to_observe() -> None:
    decision = _evaluate(
        state_delegation_digest="9" * 64,
        requested=AutonomyLevel.AUTONOMOUS,
    )

    assert decision.accepted is True
    assert decision.next_level is AutonomyLevel.OBSERVE
    assert "delegation-invalid" in decision.reasons


def test_observe_cannot_escalate_with_invalid_delegation() -> None:
    decision = _evaluate(
        level=AutonomyLevel.OBSERVE,
        requested=AutonomyLevel.SUGGEST,
        accepted_delegation=False,
    )

    assert decision.accepted is False
    assert decision.disposition is TransitionDisposition.BLOCKED
    assert decision.next_level is AutonomyLevel.OBSERVE
    assert decision.reasons == ("delegation-invalid",)


def test_escalation_requires_exact_authorization() -> None:
    decision = _evaluate(requested=AutonomyLevel.AUTONOMOUS)

    assert decision.accepted is False
    assert decision.disposition is TransitionDisposition.BLOCKED
    assert decision.next_level is AutonomyLevel.DELEGATED
    assert decision.reasons == ("escalation-authorization-missing",)


def test_exact_one_step_independent_authorization_allows_escalation() -> None:
    delegation = _delegation()
    state = _state(delegation)
    authorization = _authorization(state, delegation)

    decision = evaluate_autonomy_transition(
        state=state,
        requested_level=AutonomyLevel.AUTONOMOUS,
        signal=AutonomySignal(),
        delegation=delegation,
        observed_at=NOW,
        authorization=authorization,
    )

    assert decision.accepted is True
    assert decision.disposition is TransitionDisposition.APPLY
    assert decision.next_level is AutonomyLevel.AUTONOMOUS
    assert decision.authorization_digest == authorization.digest
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "autonomy_transition_qualification"
    assert evidence.digest == decision.decision_digest


def test_multi_level_escalation_is_blocked_even_with_no_adverse_signal() -> None:
    decision = _evaluate(
        level=AutonomyLevel.ASSISTED,
        requested=AutonomyLevel.AUTONOMOUS,
    )

    assert decision.accepted is False
    assert decision.reasons == ("escalation-step-too-large",)


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    (
        ({"expires_at": NOW}, "authorization-expired"),
        ({"independent": False}, "authorization-not-independent"),
        ({"operation_id": "other-operation"}, "authorization-operation-mismatch"),
        ({"execution_id": "other-execution"}, "authorization-execution-mismatch"),
        ({"agent_id": "other-agent"}, "authorization-agent-mismatch"),
        ({"delegation_digest": "8" * 64}, "authorization-delegation-mismatch"),
    ),
)
def test_escalation_authorization_is_exact_and_expiring(
    kwargs: dict,
    reason: str,
) -> None:
    delegation = _delegation()
    state = _state(delegation)
    authorization = _authorization(state, delegation, **kwargs)

    decision = evaluate_autonomy_transition(
        state=state,
        requested_level=AutonomyLevel.AUTONOMOUS,
        signal=AutonomySignal(),
        delegation=delegation,
        observed_at=NOW,
        authorization=authorization,
    )

    assert decision.accepted is False
    assert reason in decision.reasons
    assert decision.next_level is state.level


def test_policy_max_level_forces_deescalation() -> None:
    decision = _evaluate(
        requested=AutonomyLevel.AUTONOMOUS,
        policy=AutonomyPolicy(max_level=AutonomyLevel.ASSISTED),
    )

    assert decision.accepted is True
    assert decision.disposition is TransitionDisposition.FORCED_DEESCALATION
    assert decision.next_level is AutonomyLevel.ASSISTED
    assert "policy-max-level" in decision.reasons


def test_requested_level_above_policy_is_blocked_when_not_already_over_ceiling() -> None:
    delegation = _delegation()
    state = _state(delegation, level=AutonomyLevel.SUGGEST)
    policy = AutonomyPolicy(max_level=AutonomyLevel.ASSISTED)

    decision = evaluate_autonomy_transition(
        state=state,
        requested_level=AutonomyLevel.DELEGATED,
        signal=AutonomySignal(),
        delegation=delegation,
        observed_at=NOW,
        policy=policy,
    )

    assert decision.accepted is False
    assert decision.reasons == ("requested-level-exceeds-policy",)


def test_rejected_transition_cannot_become_promotion_evidence() -> None:
    decision = _evaluate(requested=AutonomyLevel.AUTONOMOUS)

    with pytest.raises(AutonomyControlError, match="cannot become"):
        decision.accepted_evidence_ref()


def test_observation_time_does_not_change_stable_accepted_identity() -> None:
    first = _evaluate(observed_at=NOW)
    second = _evaluate(observed_at=NOW + 10.0)

    assert first.accepted is True
    assert second.accepted is True
    assert first.decision_digest == second.decision_digest


def test_authorization_evidence_is_sorted_deduplicated_and_digest_stable() -> None:
    delegation = _delegation()
    state = _state(delegation)
    first = _ref("approval://a", "1")
    second = _ref("approval://b", "2")

    left = AutonomyAuthorization(
        operation_id=state.operation_id,
        execution_id=state.execution_id,
        agent_id=state.agent_id,
        from_level=state.level,
        to_level=AutonomyLevel.AUTONOMOUS,
        delegation_digest=delegation.decision_digest,
        issuer_id="human:operator-1",
        issuer_digest="f" * 64,
        expires_at=NOW + 300.0,
        evidence_refs=(first, second, first),
    )
    right = AutonomyAuthorization(
        operation_id=state.operation_id,
        execution_id=state.execution_id,
        agent_id=state.agent_id,
        from_level=state.level,
        to_level=AutonomyLevel.AUTONOMOUS,
        delegation_digest=delegation.decision_digest,
        issuer_id="human:operator-1",
        issuer_digest="f" * 64,
        expires_at=NOW + 300.0,
        evidence_refs=(second, first),
    )

    assert left.evidence_refs == right.evidence_refs
    assert left.digest == right.digest


def test_autonomy_identities_use_shared_canonical_contract_bytes() -> None:
    delegation = _delegation()
    state = _state(delegation)
    signal = AutonomySignal()
    policy = AutonomyPolicy()
    authorization = _authorization(state, delegation)

    decision = evaluate_autonomy_transition(
        state=state,
        requested_level=AutonomyLevel.AUTONOMOUS,
        signal=signal,
        delegation=delegation,
        observed_at=NOW,
        authorization=authorization,
        policy=policy,
    )

    assert state.digest == hashlib.sha256(canonical_json_bytes(state.payload())).hexdigest()
    assert signal.digest == hashlib.sha256(canonical_json_bytes(signal.payload())).hexdigest()
    assert policy.digest == hashlib.sha256(canonical_json_bytes(policy.payload())).hexdigest()
    assert authorization.digest == hashlib.sha256(
        canonical_json_bytes(authorization.payload())
    ).hexdigest()
    assert decision.decision_digest == hashlib.sha256(
        canonical_json_bytes(decision.payload())
    ).hexdigest()


def test_invalid_signal_policy_and_state_values_fail_closed() -> None:
    delegation = _delegation()

    with pytest.raises(AutonomyControlError, match="uncertainty"):
        AutonomySignal(uncertainty=float("nan"))
    with pytest.raises(AutonomyControlError, match="failure_count"):
        AutonomySignal(failure_count=-1)
    with pytest.raises(AutonomyControlError, match="uncertainty thresholds"):
        AutonomyPolicy(medium_uncertainty=0.8, high_uncertainty=0.7)
    with pytest.raises(AutonomyControlError, match="version"):
        AutonomyState(
            operation_id="operation-1",
            execution_id="execution-1",
            agent_id="agent-1",
            level=AutonomyLevel.ASSISTED,
            delegation_digest=delegation.decision_digest,
            version=0,
        )


def test_source_and_ai_autonomy_control_mirror_are_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    source = root / "skeleton/automation/agents/autonomy_control.py"
    mirror = root / "skeleton/ai/agents/core/autonomy_control.py"

    assert source.read_bytes() == mirror.read_bytes()
