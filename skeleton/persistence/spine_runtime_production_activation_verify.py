"""Independent live verifier for the P2 production activation record."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.contracts.operation import OperationState
from skeleton.persistence.consistency_fence import SQLiteConsistencyFence
from skeleton.persistence.operation_runtime import DurableOperationRuntime
from skeleton.persistence.spine_runtime_transition_slot import SpineRuntimeSlot


class SpineRuntimeProductionActivationVerifyError(RuntimeError):
    """Production activation verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeProductionActivationVerify:
    """Reconstruct activation and re-read runtime, operation, slot, and fence."""

    def verify(
        self,
        card: dict[str, Any],
        *,
        slot: SpineRuntimeSlot,
        candidate_runtime: DurableOperationRuntime,
        fence: SQLiteConsistencyFence,
    ) -> dict[str, Any]:
        if (
            not isinstance(card, dict)
            or card.get("kind") != "spine_runtime_production_activation"
        ):
            raise SpineRuntimeProductionActivationVerifyError(
                "production activation kind mismatch"
            )
        for field in (
            "authorization_consumed",
            "activation_accepted",
            "production_activation_authorized",
            "health_qualified",
            "operation_continuity",
            "runtime_object_replaced",
            "dispatcher_running",
            "fence_stable",
            "rollback_available",
            "runtime_activated",
        ):
            if card.get(field) is not True:
                raise SpineRuntimeProductionActivationVerifyError(
                    f"activation invariant missing: {field}"
                )
        if card.get("fence_moved_during_activation") is not False:
            raise SpineRuntimeProductionActivationVerifyError(
                "activation unexpectedly moved rollback fence"
            )
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeProductionActivationVerifyError(
                "activation target driver changed"
            )
        for field in (
            "activation_id",
            "authorization_id",
            "authorization_digest",
            "health_digest",
            "execution_id",
        ):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeProductionActivationVerifyError(
                    f"{field} is invalid"
                )
        for field in (
            "deployment_id",
            "tenant_id",
            "resource_id",
            "operation_id",
            "activated_at",
        ):
            value = card.get(field)
            if not isinstance(value, str) or not value:
                raise SpineRuntimeProductionActivationVerifyError(
                    f"{field} is missing"
                )
        slot_generation = card.get("slot_generation")
        fence_epoch = card.get("fence_epoch")
        operation_version = card.get("operation_version")
        if (
            isinstance(slot_generation, bool)
            or not isinstance(slot_generation, int)
            or slot_generation < 1
        ):
            raise SpineRuntimeProductionActivationVerifyError(
                "activation slot generation is invalid"
            )
        if (
            isinstance(fence_epoch, bool)
            or not isinstance(fence_epoch, int)
            or fence_epoch < 2
        ):
            raise SpineRuntimeProductionActivationVerifyError(
                "activation fence epoch is invalid"
            )
        if (
            isinstance(operation_version, bool)
            or not isinstance(operation_version, int)
            or operation_version < 1
        ):
            raise SpineRuntimeProductionActivationVerifyError(
                "activation operation version is invalid"
            )

        expected_id = hashlib.sha256(
            (
                f"{card['authorization_digest']}|{card['authorization_id']}|"
                f"{card['health_digest']}|{card['execution_id']}|"
                f"{card['deployment_id']}|{slot_generation}|{fence_epoch}|"
                f"{card['operation_id']}|pymongo-async"
            ).encode("utf-8")
        ).hexdigest()
        if card["activation_id"] != expected_id:
            raise SpineRuntimeProductionActivationVerifyError(
                "production activation identity mismatch"
            )
        evidence = {
            "activation_id": card["activation_id"],
            "authorization_id": card["authorization_id"],
            "authorization_digest": card["authorization_digest"],
            "health_digest": card["health_digest"],
            "execution_id": card["execution_id"],
            "deployment_id": card["deployment_id"],
            "target_driver": card["target_driver"],
            "tenant_id": card["tenant_id"],
            "resource_id": card["resource_id"],
            "operation_id": card["operation_id"],
            "operation_version": operation_version,
            "activated_at": card["activated_at"],
            "slot_generation": slot_generation,
            "fence_epoch": fence_epoch,
            "authorization_consumed": card["authorization_consumed"],
            "activation_accepted": card["activation_accepted"],
            "production_activation_authorized": card[
                "production_activation_authorized"
            ],
            "health_qualified": card["health_qualified"],
            "operation_continuity": card["operation_continuity"],
            "runtime_object_replaced": card["runtime_object_replaced"],
            "dispatcher_running": card["dispatcher_running"],
            "fence_stable": card["fence_stable"],
            "fence_moved_during_activation": card[
                "fence_moved_during_activation"
            ],
            "rollback_available": card["rollback_available"],
            "runtime_activated": card["runtime_activated"],
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineRuntimeProductionActivationVerifyError(
                "production activation digest mismatch"
            )

        if (
            not isinstance(slot, SpineRuntimeSlot)
            or slot.runtime is not candidate_runtime
            or slot.generation != slot_generation
        ):
            raise SpineRuntimeProductionActivationVerifyError(
                "runtime slot changed after activation"
            )
        if (
            not isinstance(candidate_runtime, DurableOperationRuntime)
            or candidate_runtime.dispatcher_running is not True
        ):
            raise SpineRuntimeProductionActivationVerifyError(
                "candidate dispatcher is not running after activation"
            )
        if not isinstance(fence, SQLiteConsistencyFence):
            raise SpineRuntimeProductionActivationVerifyError(
                "consistency fence is required"
            )
        token = fence.read(
            tenant_id=card["tenant_id"],
            resource_id=card["resource_id"],
        )
        if token.epoch != fence_epoch:
            raise SpineRuntimeProductionActivationVerifyError(
                "rollback fence changed after activation"
            )
        if token.writer_id != f"runtime-transition:{card['deployment_id']}":
            raise SpineRuntimeProductionActivationVerifyError(
                "rollback fence writer changed after activation"
            )
        stored = candidate_runtime.operations.get(card["operation_id"])
        if (
            stored.envelope.state is not OperationState.COMPLETED
            or stored.version != operation_version
        ):
            raise SpineRuntimeProductionActivationVerifyError(
                "durable health operation changed after activation"
            )
        if candidate_runtime.operations.pending_outbox_count(
            operation_id=card["operation_id"]
        ) != 0:
            raise SpineRuntimeProductionActivationVerifyError(
                "durable health outbox changed after activation"
            )
        return {
            "kind": "spine_runtime_production_activation_verify",
            "hit": True,
            "law": "activation-verification-preserves-live-rollback-boundary",
            "citation": "VOL-134",
            "activation_id": card["activation_id"],
            "activation_digest": digest,
            "authorization_id": card["authorization_id"],
            "health_digest": card["health_digest"],
            "execution_id": card["execution_id"],
            "verified": True,
            "runtime_activated": True,
            "rollback_available": True,
            "fence_moved_during_activation": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
