from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
from uuid import uuid4

import pytest

from skeleton.ai.assistant.contracts import SideEffectClass
from skeleton.ai.assistant.tool_recovery import (
    ToolRecoveryAction,
    ToolRecoveryError,
    committed_receipt_event,
    decide_tool_preflight,
    map_tool_side_effect,
    preflight_event,
    reconciliation_event,
)
from skeleton.ai.assistant.turn_runtime import (
    RecoveryAction,
    RecoveryPlanner,
    TurnState,
    make_event,
    start_turn,
)
from skeleton.skills.tool_contract import (
    ToolAuthorityClass,
    ToolEffect,
    ToolExecutionReceipt,
    ToolExecutionRequest,
    ToolExecutionStatus,
    ToolIdempotencyMode,
    ToolManifest,
    ToolRiskClass,
    ToolSideEffectClass,
    approval_ref_for_request,
)
from skeleton.skills.tool_receipt_store import (
    ToolReconciliationOutcome,
    ToolReconciliationReceipt,
    ToolReservation,
)


NOW = datetime(2026, 10, 6, 3, 0, tzinfo=timezone.utc)


def _manifest(
    *,
    effect=ToolEffect.READ_ONLY,
    side_effect_class=ToolSideEffectClass.NONE,
    authority_class=ToolAuthorityClass.READ,
    risk_class=ToolRiskClass.LOW,
    approval_required=False,
):
    return ToolManifest(
        tool_id="repo.action",
        version="1.0.0",
        description="test tool",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
            "additionalProperties": False,
        },
        effect=effect,
        side_effect_class=side_effect_class,
        authority_class=authority_class,
        risk_class=risk_class,
        idempotency_mode=(
            ToolIdempotencyMode.IDEMPOTENCY_KEY
            if authority_class is not ToolAuthorityClass.READ
            else ToolIdempotencyMode.NOT_REQUIRED
        ),
        approval_required=approval_required,
    )


def _request(operation_id, *, approval_ref=None):
    return ToolExecutionRequest(
        request_id=str(uuid4()),
        operation_id=operation_id,
        execution_id="exec-1",
        turn_id="turn-1",
        call_id="call-1",
        tenant_id="tenant-a",
        tool_id="repo.action",
        idempotency_key="tool-key-1",
        arguments={"path": "README.md"},
        requested_at=NOW,
        approval_ref=approval_ref,
    )


def _snapshot():
    operation_id = str(uuid4())
    snapshot = start_turn(
        operation_id=operation_id,
        request_digest="a" * 64,
        thread_id="thread-1",
        causal_user_message_id="user-1",
    )
    for state in (
        TurnState.ADMITTED,
        TurnState.USER_MESSAGE_COMMITTED,
        TurnState.CONTEXT_COMPILING,
        TurnState.ROUTING,
        TurnState.MODEL_RUNNING,
        TurnState.TOOL_REQUIRED,
    ):
        snapshot = snapshot.apply(
            make_event(snapshot, state, observed_at=NOW)
        )
    return snapshot


def _receipt(request, *, status=ToolExecutionStatus.SUCCEEDED):
    return ToolExecutionReceipt(
        receipt_id=str(uuid4()),
        request_id=request.request_id,
        operation_id=request.operation_id,
        execution_id=request.execution_id,
        turn_id=request.turn_id,
        call_id=request.call_id,
        tenant_id=request.tenant_id,
        tool_id=request.tool_id,
        idempotency_key=request.idempotency_key,
        arguments_digest=request.arguments_digest,
        status=status,
        started_at=NOW,
        finished_at=NOW,
        result_ref=(
            "artifact:result"
            if status is ToolExecutionStatus.SUCCEEDED
            else None
        ),
        error_code=(
            None
            if status is ToolExecutionStatus.SUCCEEDED
            else "tool_failed"
        ),
    )


