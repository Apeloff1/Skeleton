from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.agents.autonomy_control import (
    AutonomyLevel,
    AutonomySignal,
    AutonomyState,
    evaluate_autonomy_transition,
)
from skeleton.agents.delegation_qualification import AgentDelegationDecision
from skeleton.agents.human_control import (
    HumanControlAction,
    HumanControlCommand,
    HumanControlError,
    HumanControlState,
    evaluate_human_control,
)
from skeleton.contracts.canonical import EvidenceRef


NOW = 1_800_000_000.0


def _delegation() -> AgentDelegationDecision:
    return AgentDelegationDecision(
        accepted=True,
        reasons=(),
        parent_authority_digest="a" * 64,
        child_authority_digest="b" * 64,
        handoff_digest="c" * 64,
        lease_fence_digest="d" * 64,
        live_lease_digest="e" * 64,
        observed_at=NOW - 30.0,
    )


def _autonomy(
    delegation: AgentDelegationDecision,
    *,
    level: AutonomyLevel = AutonomyLevel.DELEGATED,
    version: int = 4,
) -> AutonomyState:
    return AutonomyState(
        operation_id="operation-1",
        execution_id="execution-1",
        agent_id="agent-1",
        level=level,
        delegation_digest=delegation.decision_digest,
        version=version,
    )


def _state(
    autonomy: AutonomyState,
    *,
    paused: bool = False,
    interrupted: bool = False,
    version: int = 7,
    last_receipt_digest: str | None = None,
) -> HumanControlState:
    return HumanControlState(
        operation_id=autonomy.operation_id,
        execution_id=autonomy.execution_id,
        agent_id=autonomy.agent_id,
        autonomy_state_digest=autonomy.digest,
        authority_digest=autonomy.delegation_digest,
        level=autonomy.level,
        paused=paused,
        interrupted=interrupted,
        version=version,
        last_receipt_digest=last_receipt_digest,
    )


def _ref(source: str = "human://operator-1", char: str = "1") -> EvidenceRef:
    return EvidenceRef(
        source=source,
        digest=char * 64,
        category="human_control_authorization",
    )


def _command(
    state: HumanControlState,
    *,
    action: HumanControlAction = HumanControlAction.APPROVE,
    requested_level: AutonomyLevel | None = AutonomyLevel.AUTONOMOUS,
    operation_id: str | None = None,
    execution_id: str | None = None,
    agent_id: str | None = None,
    authority_digest: str | None = None,
    state_digest: str | None = None,
    state_version: int | None = None,
    issuer_id: str = "human:operator-1",
    issued_at: float = NOW - 30.0,
    expires_at: float = NOW + 300.0,
    independent: bool = True,
    evidence_refs: tuple[EvidenceRef, ...] | None = None,
) -> HumanControlCommand:
    if action not in {HumanControlAction.APPROVE, HumanControlAction.OVERRIDE}:
        requested_level = None
    return HumanControlCommand(
        operation_id=operation_id or state.operation_id,
        execution_id=execution_id or state.execution_id,
        agent_id=agent_id or state.agent_id,
        action=action,
        arguments_digest="6" * 64,
        authority_digest=authority_digest or state.authority_digest,
        state_digest=state_digest or state.digest,
        state_version=state.version if state_version is None else state_version,
        issuer_id=issuer_id,
        issuer_digest="f" * 64,
        issued_at=issued_at,
        expires_at=expires_at,
        evidence_refs=evidence_refs or (_ref(),),
        requested_level=requested_level,
        independent=independent,
    )


def _evaluate(
    *,
    level: AutonomyLevel = AutonomyLevel.DELEGATED,
    paused: bool = False,
    interrupted: bool = False,
    action: HumanControlAction = HumanControlAction.APPROVE,
    requested_level: AutonomyLevel | None = AutonomyLevel.AUTONOMOUS,
    observed_at: float = NOW,
    command_overrides: dict | None = None,
):
    delegation = _delegation()
    autonomy = _autonomy(delegation, level=level)
    state = _state(
        autonomy,
        paused=paused,
        interrupted=interrupted,
    )
    command = _command(
        state,
        action=action,
        requested_level=requested_level,
        **(command_overrides or {}),
    )
    decision = evaluate_human_control(
        state=state,
        command=command,
        autonomy_state=autonomy,
        observed_at=observed_at,
    )
    return delegation, autonomy, state, command, decision


