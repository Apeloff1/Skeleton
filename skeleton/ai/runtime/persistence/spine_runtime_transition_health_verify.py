"""Independent live verifier for P2 post-transition health evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.contracts.operation import OperationState
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.spine_runtime_transition_slot import SpineRuntimeSlot


class SpineRuntimeTransitionHealthVerifyError(RuntimeError):
    """Post-transition health verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionHealthVerify:
    """Re-read live runtime, durable operation, slot, and fence state."""

    def verify(
        self,
        card: dict[str, Any],
        *,
        slot: SpineRuntimeSlot,
        candidate_runtime: DurableOperationRuntime,
        fence: SQLiteConsistencyFence,
    ) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_runtime_transition_health":
            raise SpineRuntimeTransitionHealthVerifyError(
                "transition health kind mismatch"
            )
        if card.get("health_qualified") is not True:
            raise SpineRuntimeTransitionHealthVerifyError(
                "transition health is not qualified"
            )
        if card.get("operation_continuity") is not True:
            raise SpineRuntimeTransitionHealthVerifyError(
                "operation continuity is not proven"
            )
        for field in (
            "runtime_object_replaced",
            "dispatcher_running",
            "fence_stable",
            "rollback_available",
        ):
            if card.get(field) is not True:
                raise SpineRuntimeTransitionHealthVerifyError(
                    f"health invariant missing: {field}"
                )
        if card.get("runtime_activated") is not False:
            raise SpineRuntimeTransitionHealthVerifyError(
                "health evidence cannot self-activate runtime"
            )
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionHealthVerifyError(
                "transition target driver changed"
            )
        for field in ("execution_id", "execution_digest", "transition_id"):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionHealthVerifyError(
                    f"{field} is invalid"
                )
        for field in (
            "deployment_id",
            "tenant_id",
            "resource_id",
            "checked_at",
            "operation_id",
        ):
            value = card.get(field)
            if not isinstance(value, str) or not value:
                raise SpineRuntimeTransitionHealthVerifyError(
                    f"{field} is missing"
                )
        if card.get("pending_outbox") != 0:
            raise SpineRuntimeTransitionHealthVerifyError(
                "health outbox is not drained"
            )

        evidence = {
            "execution_id": card["execution_id"],
            "execution_digest": card["execution_digest"],
            "transition_id": card["transition_id"],
            "deployment_id": card["deployment_id"],
            "target_driver": card["target_driver"],
            "tenant_id": card["tenant_id"],
            "resource_id": card["resource_id"],
            "checked_at": card["checked_at"],
            "operation_id": card["operation_id"],
            "operation_version": card["operation_version"],
            "slot_generation": card["slot_generation"],
            "fence_epoch": card["fence_epoch"],
            "pending_outbox": card["pending_outbox"],
            "health_qualified": card["health_qualified"],
            "operation_continuity": card["operation_continuity"],
            "runtime_object_replaced": card["runtime_object_replaced"],
            "dispatcher_running": card["dispatcher_running"],
            "fence_stable": card["fence_stable"],
            "rollback_available": card["rollback_available"],
            "runtime_activated": card["runtime_activated"],
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineRuntimeTransitionHealthVerifyError(
                "transition health digest mismatch"
            )

        if not isinstance(slot, SpineRuntimeSlot) or slot.runtime is not candidate_runtime:
            raise SpineRuntimeTransitionHealthVerifyError(
                "runtime slot no longer points to candidate"
            )
        if slot.generation != card.get("slot_generation"):
            raise SpineRuntimeTransitionHealthVerifyError(
                "runtime slot generation changed"
            )
        if (
            not isinstance(candidate_runtime, DurableOperationRuntime)
            or candidate_runtime.dispatcher_running is not True
        ):
            raise SpineRuntimeTransitionHealthVerifyError(
                "candidate dispatcher is not running"
            )
        if not isinstance(fence, SQLiteConsistencyFence):
            raise SpineRuntimeTransitionHealthVerifyError(
                "consistency fence is required"
            )
        token = fence.read(
            tenant_id=card["tenant_id"],
            resource_id=card["resource_id"],
        )
        if token.epoch != card.get("fence_epoch"):
            raise SpineRuntimeTransitionHealthVerifyError(
                "transition fence epoch changed"
            )
        if token.writer_id != f"runtime-transition:{card['deployment_id']}":
            raise SpineRuntimeTransitionHealthVerifyError(
                "transition fence writer changed"
            )

        stored = candidate_runtime.operations.get(card["operation_id"])
        if (
            stored.envelope.state is not OperationState.COMPLETED
            or stored.version != card.get("operation_version")
        ):
            raise SpineRuntimeTransitionHealthVerifyError(
                "durable health operation changed"
            )
        if candidate_runtime.operations.pending_outbox_count(
            operation_id=card["operation_id"]
        ) != 0:
            raise SpineRuntimeTransitionHealthVerifyError(
                "durable health outbox changed"
            )

        return {
            "kind": "spine_runtime_transition_health_verify",
            "hit": True,
            "law": "live-health-verification-does-not-promote-runtime-activation",
            "citation": "VOL-134",
            "health_digest": digest,
            "execution_id": card["execution_id"],
            "deployment_id": card["deployment_id"],
            "target_driver": card["target_driver"],
            "tenant_id": card["tenant_id"],
            "resource_id": card["resource_id"],
            "operation_id": card["operation_id"],
            "operation_version": card["operation_version"],
            "slot_generation": card["slot_generation"],
            "fence_epoch": card["fence_epoch"],
            "verified": True,
            "health_qualified": True,
            "operation_continuity": True,
            "dispatcher_running": True,
            "fence_stable": True,
            "rollback_available": True,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
