from __future__ import annotations

from dataclasses import replace

import pytest

from core.operator_control_projection import (
    OperatorControlProjectionError,
    build_operator_control_projection,
    verify_operator_control_projection,
)
from core.workspace_projection import (
    TerminalResultProjection,
    WorkspaceProjection,
    WorkspaceProjectionDecision,
)
from skeleton.agents.autonomy_control import AutonomyLevel
from skeleton.agents.human_control import (
    HumanControlAction,
    HumanControlDecision,
)
from skeleton.contracts.canonical import EvidenceRef
from skeleton.contracts.operation import OperationState


def _terminal_result() -> TerminalResultProjection:
    return TerminalResultProjection(
        summary="Canonical operation is terminal.",
        result=EvidenceRef(
            source="ci://prod-04/terminal",
            digest="a" * 64,
            category="operation_result",
        ),
    )


def _workspace(
    *,
    state: OperationState = OperationState.RUNNING,
    tenant_id: str = "tenant-a",
) -> tuple[WorkspaceProjection, WorkspaceProjectionDecision]:
    terminal = state in {
        OperationState.COMPLETED,
        OperationState.FAILED,
        OperationState.CANCELLED,
    }
    workspace = WorkspaceProjection(
        operation_id="operation-1",
        tenant_id=tenant_id,
        trace_id="trace-1",
        canonical_state=state,
        operation_version=5,
        cursor_sequence=5,
        terminal=terminal,
        operation_projection_digest="1" * 64,
        projection_authority_digest="2" * 64,
        terminal_result=_terminal_result() if terminal else None,
    )
    decision = WorkspaceProjectionDecision(
        accepted=True,
        reasons=(),
        workspace_projection_digest=workspace.projection_digest,
        operation_projection_digest="1" * 64,
        projection_authority_digest="2" * 64,
        operation_id=workspace.operation_id,
        tenant_id=workspace.tenant_id,
        operation_version=workspace.operation_version,
        cursor_sequence=workspace.cursor_sequence,
    )
    return workspace, decision


def _human(
    action: HumanControlAction,
    *,
    accepted: bool = True,
    next_paused: bool = False,
    next_interrupted: bool = False,
    next_level: AutonomyLevel = AutonomyLevel.DELEGATED,
    requested_level: AutonomyLevel | None = None,
    previous_receipt_digest: str | None = None,
) -> HumanControlDecision:
    current_version = 7
    return HumanControlDecision(
        accepted=accepted,
        action=action,
        reasons=() if accepted else ("forced-rejection",),
        operation_id="operation-1",
        execution_id="execution-1",
        agent_id="agent-1",
        arguments_digest="3" * 64,
        state_digest="4" * 64,
        command_digest="5" * 64,
        autonomy_state_digest="6" * 64,
        authority_digest="7" * 64,
        from_level=AutonomyLevel.DELEGATED,
        requested_level=requested_level,
        next_level=next_level,
        next_paused=next_paused,
        next_interrupted=next_interrupted,
        current_version=current_version,
        next_version=current_version + 1 if accepted else current_version,
        issuer_id="human:operator-1",
        issuer_digest="8" * 64,
        expires_at=1_800_000_300.0,
        evidence_refs=(
            EvidenceRef(
                source="ci://prod-04/control",
                digest="9" * 64,
                category="human_control_authorization",
            ),
        ),
        independent=True,
        observed_at=1_800_000_000.0,
        previous_receipt_digest=previous_receipt_digest,
    )


def test_unknown_human_control_state_exposes_only_canonical_cancel() -> None:
    workspace, decision = _workspace()

    projection = build_operator_control_projection(
        workspace=workspace,
        workspace_decision=decision,
    )
    verified = verify_operator_control_projection(
        projection,
        workspace,
        decision,
    )

    assert projection.control_known is False
    assert projection.available_actions == ("cancel",)
    assert projection.cancelled is False
    assert verified.accepted is True


@pytest.mark.parametrize(
    ("receipt", "actions"),
    (
        (
            _human(
                HumanControlAction.PAUSE,
                next_paused=True,
                next_level=AutonomyLevel.OBSERVE,
            ),
            ("cancel", "resume"),
        ),
        (
            _human(
                HumanControlAction.INTERRUPT,
                next_paused=True,
                next_interrupted=True,
                next_level=AutonomyLevel.OBSERVE,
            ),
            ("cancel", "resume"),
        ),
        (
            _human(
                HumanControlAction.RESUME,
                next_paused=False,
                next_interrupted=False,
            ),
            ("cancel", "interrupt", "override", "pause"),
        ),
        (
            _human(
                HumanControlAction.OVERRIDE,
                next_level=AutonomyLevel.OBSERVE,
                requested_level=AutonomyLevel.OBSERVE,
            ),
            ("cancel", "interrupt", "override", "pause"),
        ),
    ),
)
def test_accepted_auto04_receipt_drives_projected_controls(
    receipt: HumanControlDecision,
    actions: tuple[str, ...],
) -> None:
    workspace, decision = _workspace()

    projection = build_operator_control_projection(
        workspace=workspace,
        workspace_decision=decision,
        human_control=receipt,
    )
    verified = verify_operator_control_projection(
        projection,
        workspace,
        decision,
        receipt,
    )

    assert projection.control_known is True
    assert projection.human_control_receipt_digest == receipt.receipt_digest
    assert projection.control_version == receipt.next_version
    assert projection.available_actions == actions
    assert verified.accepted is True
    evidence = verified.accepted_evidence_ref()
    assert evidence.category == "operator_control_projection"
    assert evidence.digest == verified.decision_digest