def test_exact_approval_materializes_auto03_authorization() -> None:
    delegation, autonomy, _, command, decision = _evaluate()

    assert decision.accepted is True
    assert decision.arguments_digest == command.arguments_digest
    assert decision.action is HumanControlAction.APPROVE
    assert decision.next_level is AutonomyLevel.DELEGATED
    assert decision.next_version == decision.current_version + 1

    authorization = decision.accepted_autonomy_authorization()
    assert authorization.operation_id == autonomy.operation_id
    assert authorization.execution_id == autonomy.execution_id
    assert authorization.agent_id == autonomy.agent_id
    assert authorization.from_level is AutonomyLevel.DELEGATED
    assert authorization.to_level is AutonomyLevel.AUTONOMOUS
    assert authorization.delegation_digest == delegation.decision_digest

    transition = evaluate_autonomy_transition(
        state=autonomy,
        requested_level=AutonomyLevel.AUTONOMOUS,
        signal=AutonomySignal(),
        delegation=delegation,
        observed_at=NOW,
        authorization=authorization,
    )
    assert transition.accepted is True
    assert transition.next_level is AutonomyLevel.AUTONOMOUS


@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        ({"operation_id": "operation-other"}, "command-operation-mismatch"),
        ({"execution_id": "execution-other"}, "command-execution-mismatch"),
        ({"agent_id": "agent-other"}, "command-agent-mismatch"),
        ({"authority_digest": "9" * 64}, "command-authority-mismatch"),
        ({"state_digest": "8" * 64}, "command-state-digest-mismatch"),
        ({"state_version": 8}, "command-state-version-mismatch"),
        ({"issuer_id": "agent-1"}, "issuer-not-independent-of-agent"),
        ({"issued_at": NOW + 1.0}, "command-not-yet-valid"),
        ({"expires_at": NOW}, "command-expired"),
        ({"independent": False}, "approval-not-independent"),
    ),
)
def test_approval_exact_identity_and_freshness_fail_closed(
    overrides: dict,
    reason: str,
) -> None:
    *_, decision = _evaluate(command_overrides=overrides)

    assert decision.accepted is False
    assert reason in decision.reasons
    assert decision.next_version == decision.current_version


def test_approval_is_exactly_one_level_and_cannot_skip() -> None:
    *_, decision = _evaluate(
        level=AutonomyLevel.ASSISTED,
        requested_level=AutonomyLevel.AUTONOMOUS,
    )

    assert decision.accepted is False
    assert decision.reasons == ("approval-not-one-step-escalation",)


def test_pause_forces_observe_and_never_widens_authority() -> None:
    *_, decision = _evaluate(
        action=HumanControlAction.PAUSE,
        requested_level=None,
    )

    assert decision.accepted is True
    assert decision.next_level is AutonomyLevel.OBSERVE
    assert decision.next_paused is True
    assert decision.next_interrupted is False


def test_interrupt_forces_observe_pause_and_interrupt_latch() -> None:
    *_, decision = _evaluate(
        action=HumanControlAction.INTERRUPT,
        requested_level=None,
    )

    assert decision.accepted is True
    assert decision.next_level is AutonomyLevel.OBSERVE
    assert decision.next_paused is True
    assert decision.next_interrupted is True


def test_resume_requires_pause_and_does_not_restore_prior_autonomy() -> None:
    *_, rejected = _evaluate(
        level=AutonomyLevel.OBSERVE,
        action=HumanControlAction.RESUME,
        requested_level=None,
    )
    assert rejected.accepted is False
    assert rejected.reasons == ("state-not-paused",)

    *_, accepted = _evaluate(
        level=AutonomyLevel.OBSERVE,
        paused=True,
        interrupted=True,
        action=HumanControlAction.RESUME,
        requested_level=None,
    )
    assert accepted.accepted is True
    assert accepted.next_level is AutonomyLevel.OBSERVE
    assert accepted.next_paused is False
    assert accepted.next_interrupted is False


def test_override_can_only_hold_or_reduce_level() -> None:
    *_, reduced = _evaluate(
        action=HumanControlAction.OVERRIDE,
        requested_level=AutonomyLevel.ASSISTED,
    )
    assert reduced.accepted is True
    assert reduced.next_level is AutonomyLevel.ASSISTED

    *_, widened = _evaluate(
        level=AutonomyLevel.ASSISTED,
        action=HumanControlAction.OVERRIDE,
        requested_level=AutonomyLevel.DELEGATED,
    )
    assert widened.accepted is False
    assert widened.reasons == ("override-would-escalate",)