def _reconciliation(request, outcome, *, receipt_id=None):
    return ToolReconciliationReceipt(
        reconciliation_id="b" * 64,
        tenant_id=request.tenant_id,
        operation_id=request.operation_id,
        execution_id=request.execution_id,
        turn_id=request.turn_id,
        call_id=request.call_id,
        idempotency_key=request.idempotency_key,
        request_id=request.request_id,
        tool_id=request.tool_id,
        arguments_digest=request.arguments_digest,
        outcome=outcome,
        evidence_ref="reconcile:evidence-1",
        receipt_id=receipt_id,
        reconciled_at=NOW,
    )


def test_side_effect_mapping_is_conservative():
    assert map_tool_side_effect(_manifest()) is SideEffectClass.READ_ONLY
    assert map_tool_side_effect(
        _manifest(
            effect=ToolEffect.REVERSIBLE,
            authority_class=ToolAuthorityClass.WRITE,
        )
    ) is SideEffectClass.REVERSIBLE_WRITE
    assert map_tool_side_effect(
        _manifest(
            side_effect_class=ToolSideEffectClass.EXTERNAL_REVERSIBLE,
            authority_class=ToolAuthorityClass.EXTERNAL_COMMIT,
        )
    ) is SideEffectClass.EXTERNAL_WRITE
    assert map_tool_side_effect(
        _manifest(
            effect=ToolEffect.IRREVERSIBLE,
            authority_class=ToolAuthorityClass.DESTRUCTIVE,
            approval_required=True,
        )
    ) is SideEffectClass.SECURITY_SENSITIVE


def test_missing_approval_becomes_durable_wait_state():
    snapshot = _snapshot()
    request = _request(snapshot.operation_id)
    manifest = _manifest(
        effect=ToolEffect.IRREVERSIBLE,
        authority_class=ToolAuthorityClass.DESTRUCTIVE,
        approval_required=True,
    )
    decision = decide_tool_preflight(
        snapshot,
        request,
        manifest,
        None,
    )
    assert decision.action is ToolRecoveryAction.WAIT_FOR_APPROVAL
    event = preflight_event(
        snapshot,
        request,
        decision,
        observed_at=NOW,
    )
    waited = snapshot.apply(event)
    assert waited.state is TurnState.AWAITING_USER


def test_approved_consequential_execution_marks_crash_as_ambiguous():
    snapshot = _snapshot()
    bare = _request(snapshot.operation_id)
    manifest = _manifest(
        effect=ToolEffect.IRREVERSIBLE,
        authority_class=ToolAuthorityClass.DESTRUCTIVE,
        approval_required=True,
    )
    request = replace(
        bare,
        approval_ref=approval_ref_for_request(bare),
    )
    decision = decide_tool_preflight(
        snapshot,
        request,
        manifest,
        None,
    )
    assert decision.action is ToolRecoveryAction.EXECUTE
    event = preflight_event(
        snapshot,
        request,
        decision,
        observed_at=NOW,
    )
    executing = snapshot.apply(event)
    assert executing.external_effect_started is True
    assert executing.has_ambiguous_external_effect is True
    recovery = RecoveryPlanner.plan(executing)
    assert recovery.action is RecoveryAction.RECONCILE_TOOL
    assert recovery.safe_to_retry is False


def test_in_doubt_reservation_never_executes_again():
    snapshot = _snapshot()
    request = _request(snapshot.operation_id)
    manifest = _manifest(
        effect=ToolEffect.REVERSIBLE,
        authority_class=ToolAuthorityClass.WRITE,
    )
    decision = decide_tool_preflight(
        snapshot,
        request,
        manifest,
        ToolReservation(status="in_doubt"),
    )
    assert decision.action is ToolRecoveryAction.RECONCILE
    assert decision.safe_to_execute is False
    assert decision.requires_reconciliation is True

    executing = snapshot.apply(
        preflight_event(
            snapshot,
            request,
            decision,
            observed_at=NOW,
        )
    )
    assert RecoveryPlanner.plan(executing).action is RecoveryAction.RECONCILE_TOOL


