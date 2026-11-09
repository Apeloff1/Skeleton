"""Independent verifier for effectful P2 runtime transition evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineRuntimeTransitionExecutionVerifyError(RuntimeError):
    """Effectful transition verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionExecutionVerify:
    """Verify direct runtime/dispatcher/fence effects without claiming activation."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_runtime_transition_execution":
            raise SpineRuntimeTransitionExecutionVerifyError(
                "transition execution kind mismatch"
            )
        if card.get("transition_executed") is not True:
            raise SpineRuntimeTransitionExecutionVerifyError(
                "transition did not execute"
            )
        if card.get("runtime_driver_selected") is not True:
            raise SpineRuntimeTransitionExecutionVerifyError(
                "runtime driver selection disappeared"
            )
        for field in (
            "runtime_object_replaced",
            "dispatcher_started",
            "dispatcher_running",
            "fence_moved",
            "rollback_required",
        ):
            if card.get(field) is not True:
                raise SpineRuntimeTransitionExecutionVerifyError(
                    f"effectful transition proof missing: {field}"
                )
        if card.get("runtime_activated") is not False:
            raise SpineRuntimeTransitionExecutionVerifyError(
                "execution evidence cannot self-activate runtime"
            )
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionExecutionVerifyError(
                "transition target driver changed"
            )

        for field in (
            "execution_id",
            "rollback_digest",
            "attempt_id",
            "transition_id",
        ):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionExecutionVerifyError(
                    f"{field} is invalid"
                )
        for field in ("deployment_id", "tenant_id", "resource_id", "executed_at"):
            value = card.get(field)
            if not isinstance(value, str) or not value:
                raise SpineRuntimeTransitionExecutionVerifyError(
                    f"{field} is missing"
                )

        before = card.get("fence_epoch_before")
        after = card.get("fence_epoch_after")
        generation_before = card.get("slot_generation_before")
        generation_after = card.get("slot_generation_after")
        if (
            isinstance(before, bool)
            or not isinstance(before, int)
            or before < 1
            or after != before + 1
        ):
            raise SpineRuntimeTransitionExecutionVerifyError(
                "transition fence epoch is not a single advance"
            )
        if (
            isinstance(generation_before, bool)
            or not isinstance(generation_before, int)
            or generation_before < 0
            or generation_after != generation_before + 1
        ):
            raise SpineRuntimeTransitionExecutionVerifyError(
                "runtime slot generation is not a single replacement"
            )

        expected_id = hashlib.sha256(
            (
                f"{card['rollback_digest']}|{card['transition_id']}|"
                f"{card['deployment_id']}|{card['tenant_id']}|"
                f"{card['resource_id']}|pymongo-async"
            ).encode("utf-8")
        ).hexdigest()
        if card["execution_id"] != expected_id:
            raise SpineRuntimeTransitionExecutionVerifyError(
                "transition execution identity mismatch"
            )

        evidence = {
            "execution_id": card["execution_id"],
            "rollback_digest": card["rollback_digest"],
            "attempt_id": card["attempt_id"],
            "transition_id": card["transition_id"],
            "deployment_id": card["deployment_id"],
            "target_driver": card["target_driver"],
            "tenant_id": card["tenant_id"],
            "resource_id": card["resource_id"],
            "executed_at": card["executed_at"],
            "fence_epoch_before": before,
            "fence_epoch_after": after,
            "slot_generation_before": generation_before,
            "slot_generation_after": generation_after,
            "transition_executed": card["transition_executed"],
            "runtime_driver_selected": card["runtime_driver_selected"],
            "runtime_object_replaced": card["runtime_object_replaced"],
            "dispatcher_started": card["dispatcher_started"],
            "dispatcher_running": card["dispatcher_running"],
            "fence_moved": card["fence_moved"],
            "rollback_required": card["rollback_required"],
            "runtime_activated": card["runtime_activated"],
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineRuntimeTransitionExecutionVerifyError(
                "transition execution digest mismatch"
            )
        return {
            "kind": "spine_runtime_transition_execution_verify",
            "hit": True,
            "law": "effect-verification-does-not-self-promote-runtime-activation",
            "citation": "VOL-134",
            "execution_id": card["execution_id"],
            "execution_digest": digest,
            "transition_id": card["transition_id"],
            "verified": True,
            "transition_executed": True,
            "runtime_object_replaced": True,
            "dispatcher_started": True,
            "dispatcher_running": True,
            "fence_moved": True,
            "rollback_required": True,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
