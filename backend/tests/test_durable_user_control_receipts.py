from __future__ import annotations

from dataclasses import replace

import pytest

from core.operator_control_projection import (
    build_operator_control_projection_from_store,
    verify_operator_control_projection_from_store,
)
from core.user_control_receipts import (
    HumanControlReceiptConflict,
    SQLiteHumanControlReceiptStore,
)
from core.workspace_projection import (
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


NOW = 1_800_000_000.0


def _decision(
    *,
    action: HumanControlAction = HumanControlAction.PAUSE,
    current_version: int = 1,
    previous_receipt_digest: str | None = None,
    operation_id: str = "operation-1",
    execution_id: str = "execution-1",
    agent_id: str = "agent-1",
    authority_digest: str = "a" * 64,
    next_paused: bool = True,
    next_interrupted: bool = False,
    from_level: AutonomyLevel = AutonomyLevel.DELEGATED,
    next_level: AutonomyLevel = AutonomyLevel.OBSERVE,
    requested_level: AutonomyLevel | None = None,
    accepted: bool = True,
    reasons: tuple[str, ...] = (),
) -> HumanControlDecision:
    return HumanControlDecision(
        accepted=accepted,
        action=action,
        reasons=reasons,
        operation_id=operation_id,
        execution_id=execution_id,
        agent_id=agent_id,
        arguments_digest="b" * 64,
        state_digest=f"{current_version:x}".rjust(64, "0"),
        command_digest=f"{current_version + 20:x}".rjust(64, "0"),
        autonomy_state_digest="c" * 64,
        authority_digest=authority_digest,
        from_level=from_level,
        requested_level=requested_level,
        next_level=next_level,
        next_paused=next_paused,
        next_interrupted=next_interrupted,
        current_version=current_version,
        next_version=current_version + 1 if accepted else current_version,
        issuer_id="human:operator",
        issuer_digest="d" * 64,
        expires_at=NOW + 300.0,
        evidence_refs=(
            EvidenceRef(
                source=f"control://receipt/{current_version}",
                digest="e" * 64,
                category="human_control_authorization",
            ),
        ),
        independent=True,
        observed_at=NOW + current_version,
        previous_receipt_digest=previous_receipt_digest,
    )


def _workspace(
    *,
    tenant_id: str = "tenant-a",
) -> tuple[WorkspaceProjection, WorkspaceProjectionDecision]:
    workspace = WorkspaceProjection(
        operation_id="operation-1",
        tenant_id=tenant_id,
        trace_id="trace-1",
        canonical_state=OperationState.RUNNING,
        operation_version=5,
        cursor_sequence=5,
        terminal=False,
        operation_projection_digest="1" * 64,
        projection_authority_digest="2" * 64,
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


def test_receipt_chain_survives_restart(tmp_path) -> None:
    path = tmp_path / "human-control.sqlite"
    first = _decision()

    store = SQLiteHumanControlReceiptStore(path)
    assert store.append(tenant_id="tenant-a", decision=first) == first
    store.close()

    reopened = SQLiteHumanControlReceiptStore(path)
    loaded = reopened.chain(
        tenant_id="tenant-a",
        operation_id=first.operation_id,
        execution_id=first.execution_id,
    )
    assert loaded == (first,)

    second = _decision(
        action=HumanControlAction.RESUME,
        current_version=2,
        previous_receipt_digest=first.receipt_digest,
        next_paused=False,
        from_level=AutonomyLevel.OBSERVE,
        next_level=AutonomyLevel.OBSERVE,
    )
    reopened.append(tenant_id="tenant-a", decision=second)
    reopened.close()

    final = SQLiteHumanControlReceiptStore(path)
    assert final.chain(
        tenant_id="tenant-a",
        operation_id=first.operation_id,
        execution_id=first.execution_id,
    ) == (first, second)
    final.close()


def test_exact_duplicate_append_is_idempotent(tmp_path) -> None:
    store = SQLiteHumanControlReceiptStore(
        tmp_path / "human-control.sqlite"
    )
    decision = _decision()
    first = store.append(tenant_id="tenant-a", decision=decision)
    second = store.append(tenant_id="tenant-a", decision=decision)
    assert first == second
    assert store.chain(
        tenant_id="tenant-a",
        operation_id=decision.operation_id,
        execution_id=decision.execution_id,
    ) == (decision,)
    store.close()


def test_tenant_identity_isolation_is_enforced(tmp_path) -> None:
    store = SQLiteHumanControlReceiptStore(
        tmp_path / "human-control.sqlite"
    )
    decision = _decision()
    store.append(tenant_id="tenant-a", decision=decision)

    assert store.chain(
        tenant_id="tenant-b",
        operation_id=decision.operation_id,
        execution_id=decision.execution_id,
    ) == ()
    store.close()


def test_rejected_receipt_cannot_persist(tmp_path) -> None:
    store = SQLiteHumanControlReceiptStore(
        tmp_path / "human-control.sqlite"
    )
    rejected = _decision(
        accepted=False,
        reasons=("forced-rejection",),
    )
    with pytest.raises(
        HumanControlReceiptConflict,
        match="rejected",
    ):
        store.append(tenant_id="tenant-a", decision=rejected)
    store.close()


def test_first_receipt_must_begin_at_version_one(tmp_path) -> None:
    store = SQLiteHumanControlReceiptStore(
        tmp_path / "human-control.sqlite"
    )
    with pytest.raises(
        HumanControlReceiptConflict,
        match="version 1",
    ):
        store.append(
            tenant_id="tenant-a",
            decision=_decision(current_version=2),
        )
    store.close()


def test_predecessor_and_version_tamper_fail_closed(tmp_path) -> None:
    store = SQLiteHumanControlReceiptStore(
        tmp_path / "human-control.sqlite"
    )
    first = _decision()
    store.append(tenant_id="tenant-a", decision=first)

    bad_predecessor = _decision(
        action=HumanControlAction.RESUME,
        current_version=2,
        previous_receipt_digest="0" * 64,
        next_paused=False,
        from_level=AutonomyLevel.OBSERVE,
        next_level=AutonomyLevel.OBSERVE,
    )
    with pytest.raises(
        HumanControlReceiptConflict,
        match="predecessor",
    ):
        store.append(
            tenant_id="tenant-a",
            decision=bad_predecessor,
        )

    skipped = _decision(
        action=HumanControlAction.RESUME,
        current_version=3,
        previous_receipt_digest=first.receipt_digest,
        next_paused=False,
        from_level=AutonomyLevel.OBSERVE,
        next_level=AutonomyLevel.OBSERVE,
    )
    with pytest.raises(
        HumanControlReceiptConflict,
        match="not contiguous",
    ):
        store.append(tenant_id="tenant-a", decision=skipped)
    store.close()


def test_agent_or_authority_change_inside_chain_is_rejected(
    tmp_path,
) -> None:
    store = SQLiteHumanControlReceiptStore(
        tmp_path / "human-control.sqlite"
    )
    first = _decision()
    store.append(tenant_id="tenant-a", decision=first)

    second = _decision(
        action=HumanControlAction.RESUME,
        current_version=2,
        previous_receipt_digest=first.receipt_digest,
        next_paused=False,
        from_level=AutonomyLevel.OBSERVE,
        next_level=AutonomyLevel.OBSERVE,
    )
    with pytest.raises(
        HumanControlReceiptConflict,
        match="agent identity",
    ):
        store.append(
            tenant_id="tenant-a",
            decision=replace(second, agent_id="agent-other"),
        )
    with pytest.raises(
        HumanControlReceiptConflict,
        match="authority digest",
    ):
        store.append(
            tenant_id="tenant-a",
            decision=replace(
                second,
                authority_digest="f" * 64,
            ),
        )
    store.close()


def test_workspace_projection_rebuilds_from_durable_latest_receipt(
    tmp_path,
) -> None:
    workspace, workspace_decision = _workspace()
    pause = _decision(
        next_paused=True,
        next_level=AutonomyLevel.OBSERVE,
    )
    path = tmp_path / "human-control.sqlite"

    store = SQLiteHumanControlReceiptStore(path)
    store.append(tenant_id=workspace.tenant_id, decision=pause)
    store.close()

    reopened = SQLiteHumanControlReceiptStore(path)
    projection = build_operator_control_projection_from_store(
        store=reopened,
        tenant_id=workspace.tenant_id,
        execution_id=pause.execution_id,
        workspace=workspace,
        workspace_decision=workspace_decision,
    )
    verified = verify_operator_control_projection_from_store(
        projection,
        store=reopened,
        tenant_id=workspace.tenant_id,
        execution_id=pause.execution_id,
        workspace=workspace,
        workspace_decision=workspace_decision,
    )

    assert projection.control_known is True
    assert projection.last_action is HumanControlAction.PAUSE
    assert projection.human_control_receipt_digest == pause.receipt_digest
    assert projection.available_actions == ("cancel", "resume")
    assert verified.accepted is True
    reopened.close()


def test_wrong_tenant_cannot_recover_control_state(tmp_path) -> None:
    workspace, workspace_decision = _workspace()
    pause = _decision()
    store = SQLiteHumanControlReceiptStore(
        tmp_path / "human-control.sqlite"
    )
    store.append(tenant_id="tenant-a", decision=pause)

    projection = build_operator_control_projection_from_store(
        store=store,
        tenant_id="tenant-b",
        execution_id=pause.execution_id,
        workspace=workspace,
        workspace_decision=workspace_decision,
    )

    assert projection.control_known is False
    assert projection.available_actions == ("cancel",)
    store.close()
