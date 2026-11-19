from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.ai.assistant.attachments import (
    AttachmentAdmissionPlane,
    AttachmentUpload,
)
from skeleton.ai.assistant.contracts import SideEffectClass
from skeleton.ai.assistant.resilience import (
    ResilienceBindingError,
    TurnAuthorityFingerprint,
    bind_attachment_batch,
    bind_route_decision,
    bind_tool_recovery_decision,
    build_cross_plane_resilience_receipt,
    remaining_execution_budget,
    route_request_for_remaining_turn,
)
from skeleton.ai.assistant.tool_recovery import (
    ToolRecoveryAction,
    ToolRecoveryDecision,
)
from skeleton.ai.assistant.turn_runtime import (
    BudgetUsage,
    ExecutionBudget,
    TurnSnapshot,
    TurnState,
)
from skeleton.ai.compat.backend_core.model_router import (
    ModelEndpoint,
    PrivacyLevel,
    RouteCandidate,
    RouteDecision,
    RouteRequest,
)


REQUEST_DIGEST = "a" * 64


def snapshot(
    *,
    operation_id: str = "turn-1",
    state: TurnState = TurnState.ROUTING,
    usage: BudgetUsage | None = None,
    provider_receipt_ref: str | None = None,
    pending_tool_side_effect: SideEffectClass | None = None,
    external_effect_started: bool = False,
    pending_tool_receipt_ref: str | None = None,
) -> TurnSnapshot:
    return TurnSnapshot(
        operation_id=operation_id,
        request_digest=REQUEST_DIGEST,
        thread_id="thread-1",
        causal_user_message_id="msg-1",
        state=state,
        budget=ExecutionBudget(
            max_wall_seconds=100,
            max_input_tokens=10_000,
            max_output_tokens=4_000,
            max_model_calls=4,
            max_tool_calls=8,
            max_agent_depth=4,
            max_parallel_workers=4,
            max_retrieval_queries=8,
            max_external_writes=2,
            max_cost_usd=5.0,
        ),
        usage=usage or BudgetUsage(),
        provider_receipt_ref=provider_receipt_ref,
        pending_tool_call_id=(
            "call-1" if pending_tool_side_effect is not None else None
        ),
        pending_tool_side_effect=pending_tool_side_effect,
        external_effect_started=external_effect_started,
        pending_tool_receipt_ref=pending_tool_receipt_ref,
    )


def endpoint(
    endpoint_id: str = "ep-a",
    *,
    receipt_capable: bool = True,
) -> ModelEndpoint:
    return ModelEndpoint(
        endpoint_id=endpoint_id,
        provider="provider-a",
        model="model-a",
        capabilities=frozenset({"chat"}),
        modalities=frozenset({"text"}),
        max_context_tokens=100_000,
        input_cost_per_million=1.0,
        output_cost_per_million=2.0,
        nominal_latency_ms=500.0,
        privacy_ceiling=PrivacyLevel.RESTRICTED,
        jurisdiction="no",
        receipt_capable=receipt_capable,
    )


def route_decision(
    snap: TurnSnapshot,
    *,
    require_provider_receipt: bool = False,
    selected: ModelEndpoint | None = None,
    request_override: RouteRequest | None = None,
) -> RouteDecision:
    selected = selected or endpoint()
    request = request_override or route_request_for_remaining_turn(
        snap,
        "chat",
        context_tokens=1_000,
        expected_output_tokens=500,
        required_capabilities=frozenset({"chat"}),
        privacy=PrivacyLevel.INTERNAL,
        allowed_jurisdictions=frozenset({"no"}),
        require_provider_receipt=require_provider_receipt,
    )
    candidate = RouteCandidate(
        endpoint_id=selected.endpoint_id,
        score=0.9,
        reliability=1.0,
        quality=0.9,
        estimated_latency_ms=500.0,
        estimated_cost=0.002,
        provider_preference=0,
    )
    return RouteDecision(
        request=request,
        selected=selected,
        candidates=(candidate,),
        rejected={},
        routed_at=10.0,
    )


def tool_decision(
    *,
    action: ToolRecoveryAction = ToolRecoveryAction.EXECUTE,
    next_state: TurnState = TurnState.TOOL_EXECUTING,
    safe_to_execute: bool = True,
    requires_user_approval: bool = False,
    requires_reconciliation: bool = False,
    tool_receipt_ref: str | None = None,
) -> ToolRecoveryDecision:
    return ToolRecoveryDecision(
        action=action,
        reason_code="test-decision",
        side_effect=SideEffectClass.READ_ONLY,
        next_state=next_state,
        safe_to_execute=safe_to_execute,
        requires_user_approval=requires_user_approval,
        requires_reconciliation=requires_reconciliation,
        tool_receipt_ref=tool_receipt_ref,
    )


