"""Live post-transition health proof for the P2 runtime spine."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from skeleton.contracts.operation import OperationState
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.spine_runtime_transition_slot import SpineRuntimeSlot


class SpineRuntimeTransitionHealthError(RuntimeError):
    """Post-transition health proof failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionHealth:
    """Prove live operation continuity after the effectful runtime transition."""

    def probe(
        self,
        *,
        execution: dict[str, Any],
        execution_verify: dict[str, Any],
        slot: SpineRuntimeSlot,
        candidate_runtime: DurableOperationRuntime,
        fence: SQLiteConsistencyFence,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(execution, dict)
            or execution.get("kind") != "spine_runtime_transition_execution"
            or execution.get("transition_executed") is not True
            or execution.get("runtime_object_replaced") is not True
            or execution.get("dispatcher_running") is not True
            or execution.get("fence_moved") is not True
            or execution.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionHealthError(
                "verified effectful transition is required"
            )
        execution_id = execution.get("execution_id")
        execution_digest = execution.get("digest")
        transition_id = execution.get("transition_id")
        deployment_id = execution.get("deployment_id")
        for field, value in (
            ("execution identity", execution_id),
            ("execution digest", execution_digest),
            ("transition identity", transition_id),
        ):
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionHealthError(f"{field} is invalid")
        if not isinstance(deployment_id, str) or not deployment_id:
            raise SpineRuntimeTransitionHealthError(
                "deployment identity is missing"
            )
        if (
            not isinstance(execution_verify, dict)
            or execution_verify.get("kind") != "spine_runtime_transition_execution_verify"
            or execution_verify.get("verified") is not True
            or execution_verify.get("execution_id") != execution_id
            or execution_verify.get("execution_digest") != execution_digest
            or execution_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeTransitionHealthError(
                "independent execution verification is required"
            )
        if not isinstance(slot, SpineRuntimeSlot):
            raise SpineRuntimeTransitionHealthError("runtime slot is required")
        if not isinstance(candidate_runtime, DurableOperationRuntime):
            raise SpineRuntimeTransitionHealthError(
                "candidate runtime must be durable"
            )
        if not isinstance(fence, SQLiteConsistencyFence):
            raise SpineRuntimeTransitionHealthError(
                "consistency fence is required"
            )
        if slot.runtime is not candidate_runtime:
            raise SpineRuntimeTransitionHealthError(
                "runtime slot is not on transitioned candidate"
            )
        slot_generation = execution.get("slot_generation_after")
        if slot.generation != slot_generation:
            raise SpineRuntimeTransitionHealthError(
                "runtime slot generation changed after transition"
            )
        if candidate_runtime.dispatcher_running is not True:
            raise SpineRuntimeTransitionHealthError(
                "candidate dispatcher is not running"
            )

        tenant_id = execution.get("tenant_id")
        resource_id = execution.get("resource_id")
        expected_epoch = execution.get("fence_epoch_after")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise SpineRuntimeTransitionHealthError("tenant identity is missing")
        if not isinstance(resource_id, str) or not resource_id:
            raise SpineRuntimeTransitionHealthError("resource identity is missing")
        if (
            isinstance(expected_epoch, bool)
            or not isinstance(expected_epoch, int)
            or expected_epoch < 2
        ):
            raise SpineRuntimeTransitionHealthError(
                "transition fence epoch is invalid"
            )
        token = fence.read(tenant_id=tenant_id, resource_id=resource_id)
        if token.epoch != expected_epoch:
            raise SpineRuntimeTransitionHealthError(
                "transition fence epoch changed before health probe"
            )
        if token.writer_id != f"runtime-transition:{deployment_id}":
            raise SpineRuntimeTransitionHealthError(
                "transition fence writer changed before health probe"
            )

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRuntimeTransitionHealthError(
                "now must be timezone-aware"
            )
        instant = instant.astimezone(timezone.utc)
        result = candidate_runtime.reason(
            "p2-runtime-transition-health",
            context={
                "execution_id": execution_id,
                "transition_id": transition_id,
            },
            tenant_id=tenant_id,
            actor_id="runtime-transition-health",
            idempotency_key=f"p2-health:{execution_id}",
            trace_id=f"p2-health:{execution_id}",
        )
        if not isinstance(result, dict) or result.get("error"):
            raise SpineRuntimeTransitionHealthError(
                "candidate runtime health operation failed"
            )
        if result.get("operation_state") != OperationState.COMPLETED.value:
            raise SpineRuntimeTransitionHealthError(
                "candidate runtime health operation did not complete"
            )
        if result.get("idempotent_replay") is not False:
            raise SpineRuntimeTransitionHealthError(
                "candidate runtime health operation unexpectedly replayed"
            )
        operation_id = result.get("operation_id")
        operation_version = result.get("operation_version")
        if not isinstance(operation_id, str) or not operation_id:
            raise SpineRuntimeTransitionHealthError(
                "candidate runtime health operation identity is missing"
            )
        if (
            isinstance(operation_version, bool)
            or not isinstance(operation_version, int)
            or operation_version < 1
        ):
            raise SpineRuntimeTransitionHealthError(
                "candidate runtime health operation version is invalid"
            )
        stored = candidate_runtime.operations.get(operation_id)
        if not stored.terminal or stored.envelope.state is not OperationState.COMPLETED:
            raise SpineRuntimeTransitionHealthError(
                "candidate runtime durable operation is not completed"
            )
        pending = candidate_runtime.operations.pending_outbox_count(
            operation_id=operation_id
        )
        if pending != 0:
            raise SpineRuntimeTransitionHealthError(
                "candidate runtime health outbox is not drained"
            )

        token_after = fence.read(tenant_id=tenant_id, resource_id=resource_id)
        if token_after.epoch != expected_epoch:
            raise SpineRuntimeTransitionHealthError(
                "health probe moved transition fence"
            )
        if slot.runtime is not candidate_runtime or slot.generation != slot_generation:
            raise SpineRuntimeTransitionHealthError(
                "runtime slot changed during health probe"
            )
        if candidate_runtime.dispatcher_running is not True:
            raise SpineRuntimeTransitionHealthError(
                "candidate dispatcher stopped during health probe"
            )

        evidence = {
            "execution_id": execution_id,
            "execution_digest": execution_digest,
            "transition_id": transition_id,
            "deployment_id": deployment_id,
            "target_driver": "pymongo-async",
            "tenant_id": tenant_id,
            "resource_id": resource_id,
            "checked_at": instant.isoformat(),
            "operation_id": operation_id,
            "operation_version": operation_version,
            "slot_generation": slot_generation,
            "fence_epoch": expected_epoch,
            "pending_outbox": 0,
            "health_qualified": True,
            "operation_continuity": True,
            "runtime_object_replaced": True,
            "dispatcher_running": True,
            "fence_stable": True,
            "rollback_available": True,
            "runtime_activated": False,
        }
        return {
            "kind": "spine_runtime_transition_health",
            "hit": True,
            "law": "post-transition-health-proves-live-operation-continuity",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
