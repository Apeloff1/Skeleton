"""Cross-plane resilience bindings for the canonical AI-chat runtime.

The chat runtime, model router, attachment plane, and tool-recovery bridge each
own their own authority.  This module does not replace any of them and executes
nothing.  It binds their already-admitted evidence to one immutable turn
identity so retries, failover, attachments, and side-effect recovery cannot
silently regain authority that the turn has already consumed.

The key October-2026 invariant is *remaining-budget routing*: a retry or
failover must be routed against the turn's remaining wall-time, token, call,
and cost authority rather than the original per-turn ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from skeleton.ai.compat.backend_core.model_router import (
    RouteDecision,
    RouteRequest,
)

from .attachments import AttachmentBatchReceipt
from .contracts import digest_json
from .tool_recovery import ToolRecoveryAction, ToolRecoveryDecision
from .turn_runtime import (
    BudgetGovernor,
    ExecutionBudget,
    TurnSnapshot,
    TurnState,
    operation_digest,
)


CROSS_PLANE_RESILIENCE_SCHEMA_VERSION = 1


class ResilienceBindingError(ValueError):
    """Cross-plane evidence cannot be safely bound to the same turn authority."""


def _budget_digest(budget: ExecutionBudget) -> str:
    return digest_json(budget.as_dict())


@dataclass(frozen=True, slots=True)
class TurnAuthorityFingerprint:
    """Immutable identity and ceiling shared by all evidence from one turn."""

    operation_id: str
    request_digest: str
    thread_id: str
    causal_user_message_id: str
    budget_digest: str
    digest: str

    @classmethod
    def from_snapshot(cls, snapshot: TurnSnapshot) -> "TurnAuthorityFingerprint":
        if not isinstance(snapshot, TurnSnapshot):
            raise TypeError("snapshot must be TurnSnapshot")
        payload = {
            "operation_id": snapshot.operation_id,
            "request_digest": snapshot.request_digest,
            "thread_id": snapshot.thread_id,
            "causal_user_message_id": snapshot.causal_user_message_id,
            "budget_digest": _budget_digest(snapshot.budget),
        }
        return cls(**payload, digest=digest_json(payload))

    def as_dict(self) -> dict[str, object]:
        return {
            "operation_id": self.operation_id,
            "request_digest": self.request_digest,
            "thread_id": self.thread_id,
            "causal_user_message_id": self.causal_user_message_id,
            "budget_digest": self.budget_digest,
            "digest": self.digest,
        }


def remaining_execution_budget(snapshot: TurnSnapshot) -> ExecutionBudget:
    """Project the exact unconsumed turn authority into a new hard ceiling."""

    if not isinstance(snapshot, TurnSnapshot):
        raise TypeError("snapshot must be TurnSnapshot")
    decision = BudgetGovernor.assess(snapshot.budget, snapshot.usage)
    if not decision.allowed:
        raise ResilienceBindingError("turn usage already exceeds durable budget")
    remaining = decision.remaining
    return ExecutionBudget(
        max_wall_seconds=float(remaining["wall_seconds"]),
        max_input_tokens=int(remaining["input_tokens"]),
        max_output_tokens=int(remaining["output_tokens"]),
        max_model_calls=int(remaining["model_calls"]),
        max_tool_calls=int(remaining["tool_calls"]),
        max_agent_depth=int(remaining["agent_depth"]),
        max_parallel_workers=int(remaining["parallel_workers"]),
        max_retrieval_queries=int(remaining["retrieval_queries"]),
        max_external_writes=int(remaining["external_writes"]),
        max_cost_usd=float(remaining["cost_usd"]),
    )


def route_request_for_remaining_turn(
    snapshot: TurnSnapshot,
    task_type: str,
    *,
    context_tokens: int = 0,
    expected_output_tokens: int | None = None,
    **kwargs: Any,
) -> RouteRequest:
    """Delegate remaining-authority projection to the canonical model router."""

    if not isinstance(snapshot, TurnSnapshot):
        raise TypeError("snapshot must be TurnSnapshot")
    if snapshot.terminal:
        raise ResilienceBindingError("terminal turn cannot acquire model authority")
    if snapshot.state not in {TurnState.ROUTING, TurnState.MODEL_RUNNING}:
        raise ResilienceBindingError(
            "model routing requires ROUTING or MODEL_RUNNING turn state"
        )
    try:
        return RouteRequest.from_turn_snapshot(
            task_type,
            snapshot,
            context_tokens=context_tokens,
            expected_output_tokens=expected_output_tokens,
            **kwargs,
        )
    except ValueError as exc:
        raise ResilienceBindingError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class TurnRouteBinding:
    authority_digest: str
    stage_snapshot_digest: str
    remaining_budget_digest: str
    route_request_digest: str
    route_decision_digest: str
    selected_endpoint_id: str
    fallback_endpoint_ids: tuple[str, ...]
    provider_receipt_required: bool
    schema_version: int = CROSS_PLANE_RESILIENCE_SCHEMA_VERSION
    authority_scope: str = "routing-evidence-binding-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != CROSS_PLANE_RESILIENCE_SCHEMA_VERSION:
            raise ResilienceBindingError("unsupported route-binding schema")
        if not self.selected_endpoint_id:
            raise ResilienceBindingError("route binding requires selected endpoint")
        if self.selected_endpoint_id in self.fallback_endpoint_ids:
            raise ResilienceBindingError("selected endpoint cannot also be fallback")
        if len(set(self.fallback_endpoint_ids)) != len(self.fallback_endpoint_ids):
            raise ResilienceBindingError("fallback endpoints must be unique")
        if self.authority_scope != "routing-evidence-binding-only":
            raise ResilienceBindingError("route binding authority scope escalated")
        if self.production_authority is not False:
            raise ResilienceBindingError("route binding cannot execute inference")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "authority_digest": self.authority_digest,
            "stage_snapshot_digest": self.stage_snapshot_digest,
            "remaining_budget_digest": self.remaining_budget_digest,
            "route_request_digest": self.route_request_digest,
            "route_decision_digest": self.route_decision_digest,
            "selected_endpoint_id": self.selected_endpoint_id,
            "fallback_endpoint_ids": list(self.fallback_endpoint_ids),
            "provider_receipt_required": self.provider_receipt_required,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


def bind_route_decision(
    snapshot: TurnSnapshot,
    decision: RouteDecision,
) -> TurnRouteBinding:
    """Bind a canonical route decision to the exact remaining turn authority."""

    if not isinstance(snapshot, TurnSnapshot):
        raise TypeError("snapshot must be TurnSnapshot")
    if not isinstance(decision, RouteDecision):
        raise TypeError("decision must be RouteDecision")
    if snapshot.terminal:
        raise ResilienceBindingError("terminal turn cannot bind route evidence")

    remaining = remaining_execution_budget(snapshot)
    request = decision.request
    if remaining.max_model_calls < 1:
        raise ResilienceBindingError("route decision outlived model-call budget")
    if request.context_tokens > remaining.max_input_tokens:
        raise ResilienceBindingError("route context exceeds remaining input budget")
    if request.expected_output_tokens > remaining.max_output_tokens:
        raise ResilienceBindingError("route output exceeds remaining output budget")
    if request.latency_budget_ms is None:
        raise ResilienceBindingError("route decision lacks durable latency budget")
    if request.latency_budget_ms > remaining.max_wall_seconds * 1000.0:
        raise ResilienceBindingError("route latency budget amplifies turn authority")
    if request.cost_budget is None:
        raise ResilienceBindingError("route decision lacks durable cost budget")
    if request.cost_budget > remaining.max_cost_usd:
        raise ResilienceBindingError("route cost budget amplifies turn authority")
    if (
        request.require_provider_receipt
        and not decision.selected.receipt_capable
    ):
        raise ResilienceBindingError(
            "selected endpoint cannot satisfy provider-receipt requirement"
        )
    if decision.selected.endpoint_id in request.excluded_endpoints:
        raise ResilienceBindingError("route selected an explicitly excluded endpoint")

    authority = TurnAuthorityFingerprint.from_snapshot(snapshot)
    return TurnRouteBinding(
        authority_digest=authority.digest,
        stage_snapshot_digest=operation_digest(snapshot),
        remaining_budget_digest=_budget_digest(remaining),
        route_request_digest=request.digest,
        route_decision_digest=decision.digest,
        selected_endpoint_id=decision.selected.endpoint_id,
        fallback_endpoint_ids=decision.fallback_endpoint_ids,
        provider_receipt_required=request.require_provider_receipt,
    )


@dataclass(frozen=True, slots=True)
class TurnToolRecoveryBinding:
    authority_digest: str
    stage_snapshot_digest: str
    action: str
    reason_code: str
    side_effect: str
    next_state: str
    safe_to_execute: bool
    requires_user_approval: bool
    requires_reconciliation: bool
    tool_receipt_ref: str | None
    schema_version: int = CROSS_PLANE_RESILIENCE_SCHEMA_VERSION
    authority_scope: str = "tool-recovery-evidence-binding-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != CROSS_PLANE_RESILIENCE_SCHEMA_VERSION:
            raise ResilienceBindingError("unsupported tool-binding schema")
        if self.authority_scope != "tool-recovery-evidence-binding-only":
            raise ResilienceBindingError("tool binding authority scope escalated")
        if self.production_authority is not False:
            raise ResilienceBindingError("tool binding cannot execute side effects")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "authority_digest": self.authority_digest,
            "stage_snapshot_digest": self.stage_snapshot_digest,
            "action": self.action,
            "reason_code": self.reason_code,
            "side_effect": self.side_effect,
            "next_state": self.next_state,
            "safe_to_execute": self.safe_to_execute,
            "requires_user_approval": self.requires_user_approval,
            "requires_reconciliation": self.requires_reconciliation,
            "tool_receipt_ref": self.tool_receipt_ref,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


_TOOL_NEXT_STATE = {
    ToolRecoveryAction.EXECUTE: TurnState.TOOL_EXECUTING,
    ToolRecoveryAction.WAIT_FOR_APPROVAL: TurnState.AWAITING_USER,
    ToolRecoveryAction.RECONCILE: TurnState.TOOL_EXECUTING,
    ToolRecoveryAction.USE_COMMITTED_RECEIPT: TurnState.MODEL_RUNNING,
}


def bind_tool_recovery_decision(
    snapshot: TurnSnapshot,
    decision: ToolRecoveryDecision,
) -> TurnToolRecoveryBinding:
    """Bind an existing tool-recovery decision without acquiring tool authority."""

    if not isinstance(snapshot, TurnSnapshot):
        raise TypeError("snapshot must be TurnSnapshot")
    if not isinstance(decision, ToolRecoveryDecision):
        raise TypeError("decision must be ToolRecoveryDecision")
    if snapshot.terminal:
        raise ResilienceBindingError("terminal turn cannot bind tool recovery")
    expected = _TOOL_NEXT_STATE[decision.action]
    if decision.next_state is not expected:
        raise ResilienceBindingError("tool recovery next state contradicts action")
    if (
        decision.action is ToolRecoveryAction.RECONCILE
        and not decision.requires_reconciliation
    ):
        raise ResilienceBindingError("reconcile action lost reconciliation requirement")
    if (
        decision.action is ToolRecoveryAction.WAIT_FOR_APPROVAL
        and not decision.requires_user_approval
    ):
        raise ResilienceBindingError("approval wait lost approval requirement")
    if (
        decision.action is ToolRecoveryAction.USE_COMMITTED_RECEIPT
        and decision.tool_receipt_ref is None
    ):
        raise ResilienceBindingError("committed recovery lacks tool receipt")

    authority = TurnAuthorityFingerprint.from_snapshot(snapshot)
    return TurnToolRecoveryBinding(
        authority_digest=authority.digest,
        stage_snapshot_digest=operation_digest(snapshot),
        action=decision.action.value,
        reason_code=decision.reason_code,
        side_effect=decision.side_effect.value,
        next_state=decision.next_state.value,
        safe_to_execute=decision.safe_to_execute,
        requires_user_approval=decision.requires_user_approval,
        requires_reconciliation=decision.requires_reconciliation,
        tool_receipt_ref=decision.tool_receipt_ref,
    )


@dataclass(frozen=True, slots=True)
class TurnAttachmentBinding:
    authority_digest: str
    stage_snapshot_digest: str
    batch_digest: str
    content_refs: tuple[str, ...]
    data_classes: tuple[str, ...]
    total_bytes: int
    schema_version: int = CROSS_PLANE_RESILIENCE_SCHEMA_VERSION
    authority_scope: str = "attachment-evidence-binding-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != CROSS_PLANE_RESILIENCE_SCHEMA_VERSION:
            raise ResilienceBindingError("unsupported attachment-binding schema")
        if len(set(self.content_refs)) != len(self.content_refs):
            raise ResilienceBindingError("attachment content references must be unique")
        if self.authority_scope != "attachment-evidence-binding-only":
            raise ResilienceBindingError("attachment binding authority scope escalated")
        if self.production_authority is not False:
            raise ResilienceBindingError("attachment binding grants no execution authority")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "authority_digest": self.authority_digest,
            "stage_snapshot_digest": self.stage_snapshot_digest,
            "batch_digest": self.batch_digest,
            "content_refs": list(self.content_refs),
            "data_classes": list(self.data_classes),
            "total_bytes": self.total_bytes,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


def bind_attachment_batch(
    snapshot: TurnSnapshot,
    batch: AttachmentBatchReceipt,
) -> TurnAttachmentBinding:
    """Bind only context-eligible, content-addressed attachments to a turn."""

    if not isinstance(snapshot, TurnSnapshot):
        raise TypeError("snapshot must be TurnSnapshot")
    if not isinstance(batch, AttachmentBatchReceipt):
        raise TypeError("batch must be AttachmentBatchReceipt")
    if snapshot.terminal:
        raise ResilienceBindingError("terminal turn cannot acquire attachment evidence")
    blocked = tuple(
        reference.attachment_id
        for reference in batch.references
        if not reference.ready_for_context
    )
    if blocked:
        raise ResilienceBindingError(
            "quarantined attachments cannot be bound to turn context: "
            + ", ".join(blocked)
        )

    authority = TurnAuthorityFingerprint.from_snapshot(snapshot)
    return TurnAttachmentBinding(
        authority_digest=authority.digest,
        stage_snapshot_digest=operation_digest(snapshot),
        batch_digest=batch.digest,
        content_refs=tuple(reference.content_ref for reference in batch.references),
        data_classes=tuple(sorted({reference.data_class for reference in batch.references})),
        total_bytes=batch.total_bytes,
    )


@dataclass(frozen=True, slots=True)
class CrossPlaneResilienceReceipt:
    authority: TurnAuthorityFingerprint
    current_snapshot_digest: str
    route_binding_digest: str | None
    tool_binding_digests: tuple[str, ...]
    attachment_binding_digest: str | None
    provider_receipt_ref: str | None
    state: str
    schema_version: int = CROSS_PLANE_RESILIENCE_SCHEMA_VERSION
    authority_scope: str = "cross-plane-evidence-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if self.schema_version != CROSS_PLANE_RESILIENCE_SCHEMA_VERSION:
            raise ResilienceBindingError("unsupported resilience-receipt schema")
        if len(set(self.tool_binding_digests)) != len(self.tool_binding_digests):
            raise ResilienceBindingError("duplicate tool-binding evidence")
        if self.authority_scope != "cross-plane-evidence-only":
            raise ResilienceBindingError("cross-plane authority scope escalated")
        if self.production_authority is not False:
            raise ResilienceBindingError("resilience receipt cannot execute work")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "authority": self.authority.as_dict(),
            "current_snapshot_digest": self.current_snapshot_digest,
            "route_binding_digest": self.route_binding_digest,
            "tool_binding_digests": list(self.tool_binding_digests),
            "attachment_binding_digest": self.attachment_binding_digest,
            "provider_receipt_ref": self.provider_receipt_ref,
            "state": self.state,
            "authority_scope": self.authority_scope,
            "production_authority": self.production_authority,
        }

    @property
    def digest(self) -> str:
        return digest_json(self.as_dict())


def _require_same_authority(
    expected: TurnAuthorityFingerprint,
    evidence: Iterable[object],
) -> None:
    for item in evidence:
        authority_digest = getattr(item, "authority_digest", None)
        if authority_digest != expected.digest:
            raise ResilienceBindingError("cross-plane evidence belongs to another turn authority")


_PROVIDER_OUTCOME_STATES = {
    TurnState.TOOL_REQUIRED,
    TurnState.AWAITING_USER,
    TurnState.TOOL_EXECUTING,
    TurnState.VERIFYING,
    TurnState.FINALIZING,
    TurnState.ASSISTANT_MESSAGE_COMMITTED,
    TurnState.MEMORY_PROPOSAL,
    TurnState.COMPLETE,
    TurnState.DEGRADED,
}


def build_cross_plane_resilience_receipt(
    snapshot: TurnSnapshot,
    *,
    route: TurnRouteBinding | None = None,
    tools: Iterable[TurnToolRecoveryBinding] = (),
    attachments: TurnAttachmentBinding | None = None,
) -> CrossPlaneResilienceReceipt:
    """Produce a digest-bound conformance receipt for one durable turn state.

    This receipt is evidence only.  It cannot authorize a provider call, tool
    execution, attachment ingest, state transition, or conversation commit.
    """

    if not isinstance(snapshot, TurnSnapshot):
        raise TypeError("snapshot must be TurnSnapshot")
    authority = TurnAuthorityFingerprint.from_snapshot(snapshot)
    tool_bindings = tuple(tools)
    evidence: list[object] = list(tool_bindings)
    if route is not None:
        evidence.append(route)
    if attachments is not None:
        evidence.append(attachments)
    _require_same_authority(authority, evidence)

    if snapshot.has_ambiguous_external_effect:
        raise ResilienceBindingError(
            "cannot qualify turn while consequential tool effect is ambiguous"
        )
    if (
        route is not None
        and route.provider_receipt_required
        and snapshot.state in _PROVIDER_OUTCOME_STATES
        and snapshot.provider_receipt_ref is None
    ):
        raise ResilienceBindingError(
            "provider-receipt-required route has no durable provider receipt"
        )

    return CrossPlaneResilienceReceipt(
        authority=authority,
        current_snapshot_digest=operation_digest(snapshot),
        route_binding_digest=None if route is None else route.digest,
        tool_binding_digests=tuple(item.digest for item in tool_bindings),
        attachment_binding_digest=None if attachments is None else attachments.digest,
        provider_receipt_ref=snapshot.provider_receipt_ref,
        state=snapshot.state.value,
    )


__all__ = [
    "CROSS_PLANE_RESILIENCE_SCHEMA_VERSION",
    "CrossPlaneResilienceReceipt",
    "ResilienceBindingError",
    "TurnAttachmentBinding",
    "TurnAuthorityFingerprint",
    "TurnRouteBinding",
    "TurnToolRecoveryBinding",
    "bind_attachment_batch",
    "bind_route_decision",
    "bind_tool_recovery_decision",
    "build_cross_plane_resilience_receipt",
    "remaining_execution_budget",
    "route_request_for_remaining_turn",
]