def test_remaining_budget_subtracts_durable_usage() -> None:
    snap = snapshot(
        usage=BudgetUsage(
            wall_seconds=25,
            input_tokens=2_000,
            output_tokens=1_000,
            model_calls=1,
            tool_calls=2,
            agent_depth=1,
            parallel_workers=1,
            retrieval_queries=3,
            external_writes=1,
            cost_usd=1.25,
        )
    )
    remaining = remaining_execution_budget(snap)
    assert remaining.max_wall_seconds == 75
    assert remaining.max_input_tokens == 8_000
    assert remaining.max_output_tokens == 3_000
    assert remaining.max_model_calls == 3
    assert remaining.max_tool_calls == 6
    assert remaining.max_external_writes == 1
    assert remaining.max_cost_usd == 3.75


def test_route_request_uses_remaining_not_original_turn_budget() -> None:
    snap = snapshot(
        usage=BudgetUsage(
            wall_seconds=40,
            output_tokens=1_500,
            model_calls=2,
            cost_usd=2.0,
        )
    )
    request = route_request_for_remaining_turn(
        snap,
        "chat",
        context_tokens=100,
        expected_output_tokens=2_000,
    )
    assert request.latency_budget_ms == 60_000
    assert request.cost_budget == 3.0
    assert request.expected_output_tokens == 2_000


def test_route_request_rejects_exhausted_model_call_budget() -> None:
    snap = snapshot(usage=BudgetUsage(model_calls=4))
    with pytest.raises(ResilienceBindingError, match="model-call budget exhausted"):
        route_request_for_remaining_turn(snap, "chat")


def test_route_request_rejects_context_over_remaining_input() -> None:
    snap = snapshot(usage=BudgetUsage(input_tokens=9_500))
    with pytest.raises(ResilienceBindingError, match="remaining input-token"):
        route_request_for_remaining_turn(snap, "chat", context_tokens=501)


def test_route_request_rejects_output_over_remaining_output() -> None:
    snap = snapshot(usage=BudgetUsage(output_tokens=3_500))
    with pytest.raises(ResilienceBindingError, match="remaining output-token"):
        route_request_for_remaining_turn(
            snap,
            "chat",
            expected_output_tokens=501,
        )


def test_route_binding_records_exact_remaining_authority() -> None:
    snap = snapshot(usage=BudgetUsage(model_calls=1, cost_usd=0.5))
    decision = route_decision(snap)
    binding = bind_route_decision(snap, decision)
    assert binding.selected_endpoint_id == "ep-a"
    assert binding.route_request_digest == decision.request.digest
    assert binding.route_decision_digest == decision.digest
    assert binding.production_authority is False


def test_route_binding_rejects_cost_authority_amplification() -> None:
    snap = snapshot(usage=BudgetUsage(cost_usd=4.0))
    request = RouteRequest(
        task_type="chat",
        context_tokens=100,
        expected_output_tokens=100,
        latency_budget_ms=1_000,
        cost_budget=2.0,
    )
    decision = route_decision(snap, request_override=request)
    with pytest.raises(ResilienceBindingError, match="cost budget amplifies"):
        bind_route_decision(snap, decision)


def test_route_binding_rejects_latency_authority_amplification() -> None:
    snap = snapshot(usage=BudgetUsage(wall_seconds=99))
    request = RouteRequest(
        task_type="chat",
        context_tokens=100,
        expected_output_tokens=100,
        latency_budget_ms=1_001,
        cost_budget=0.1,
    )
    decision = route_decision(snap, request_override=request)
    with pytest.raises(ResilienceBindingError, match="latency budget amplifies"):
        bind_route_decision(snap, decision)


@pytest.mark.parametrize(
    ("latency", "cost", "message"),
    (
        (None, 0.1, "lacks durable latency budget"),
        (1_000.0, None, "lacks durable cost budget"),
    ),
)
def test_route_binding_requires_explicit_budget_evidence(
    latency: float | None,
    cost: float | None,
    message: str,
) -> None:
    snap = snapshot()
    request = RouteRequest(
        task_type="chat",
        context_tokens=100,
        expected_output_tokens=100,
        latency_budget_ms=latency,
        cost_budget=cost,
    )
    decision = route_decision(snap, request_override=request)
    with pytest.raises(ResilienceBindingError, match=message):
        bind_route_decision(snap, decision)


def test_route_binding_rechecks_provider_receipt_capability() -> None:
    snap = snapshot()
    decision = route_decision(
        snap,
        require_provider_receipt=True,
        selected=endpoint(receipt_capable=False),
    )
    with pytest.raises(ResilienceBindingError, match="provider-receipt requirement"):
        bind_route_decision(snap, decision)


def test_turn_authority_fingerprint_is_stable_across_progress() -> None:
    first = snapshot(state=TurnState.ROUTING)
    later = snapshot(
        state=TurnState.MODEL_RUNNING,
        usage=BudgetUsage(model_calls=1, cost_usd=0.25),
    )
    assert TurnAuthorityFingerprint.from_snapshot(first).digest == (
        TurnAuthorityFingerprint.from_snapshot(later).digest
    )


