"""Fail-closed bridge between canonical tool receipts and AI-chat turns.

This module does not execute tools. It converts canonical tool authority,
reservation, approval, receipt, and reconciliation facts into durable chat-turn
transitions.

Consequential tool execution is marked potentially effectful when the turn
enters TOOL_EXECUTING. That is intentionally conservative: if the process dies
after the durable reservation but before a receipt is committed, recovery
requires reconciliation rather than blind replay.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .contracts import SideEffectClass
from .turn_runtime import (
    RecoveryAction,
    RecoveryPlanner,
    TurnEvent,
    TurnRuntimeError,
    TurnSnapshot,
    TurnState,
    make_event,
)
from skeleton.skills.tool_contract import (
    ToolApprovalPolicy,
    ToolAuthorityClass,
    ToolEffect,
    ToolExecutionReceipt,
    ToolExecutionRequest,
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


class ToolRecoveryError(ValueError):
    """Tool recovery facts cannot be safely bound to the turn."""


class ToolRecoveryAction(str, Enum):
    EXECUTE = "execute"
    WAIT_FOR_APPROVAL = "wait_for_approval"
    RECONCILE = "reconcile"
    USE_COMMITTED_RECEIPT = "use_committed_receipt"


@dataclass(frozen=True, slots=True)
class ToolRecoveryDecision:
    action: ToolRecoveryAction
    reason_code: str
    side_effect: SideEffectClass
    next_state: TurnState
    safe_to_execute: bool
    requires_user_approval: bool = False
    requires_reconciliation: bool = False
    tool_receipt_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, ToolRecoveryAction):
            object.__setattr__(
                self,
                "action",
                ToolRecoveryAction(str(self.action)),
            )
        if not isinstance(self.side_effect, SideEffectClass):
            object.__setattr__(
                self,
                "side_effect",
                SideEffectClass(str(self.side_effect)),
            )
        if not isinstance(self.next_state, TurnState):
            object.__setattr__(
                self,
                "next_state",
                TurnState(str(self.next_state)),
            )
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ToolRecoveryError("reason_code must be non-empty text")
        object.__setattr__(self, "reason_code", self.reason_code.strip())
        if self.action is ToolRecoveryAction.EXECUTE and not self.safe_to_execute:
            raise ToolRecoveryError("execute decision must be safe_to_execute")
        if self.requires_reconciliation and self.safe_to_execute:
            raise ToolRecoveryError(
                "reconciliation-required decision cannot execute"
            )
        if (
            self.action is ToolRecoveryAction.USE_COMMITTED_RECEIPT
            and self.tool_receipt_ref is None
        ):
            raise ToolRecoveryError(
                "committed receipt decision requires tool_receipt_ref"
            )


_CONSEQUENTIAL = frozenset(
    {
        SideEffectClass.REVERSIBLE_WRITE,
        SideEffectClass.EXTERNAL_WRITE,
        SideEffectClass.SECURITY_SENSITIVE,
    }
)


def tool_receipt_ref(receipt: ToolExecutionReceipt) -> str:
    if not isinstance(receipt, ToolExecutionReceipt):
        raise TypeError("receipt must be ToolExecutionReceipt")
    return "tool-receipt:" + receipt.receipt_id


def map_tool_side_effect(manifest: ToolManifest) -> SideEffectClass:
    """Conservatively project canonical tool authority into chat semantics."""

    if not isinstance(manifest, ToolManifest):
        raise TypeError("manifest must be ToolManifest")

    if (
        manifest.risk_class is ToolRiskClass.CRITICAL
        or manifest.authority_class
        in {
            ToolAuthorityClass.DESTRUCTIVE,
            ToolAuthorityClass.PRIVILEGED,
        }
        or manifest.side_effect_class
        in {
            ToolSideEffectClass.LOCAL_IRREVERSIBLE,
            ToolSideEffectClass.EXTERNAL_IRREVERSIBLE,
        }
        or manifest.effect is ToolEffect.IRREVERSIBLE
    ):
        return SideEffectClass.SECURITY_SENSITIVE

    if (
        manifest.authority_class is ToolAuthorityClass.EXTERNAL_COMMIT
        or manifest.side_effect_class
        is ToolSideEffectClass.EXTERNAL_REVERSIBLE
    ):
        return SideEffectClass.EXTERNAL_WRITE

    if (
        manifest.authority_class is ToolAuthorityClass.WRITE
        or manifest.side_effect_class
        is ToolSideEffectClass.LOCAL_REVERSIBLE
        or manifest.effect is ToolEffect.REVERSIBLE
    ):
        return SideEffectClass.REVERSIBLE_WRITE

    return SideEffectClass.READ_ONLY


def _validate_binding(
    snapshot: TurnSnapshot,
    request: ToolExecutionRequest,
    manifest: ToolManifest,
) -> None:
    if not isinstance(snapshot, TurnSnapshot):
        raise TypeError("snapshot must be TurnSnapshot")
    if not isinstance(request, ToolExecutionRequest):
        raise TypeError("request must be ToolExecutionRequest")
    if not isinstance(manifest, ToolManifest):
        raise TypeError("manifest must be ToolManifest")
    if snapshot.operation_id != request.operation_id:
        raise ToolRecoveryError(
            "tool request belongs to a different turn operation"
        )
    if manifest.tool_id != request.tool_id:
        raise ToolRecoveryError(
            "tool manifest does not match tool request"
        )


def _validate_receipt(
    request: ToolExecutionRequest,
    receipt: ToolExecutionReceipt,
) -> None:
    if not isinstance(receipt, ToolExecutionReceipt):
        raise TypeError("receipt must be ToolExecutionReceipt")
    if (
        receipt.request_id != request.request_id
        or receipt.operation_id != request.operation_id
        or receipt.execution_id != request.execution_id
        or receipt.turn_id != request.turn_id
        or receipt.call_id != request.call_id
        or receipt.tenant_id != request.tenant_id
        or receipt.tool_id != request.tool_id
        or receipt.idempotency_key != request.idempotency_key
        or receipt.arguments_digest != request.arguments_digest
        or receipt.data_class != request.data_class
        or receipt.transfer_purpose != request.transfer_purpose
    ):
        raise ToolRecoveryError(
            "tool receipt does not match canonical request identity"
        )


def _approval_required(manifest: ToolManifest) -> bool:
    return (
        manifest.approval_required
        or manifest.approval_policy
        in {
            ToolApprovalPolicy.ALWAYS,
            ToolApprovalPolicy.OPERATOR_ONLY,
        }
    )


def decide_tool_preflight(
    snapshot: TurnSnapshot,
    request: ToolExecutionRequest,
    manifest: ToolManifest,
    reservation: ToolReservation | None,
) -> ToolRecoveryDecision:
    """Decide whether the canonical tool runtime may be invoked."""

    _validate_binding(snapshot, request, manifest)
    if snapshot.state not in {
        TurnState.TOOL_REQUIRED,
        TurnState.AWAITING_USER,
    }:
        raise ToolRecoveryError(
            "tool preflight requires TOOL_REQUIRED or AWAITING_USER"
        )
    side_effect = map_tool_side_effect(manifest)

    if _approval_required(manifest):
        expected = approval_ref_for_request(request)
        if request.approval_ref is None:
            return ToolRecoveryDecision(
                action=ToolRecoveryAction.WAIT_FOR_APPROVAL,
                reason_code="approval-required",
                side_effect=side_effect,
                next_state=TurnState.AWAITING_USER,
                safe_to_execute=False,
                requires_user_approval=True,
            )
        if request.approval_ref != expected:
            return ToolRecoveryDecision(
                action=ToolRecoveryAction.WAIT_FOR_APPROVAL,
                reason_code="approval-binding-mismatch",
                side_effect=side_effect,
                next_state=TurnState.AWAITING_USER,
                safe_to_execute=False,
                requires_user_approval=True,
            )

    if reservation is not None:
        if not isinstance(reservation, ToolReservation):
            raise TypeError("reservation must be ToolReservation or None")
        if reservation.status == "in_doubt":
            return ToolRecoveryDecision(
                action=ToolRecoveryAction.RECONCILE,
                reason_code="durable-tool-reservation-in-doubt",
                side_effect=side_effect,
                next_state=TurnState.TOOL_EXECUTING,
                safe_to_execute=False,
                requires_reconciliation=True,
            )
        if reservation.status == "committed":
            assert reservation.receipt is not None
            _validate_receipt(request, reservation.receipt)
            return ToolRecoveryDecision(
                action=ToolRecoveryAction.USE_COMMITTED_RECEIPT,
                reason_code="durable-tool-receipt-present",
                side_effect=side_effect,
                next_state=TurnState.MODEL_RUNNING,
                safe_to_execute=False,
                tool_receipt_ref=tool_receipt_ref(reservation.receipt),
            )
        if reservation.status != "owner":
            raise ToolRecoveryError("unknown tool reservation state")

    return ToolRecoveryDecision(
        action=ToolRecoveryAction.EXECUTE,
        reason_code="tool-execution-admitted",
        side_effect=side_effect,
        next_state=TurnState.TOOL_EXECUTING,
        safe_to_execute=True,
    )


def preflight_event(
    snapshot: TurnSnapshot,
    request: ToolExecutionRequest,
    decision: ToolRecoveryDecision,
    *,
    observed_at: datetime,
) -> TurnEvent:
    """Turn one preflight decision into its durable journal transition."""

    if not isinstance(decision, ToolRecoveryDecision):
        raise TypeError("decision must be ToolRecoveryDecision")
    if snapshot.operation_id != request.operation_id:
        raise ToolRecoveryError("preflight event operation mismatch")

    call_id = request.call_id or request.request_id
    if decision.action is ToolRecoveryAction.WAIT_FOR_APPROVAL:
        if snapshot.state is not TurnState.TOOL_REQUIRED:
            raise ToolRecoveryError(
                "approval wait transition must start at TOOL_REQUIRED"
            )
        return make_event(
            snapshot,
            TurnState.AWAITING_USER,
            observed_at=observed_at,
            reason_code=decision.reason_code,
            tool_call_id=call_id,
            tool_side_effect=decision.side_effect,
        )

    if decision.action in {
        ToolRecoveryAction.EXECUTE,
        ToolRecoveryAction.RECONCILE,
    }:
        return make_event(
            snapshot,
            TurnState.TOOL_EXECUTING,
            observed_at=observed_at,
            reason_code=decision.reason_code,
            tool_call_id=call_id,
            tool_side_effect=decision.side_effect,
            external_effect_started=decision.side_effect in _CONSEQUENTIAL,
        )

    if decision.action is ToolRecoveryAction.USE_COMMITTED_RECEIPT:
        return make_event(
            snapshot,
            TurnState.MODEL_RUNNING,
            observed_at=observed_at,
            reason_code=decision.reason_code,
            tool_receipt_ref=decision.tool_receipt_ref,
        )

    raise ToolRecoveryError(
        "unsupported tool preflight action"
    )


def committed_receipt_event(
    snapshot: TurnSnapshot,
    request: ToolExecutionRequest,
    receipt: ToolExecutionReceipt,
    *,
    observed_at: datetime,
) -> TurnEvent:
    """Advance a TOOL_EXECUTING turn using a durable canonical receipt."""

    _validate_receipt(request, receipt)
    if snapshot.operation_id != request.operation_id:
        raise ToolRecoveryError("receipt event operation mismatch")
    if snapshot.state is not TurnState.TOOL_EXECUTING:
        raise ToolRecoveryError(
            "committed receipt requires TOOL_EXECUTING state"
        )
    if receipt.error_code == "execution_in_doubt":
        raise ToolRecoveryError(
            "execution_in_doubt is not a committed resolution"
        )
    return make_event(
        snapshot,
        TurnState.MODEL_RUNNING,
        observed_at=observed_at,
        reason_code=(
            "tool-succeeded"
            if receipt.status.value == "succeeded"
            else "tool-terminal-receipt"
        ),
        tool_receipt_ref=tool_receipt_ref(receipt),
    )


def reconciliation_event(
    snapshot: TurnSnapshot,
    request: ToolExecutionRequest,
    reconciliation: ToolReconciliationReceipt,
    *,
    observed_at: datetime,
    committed_receipt: ToolExecutionReceipt | None = None,
) -> TurnEvent:
    """Resolve an ambiguous tool turn using durable reconciliation evidence."""

    if not isinstance(reconciliation, ToolReconciliationReceipt):
        raise TypeError(
            "reconciliation must be ToolReconciliationReceipt"
        )
    if snapshot.state is not TurnState.TOOL_EXECUTING:
        raise ToolRecoveryError(
            "reconciliation requires TOOL_EXECUTING state"
        )
    if (
        reconciliation.tenant_id != request.tenant_id
        or reconciliation.operation_id != request.operation_id
        or reconciliation.execution_id != request.execution_id
        or reconciliation.turn_id != request.turn_id
        or reconciliation.call_id != request.call_id
        or reconciliation.idempotency_key != request.idempotency_key
        or reconciliation.request_id != request.request_id
        or reconciliation.tool_id != request.tool_id
        or reconciliation.arguments_digest != request.arguments_digest
    ):
        raise ToolRecoveryError(
            "tool reconciliation does not match canonical request identity"
        )

    if reconciliation.outcome is ToolReconciliationOutcome.NO_EFFECT:
        if committed_receipt is not None:
            raise ToolRecoveryError(
                "no-effect reconciliation cannot carry committed receipt"
            )
        return make_event(
            snapshot,
            TurnState.TOOL_REQUIRED,
            observed_at=observed_at,
            reason_code="tool-reconciled-no-effect",
            tool_reconciliation_ref=reconciliation.reference,
        )

    if reconciliation.outcome is ToolReconciliationOutcome.COMMITTED:
        if committed_receipt is None:
            raise ToolRecoveryError(
                "committed reconciliation requires canonical receipt"
            )
        _validate_receipt(request, committed_receipt)
        if reconciliation.receipt_id != committed_receipt.receipt_id:
            raise ToolRecoveryError(
                "reconciliation receipt identity mismatch"
            )
        return make_event(
            snapshot,
            TurnState.MODEL_RUNNING,
            observed_at=observed_at,
            reason_code="tool-reconciled-committed",
            tool_receipt_ref=tool_receipt_ref(committed_receipt),
            tool_reconciliation_ref=reconciliation.reference,
        )

    raise ToolRecoveryError("unknown reconciliation outcome")


@dataclass(frozen=True, slots=True)
class ToolRestartResolution:
    """Bounded restart/reconciliation result for one canonical tool call.

    The resolution never executes a tool.  It either returns the exact durable
    event that may advance the chat journal, or a non-executing decision saying
    which canonical recovery step remains required.
    """

    action: RecoveryAction
    reason_code: str
    event: TurnEvent | None
    requires_reconciliation: bool
    safe_to_reexecute: bool
    authority_scope: str = "tool-restart-reconciliation-only"
    production_authority: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.action, RecoveryAction):
            object.__setattr__(
                self,
                "action",
                RecoveryAction(str(self.action)),
            )
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ToolRecoveryError("restart resolution reason_code is required")
        object.__setattr__(self, "reason_code", self.reason_code.strip())
        if self.event is not None and not isinstance(self.event, TurnEvent):
            raise TypeError("event must be TurnEvent or None")
        if self.requires_reconciliation and self.safe_to_reexecute:
            raise ToolRecoveryError(
                "reconciliation-required restart cannot be safe to reexecute"
            )
        if self.authority_scope != "tool-restart-reconciliation-only":
            raise ToolRecoveryError("restart resolution authority scope escalated")
        if self.production_authority is not False:
            raise ToolRecoveryError("restart resolution cannot execute tools")


def resolve_tool_restart(
    snapshot: TurnSnapshot,
    request: ToolExecutionRequest,
    manifest: ToolManifest,
    *,
    observed_at: datetime,
    reservation: ToolReservation | None = None,
    reconciliation: ToolReconciliationReceipt | None = None,
    committed_receipt: ToolExecutionReceipt | None = None,
) -> ToolRestartResolution:
    """Bind RecoveryPlanner output to canonical tool receipt reconciliation.

    Consequential ambiguity is never converted into a retry.  A durable
    reconciliation receipt is required before the journal can leave the
    ambiguous TOOL_EXECUTING state.  Read-only work may be re-executed only
    when the generic turn recovery planner already classified it as safe.
    """

    _validate_binding(snapshot, request, manifest)
    if snapshot.state is not TurnState.TOOL_EXECUTING:
        raise ToolRecoveryError(
            "tool restart resolution requires TOOL_EXECUTING state"
        )

    recovery = RecoveryPlanner.plan(snapshot)

    if recovery.action is RecoveryAction.RECONCILE_TOOL:
        if reconciliation is None:
            return ToolRestartResolution(
                action=recovery.action,
                reason_code=recovery.reason_code,
                event=None,
                requires_reconciliation=True,
                safe_to_reexecute=False,
            )
        event = reconciliation_event(
            snapshot,
            request,
            reconciliation,
            observed_at=observed_at,
            committed_receipt=committed_receipt,
        )
        return ToolRestartResolution(
            action=recovery.action,
            reason_code=(
                "canonical-tool-reconciliation:"
                + reconciliation.outcome.value
            ),
            event=event,
            requires_reconciliation=False,
            safe_to_reexecute=False,
        )

    if recovery.action is RecoveryAction.RESUME_VERIFICATION:
        receipt = committed_receipt
        if receipt is None and reservation is not None:
            if not isinstance(reservation, ToolReservation):
                raise TypeError("reservation must be ToolReservation or None")
            receipt = reservation.receipt
        if receipt is None:
            raise ToolRecoveryError(
                "durable tool receipt reference has no canonical receipt body"
            )
        event = committed_receipt_event(
            snapshot,
            request,
            receipt,
            observed_at=observed_at,
        )
        return ToolRestartResolution(
            action=recovery.action,
            reason_code="canonical-tool-receipt-recovered",
            event=event,
            requires_reconciliation=False,
            safe_to_reexecute=False,
        )

    if recovery.action is RecoveryAction.RETRY_TOOL:
        side_effect = map_tool_side_effect(manifest)
        if side_effect is not SideEffectClass.READ_ONLY:
            raise ToolRecoveryError(
                "only read-only tool work may be reexecuted without reconciliation"
            )
        if reservation is not None:
            if not isinstance(reservation, ToolReservation):
                raise TypeError("reservation must be ToolReservation or None")
            if reservation.status == "in_doubt":
                raise ToolRecoveryError(
                    "in-doubt reservation overrides generic retry safety"
                )
            if reservation.status == "committed":
                if reservation.receipt is None:
                    raise ToolRecoveryError(
                        "committed reservation is missing canonical receipt"
                    )
                event = committed_receipt_event(
                    snapshot,
                    request,
                    reservation.receipt,
                    observed_at=observed_at,
                )
                return ToolRestartResolution(
                    action=RecoveryAction.RESUME_VERIFICATION,
                    reason_code="canonical-tool-receipt-recovered",
                    event=event,
                    requires_reconciliation=False,
                    safe_to_reexecute=False,
                )
        return ToolRestartResolution(
            action=recovery.action,
            reason_code=recovery.reason_code,
            event=None,
            requires_reconciliation=False,
            safe_to_reexecute=True,
        )

    raise ToolRecoveryError(
        "turn recovery state is not a tool restart state: "
        + recovery.action.value
    )


__all__ = [
    "ToolRecoveryAction",
    "ToolRecoveryDecision",
    "ToolRecoveryError",
    "ToolRestartResolution",
    "committed_receipt_event",
    "decide_tool_preflight",
    "map_tool_side_effect",
    "preflight_event",
    "reconciliation_event",
    "resolve_tool_restart",
    "tool_receipt_ref",
]