def test_committed_reservation_bypasses_execution():
    snapshot = _snapshot()
    request = _request(snapshot.operation_id)
    receipt = _receipt(request)
    decision = decide_tool_preflight(
        snapshot,
        request,
        _manifest(),
        ToolReservation(status="committed", receipt=receipt),
    )
    assert decision.action is ToolRecoveryAction.USE_COMMITTED_RECEIPT
    assert decision.safe_to_execute is False
    resumed = snapshot.apply(
        preflight_event(
            snapshot,
            request,
            decision,
            observed_at=NOW,
        )
    )
    assert resumed.state is TurnState.MODEL_RUNNING
    assert resumed.pending_tool_call_id is None


def test_no_effect_reconciliation_is_only_legal_retry_escape():
    snapshot = _snapshot()
    request = _request(snapshot.operation_id)
    manifest = _manifest(
        effect=ToolEffect.REVERSIBLE,
        authority_class=ToolAuthorityClass.WRITE,
    )
    executing = snapshot.apply(
        preflight_event(
            snapshot,
            request,
            decide_tool_preflight(snapshot, request, manifest, None),
            observed_at=NOW,
        )
    )
    assert executing.has_ambiguous_external_effect is True

    unsafe = make_event(
        executing,
        TurnState.TOOL_REQUIRED,
        observed_at=NOW,
        reason_code="retry-without-reconciliation",
    )
    with pytest.raises(Exception, match="must be reconciled"):
        executing.apply(unsafe)

    reconciliation = _reconciliation(
        request,
        ToolReconciliationOutcome.NO_EFFECT,
    )
    retriable = executing.apply(
        reconciliation_event(
            executing,
            request,
            reconciliation,
            observed_at=NOW,
        )
    )
    assert retriable.state is TurnState.TOOL_REQUIRED
    assert retriable.has_ambiguous_external_effect is False


def test_committed_reconciliation_resumes_model_with_both_evidence_refs():
    snapshot = _snapshot()
    request = _request(snapshot.operation_id)
    manifest = _manifest(
        effect=ToolEffect.REVERSIBLE,
        authority_class=ToolAuthorityClass.WRITE,
    )
    executing = snapshot.apply(
        preflight_event(
            snapshot,
            request,
            decide_tool_preflight(snapshot, request, manifest, None),
            observed_at=NOW,
        )
    )
    receipt = _receipt(request)
    reconciliation = _reconciliation(
        request,
        ToolReconciliationOutcome.COMMITTED,
        receipt_id=receipt.receipt_id,
    )
    event = reconciliation_event(
        executing,
        request,
        reconciliation,
        observed_at=NOW,
        committed_receipt=receipt,
    )
    assert event.tool_receipt_ref == "tool-receipt:" + receipt.receipt_id
    assert event.tool_reconciliation_ref == reconciliation.reference
    resumed = executing.apply(event)
    assert resumed.state is TurnState.MODEL_RUNNING
    assert resumed.has_ambiguous_external_effect is False


def test_normal_committed_receipt_resolves_tool_execution():
    snapshot = _snapshot()
    request = _request(snapshot.operation_id)
    executing = snapshot.apply(
        preflight_event(
            snapshot,
            request,
            decide_tool_preflight(
                snapshot,
                request,
                _manifest(
                    effect=ToolEffect.REVERSIBLE,
                    authority_class=ToolAuthorityClass.WRITE,
                ),
                None,
            ),
            observed_at=NOW,
        )
    )
    receipt = _receipt(request)
    resumed = executing.apply(
        committed_receipt_event(
            executing,
            request,
            receipt,
            observed_at=NOW,
        )
    )
    assert resumed.state is TurnState.MODEL_RUNNING
    assert resumed.has_ambiguous_external_effect is False


def test_cross_operation_request_is_rejected():
    snapshot = _snapshot()
    request = _request(str(uuid4()))
    with pytest.raises(ToolRecoveryError, match="different turn operation"):
        decide_tool_preflight(
            snapshot,
            request,
            _manifest(),
            None,
        )