def test_cancelled_state_derives_only_from_canonical_operation_truth() -> None:
    workspace, decision = _workspace(state=OperationState.CANCELLED)
    stale_pause = _human(
        HumanControlAction.PAUSE,
        next_paused=True,
        next_level=AutonomyLevel.OBSERVE,
    )

    projection = build_operator_control_projection(
        workspace=workspace,
        workspace_decision=decision,
        human_control=stale_pause,
    )
    verified = verify_operator_control_projection(
        projection,
        workspace,
        decision,
        stale_pause,
    )

    assert projection.cancelled is True
    assert projection.terminal is True
    assert projection.available_actions == ()
    assert verified.accepted is True


@pytest.mark.parametrize(
    "state",
    (
        OperationState.COMPLETED,
        OperationState.FAILED,
        OperationState.CANCELLED,
    ),
)
def test_terminal_finality_exposes_no_live_controls(
    state: OperationState,
) -> None:
    workspace, decision = _workspace(state=state)
    resume = _human(HumanControlAction.RESUME)

    projection = build_operator_control_projection(
        workspace=workspace,
        workspace_decision=decision,
        human_control=resume,
    )

    assert projection.terminal is True
    assert projection.available_actions == ()


def test_rejected_human_control_receipt_cannot_drive_product_state() -> None:
    workspace, decision = _workspace()
    rejected = _human(
        HumanControlAction.PAUSE,
        accepted=False,
        next_paused=True,
        next_level=AutonomyLevel.OBSERVE,
    )

    with pytest.raises(
        OperatorControlProjectionError,
        match="receipt must be accepted",
    ):
        build_operator_control_projection(
            workspace=workspace,
            workspace_decision=decision,
            human_control=rejected,
        )


def test_approval_receipt_is_not_operator_control_projection() -> None:
    workspace, decision = _workspace()
    approval = _human(
        HumanControlAction.APPROVE,
        requested_level=AutonomyLevel.AUTONOMOUS,
    )

    with pytest.raises(
        OperatorControlProjectionError,
        match="not projectable",
    ):
        build_operator_control_projection(
            workspace=workspace,
            workspace_decision=decision,
            human_control=approval,
        )


def test_receipt_substitution_is_detected() -> None:
    workspace, decision = _workspace()
    pause = _human(
        HumanControlAction.PAUSE,
        next_paused=True,
        next_level=AutonomyLevel.OBSERVE,
    )
    projection = build_operator_control_projection(
        workspace=workspace,
        workspace_decision=decision,
        human_control=pause,
    )
    forged = replace(
        projection,
        human_control_receipt_digest="0" * 64,
    )

    verified = verify_operator_control_projection(
        forged,
        workspace,
        decision,
        pause,
    )

    assert verified.accepted is False
    assert "human-control-receipt-digest-mismatch" in verified.reasons


def test_control_version_and_state_drift_are_detected() -> None:
    workspace, decision = _workspace()
    interrupt = _human(
        HumanControlAction.INTERRUPT,
        next_paused=True,
        next_interrupted=True,
        next_level=AutonomyLevel.OBSERVE,
    )
    projection = build_operator_control_projection(
        workspace=workspace,
        workspace_decision=decision,
        human_control=interrupt,
    )
    forged = replace(
        projection,
        control_version=projection.control_version + 1,
        paused=False,
        interrupted=False,
        available_actions=("cancel", "interrupt", "override", "pause"),
    )

    verified = verify_operator_control_projection(
        forged,
        workspace,
        decision,
        interrupt,
    )

    assert verified.accepted is False
    assert "control-version-mismatch" in verified.reasons
    assert "paused-state-mismatch" in verified.reasons
    assert "interrupted-state-mismatch" in verified.reasons


def test_workspace_tenant_and_digest_drift_are_detected() -> None:
    workspace, decision = _workspace()
    projection = build_operator_control_projection(
        workspace=workspace,
        workspace_decision=decision,
    )
    forged = replace(
        projection,
        tenant_id="tenant-b",
        workspace_projection_digest="0" * 64,
    )

    verified = verify_operator_control_projection(
        forged,
        workspace,
        decision,
    )

    assert verified.accepted is False
    assert "tenant-id-mismatch" in verified.reasons
    assert "workspace-projection-digest-mismatch" in verified.reasons


def test_reconnect_rebuild_is_deterministic_from_same_authorities() -> None:
    workspace, decision = _workspace()
    pause = _human(
        HumanControlAction.PAUSE,
        next_paused=True,
        next_level=AutonomyLevel.OBSERVE,
        previous_receipt_digest="a" * 64,
    )

    first = build_operator_control_projection(
        workspace=workspace,
        workspace_decision=decision,
        human_control=pause,
    )
    second = build_operator_control_projection(
        workspace=workspace,
        workspace_decision=decision,
        human_control=pause,
    )

    assert first == second
    assert first.projection_digest == second.projection_digest
    assert first.previous_control_receipt_digest == "a" * 64


def test_stale_workspace_decision_cannot_build_operator_projection() -> None:
    workspace, decision = _workspace()
    stale = replace(
        decision,
        workspace_projection_digest="0" * 64,
    )

    with pytest.raises(
        OperatorControlProjectionError,
        match="workspace decision digest mismatch",
    ):
        build_operator_control_projection(
            workspace=workspace,
            workspace_decision=stale,
        )


def test_rejected_projection_cannot_materialize_evidence() -> None:
    workspace, decision = _workspace()
    projection = build_operator_control_projection(
        workspace=workspace,
        workspace_decision=decision,
    )
    forged = replace(projection, tenant_id="tenant-b")
    verified = verify_operator_control_projection(
        forged,
        workspace,
        decision,
    )

    assert verified.accepted is False
    with pytest.raises(
        OperatorControlProjectionError,
        match="cannot become evidence",
    ):
        verified.accepted_evidence_ref()