def test_paused_or_interrupted_state_cannot_issue_escalation_approval() -> None:
    *_, paused = _evaluate(paused=True)
    assert paused.accepted is False
    assert "state-paused" in paused.reasons

    *_, interrupted = _evaluate(paused=True, interrupted=True)
    assert interrupted.accepted is False
    assert "state-interrupted" in interrupted.reasons


def test_autonomy_snapshot_drift_fails_closed() -> None:
    delegation = _delegation()
    autonomy = _autonomy(delegation)
    state = _state(autonomy)
    command = _command(state)
    drifted = replace(autonomy, version=autonomy.version + 1)

    decision = evaluate_human_control(
        state=state,
        command=command,
        autonomy_state=drifted,
        observed_at=NOW,
    )

    assert decision.accepted is False
    assert "autonomy-state-digest-mismatch" in decision.reasons


def test_stale_command_cannot_replay_after_control_version_advances() -> None:
    delegation = _delegation()
    autonomy = _autonomy(delegation)
    state = _state(autonomy)
    command = _command(state)
    first = evaluate_human_control(
        state=state,
        command=command,
        autonomy_state=autonomy,
        observed_at=NOW,
    )
    assert first.accepted is True

    advanced = replace(
        state,
        version=first.next_version,
        last_receipt_digest=first.receipt_digest,
    )
    replay = evaluate_human_control(
        state=advanced,
        command=command,
        autonomy_state=autonomy,
        observed_at=NOW + 1.0,
    )

    assert replay.accepted is False
    assert "command-state-digest-mismatch" in replay.reasons
    assert "command-state-version-mismatch" in replay.reasons


def test_receipt_chain_and_observation_time_are_explicit() -> None:
    delegation = _delegation()
    autonomy = _autonomy(delegation)
    state = _state(autonomy, last_receipt_digest="9" * 64)
    command = _command(state)

    first = evaluate_human_control(
        state=state,
        command=command,
        autonomy_state=autonomy,
        observed_at=NOW,
    )
    second = evaluate_human_control(
        state=state,
        command=command,
        autonomy_state=autonomy,
        observed_at=NOW + 1.0,
    )

    assert first.accepted is True
    assert first.previous_receipt_digest == "9" * 64
    assert first.decision_digest == second.decision_digest
    assert first.receipt_digest != second.receipt_digest


def test_accepted_receipt_materializes_promotion_evidence() -> None:
    *_, decision = _evaluate()

    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "human_control_qualification"
    assert evidence.digest == decision.receipt_digest


def test_rejected_decision_cannot_materialize_evidence_or_authorization() -> None:
    *_, decision = _evaluate(
        command_overrides={"expires_at": NOW},
    )

    assert decision.accepted is False
    with pytest.raises(HumanControlError, match="cannot become promotion"):
        decision.accepted_evidence_ref()
    with pytest.raises(HumanControlError, match="only an accepted approval"):
        decision.accepted_autonomy_authorization()


def test_command_evidence_is_sorted_deduplicated_and_digest_stable() -> None:
    delegation = _delegation()
    autonomy = _autonomy(delegation)
    state = _state(autonomy)
    first = _ref("human://a", "1")
    second = _ref("human://b", "2")

    left = _command(state, evidence_refs=(second, first, second))
    right = _command(state, evidence_refs=(first, second))

    assert left.evidence_refs == right.evidence_refs
    assert left.digest == right.digest


def test_invalid_command_and_state_shapes_fail_closed() -> None:
    delegation = _delegation()
    autonomy = _autonomy(delegation)
    state = _state(autonomy)

    with pytest.raises(HumanControlError, match="forbids requested_level"):
        HumanControlCommand(
            operation_id=state.operation_id,
            execution_id=state.execution_id,
            agent_id=state.agent_id,
            action=HumanControlAction.PAUSE,
            arguments_digest="1" * 64,
            authority_digest=state.authority_digest,
            state_digest=state.digest,
            state_version=state.version,
            issuer_id="human:operator-1",
            issuer_digest="2" * 64,
            issued_at=NOW - 1.0,
            expires_at=NOW + 1.0,
            evidence_refs=(_ref(),),
            requested_level=AutonomyLevel.OBSERVE,
        )
    with pytest.raises(HumanControlError, match="requires requested_level"):
        _command(
            state,
            action=HumanControlAction.OVERRIDE,
            requested_level=None,
        )
    with pytest.raises(HumanControlError, match="expires_at"):
        _command(state, issued_at=NOW, expires_at=NOW)
    with pytest.raises(HumanControlError, match="last_receipt_digest"):
        _state(autonomy, last_receipt_digest="not-a-digest")
