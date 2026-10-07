"""Independent verifier for P2 runtime transition rollback witnesses."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineRuntimeTransitionRollbackVerifyError(RuntimeError):
    """Rollback witness verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionRollbackVerify:
    """Verify the no-effect rollback boundary without granting activation."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_runtime_transition_rollback_witness":
            raise SpineRuntimeTransitionRollbackVerifyError("rollback witness kind mismatch")
        if card.get("rollback_checked") is not True or card.get("rollback_verified") is not True:
            raise SpineRuntimeTransitionRollbackVerifyError("rollback witness is incomplete")
        if card.get("rollback_required") is not False or card.get("rollback_executed") is not False:
            raise SpineRuntimeTransitionRollbackVerifyError("rollback witness unexpectedly executed rollback")
        if card.get("transition_attempted") is not True or card.get("transition_executed") is not False:
            raise SpineRuntimeTransitionRollbackVerifyError("transition attempt state changed")
        if card.get("runtime_driver_selected") is not True:
            raise SpineRuntimeTransitionRollbackVerifyError("runtime driver selection disappeared")
        for field in (
            "runtime_object_replaced",
            "dispatcher_started",
            "fence_moved",
            "runtime_activated",
        ):
            if card.get(field) is not False:
                raise SpineRuntimeTransitionRollbackVerifyError(f"rollback witness changed invariant: {field}")
        if card.get("dispatcher_identity_stable") is not True:
            raise SpineRuntimeTransitionRollbackVerifyError("dispatcher identity is unstable")
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionRollbackVerifyError("transition target driver changed")

        for field in ("attempt_id", "attempt_digest", "transition_id"):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionRollbackVerifyError(f"{field} is invalid")
        deployment_id = card.get("deployment_id")
        if not isinstance(deployment_id, str) or not deployment_id:
            raise SpineRuntimeTransitionRollbackVerifyError("deployment identity is missing")

        evidence = {
            "attempt_id": card["attempt_id"],
            "attempt_digest": card["attempt_digest"],
            "transition_id": card["transition_id"],
            "deployment_id": deployment_id,
            "target_driver": card["target_driver"],
            "rollback_checked": card["rollback_checked"],
            "rollback_required": card["rollback_required"],
            "rollback_executed": card["rollback_executed"],
            "rollback_verified": card["rollback_verified"],
            "transition_attempted": card["transition_attempted"],
            "transition_executed": card["transition_executed"],
            "runtime_driver_selected": card["runtime_driver_selected"],
            "runtime_object_replaced": card["runtime_object_replaced"],
            "dispatcher_identity_stable": card["dispatcher_identity_stable"],
            "dispatcher_started": card["dispatcher_started"],
            "fence_moved": card["fence_moved"],
            "runtime_activated": card["runtime_activated"],
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineRuntimeTransitionRollbackVerifyError("rollback witness digest mismatch")

        return {
            "kind": "spine_runtime_transition_rollback_verify",
            "hit": False,
            "law": "rollback-verification-does-not-authorize-runtime-promotion",
            "citation": "VOL-134",
            "attempt_id": card["attempt_id"],
            "rollback_digest": digest,
            "verified": True,
            "rollback_required": False,
            "rollback_verified": True,
            "transition_attempted": True,
            "transition_executed": False,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_started": False,
            "fence_moved": False,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