def test_tool_recovery_binding_preserves_non_execution_boundary() -> None:
    snap = snapshot(state=TurnState.TOOL_REQUIRED)
    binding = bind_tool_recovery_decision(snap, tool_decision())
    assert binding.action == "execute"
    assert binding.next_state == TurnState.TOOL_EXECUTING.value
    assert binding.production_authority is False


def test_tool_recovery_binding_rejects_action_state_contradiction() -> None:
    snap = snapshot(state=TurnState.TOOL_REQUIRED)
    decision = tool_decision(
        action=ToolRecoveryAction.WAIT_FOR_APPROVAL,
        next_state=TurnState.TOOL_EXECUTING,
        safe_to_execute=False,
        requires_user_approval=True,
    )
    with pytest.raises(ResilienceBindingError, match="contradicts action"):
        bind_tool_recovery_decision(snap, decision)


def test_tool_recovery_binding_rechecks_reconciliation_requirement() -> None:
    snap = snapshot(state=TurnState.TOOL_REQUIRED)
    decision = tool_decision(
        action=ToolRecoveryAction.RECONCILE,
        next_state=TurnState.TOOL_EXECUTING,
        safe_to_execute=False,
        requires_reconciliation=False,
    )
    with pytest.raises(ResilienceBindingError, match="lost reconciliation"):
        bind_tool_recovery_decision(snap, decision)


def test_attachment_binding_accepts_only_context_ready_references() -> None:
    snap = snapshot()
    plane = AttachmentAdmissionPlane()
    batch = plane.admit_batch(
        (
            AttachmentUpload(
                payload=b"hello",
                declared_size=5,
                claimed_mime="text/plain",
                filename="hello.txt",
            ),
        )
    )
    binding = bind_attachment_batch(snap, batch)
    assert binding.content_refs == (batch.references[0].content_ref,)
    assert binding.total_bytes == 5
    assert binding.production_authority is False


def test_attachment_binding_rejects_quarantined_reference() -> None:
    snap = snapshot()
    payload = b"%PDF-1.7\n/OpenAction\n%%EOF"
    batch = AttachmentAdmissionPlane().admit_batch(
        (
            AttachmentUpload(
                payload=payload,
                declared_size=len(payload),
                claimed_mime="application/pdf",
                filename="unsafe.pdf",
            ),
        )
    )
    assert batch.references[0].quarantined
    with pytest.raises(ResilienceBindingError, match="quarantined attachments"):
        bind_attachment_batch(snap, batch)


def test_cross_plane_receipt_rejects_other_turn_authority() -> None:
    first = snapshot(operation_id="turn-1")
    other = snapshot(operation_id="turn-2")
    route = bind_route_decision(first, route_decision(first))
    with pytest.raises(ResilienceBindingError, match="another turn authority"):
        build_cross_plane_resilience_receipt(other, route=route)


def test_cross_plane_receipt_blocks_ambiguous_consequential_effect() -> None:
    snap = snapshot(
        state=TurnState.TOOL_EXECUTING,
        pending_tool_side_effect=SideEffectClass.EXTERNAL_WRITE,
        external_effect_started=True,
    )
    with pytest.raises(ResilienceBindingError, match="effect is ambiguous"):
        build_cross_plane_resilience_receipt(snap)


def test_provider_receipt_requirement_blocks_post_model_qualification() -> None:
    routing = snapshot(state=TurnState.ROUTING)
    route = bind_route_decision(
        routing,
        route_decision(routing, require_provider_receipt=True),
    )
    verifying = snapshot(state=TurnState.VERIFYING)
    with pytest.raises(ResilienceBindingError, match="no durable provider receipt"):
        build_cross_plane_resilience_receipt(verifying, route=route)


def test_provider_receipt_requirement_accepts_durable_receipt() -> None:
    routing = snapshot(state=TurnState.ROUTING)
    route = bind_route_decision(
        routing,
        route_decision(routing, require_provider_receipt=True),
    )
    verifying = snapshot(
        state=TurnState.VERIFYING,
        provider_receipt_ref="provider-receipt:abc",
    )
    receipt = build_cross_plane_resilience_receipt(verifying, route=route)
    assert receipt.provider_receipt_ref == "provider-receipt:abc"
    assert receipt.route_binding_digest == route.digest
    assert receipt.production_authority is False


def test_cross_plane_receipt_is_deterministic_for_same_evidence() -> None:
    snap = snapshot()
    route = bind_route_decision(snap, route_decision(snap))
    first = build_cross_plane_resilience_receipt(snap, route=route)
    second = build_cross_plane_resilience_receipt(snap, route=route)
    assert first.digest == second.digest


def test_terminal_turn_cannot_acquire_new_route_authority() -> None:
    snap = snapshot(state=TurnState.COMPLETE)
    with pytest.raises(ResilienceBindingError, match="terminal turn"):
        route_request_for_remaining_turn(snap, "chat")
