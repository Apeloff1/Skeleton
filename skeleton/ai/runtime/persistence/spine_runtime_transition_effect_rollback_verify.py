"""Independent verifier for compensating P2 transition rollback evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineRuntimeTransitionEffectRollbackVerifyError(RuntimeError):
    """Effect rollback verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionEffectRollbackVerify:
    """Verify runtime restoration and compensation fence without activation."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if (
            not isinstance(card, dict)
            or card.get("kind") != "spine_runtime_transition_effect_rollback"
        ):
            raise SpineRuntimeTransitionEffectRollbackVerifyError(
                "effect rollback kind mismatch"
            )
        for field in (
            "rollback_executed",
            "runtime_object_restored",
            "candidate_dispatcher_stopped",
            "fence_compensated",
            "transition_executed",
        ):
            if card.get(field) is not True:
                raise SpineRuntimeTransitionEffectRollbackVerifyError(
                    f"rollback proof missing: {field}"
                )
        if card.get("original_dispatcher_running") is not False:
            raise SpineRuntimeTransitionEffectRollbackVerifyError(
                "original dispatcher unexpectedly running"
            )
        if card.get("runtime_activated") is not False:
            raise SpineRuntimeTransitionEffectRollbackVerifyError(
                "rollback evidence cannot assert activation"
            )
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionEffectRollbackVerifyError(
                "transition target driver changed"
            )

        for field in (
            "rollback_id",
            "execution_id",
            "execution_digest",
            "transition_id",
        ):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionEffectRollbackVerifyError(
                    f"{field} is invalid"
                )
        for field in (
            "deployment_id",
            "tenant_id",
            "resource_id",
            "rolled_back_at",
        ):
            value = card.get(field)
            if not isinstance(value, str) or not value:
                raise SpineRuntimeTransitionEffectRollbackVerifyError(
                    f"{field} is missing"
                )

        before = card.get("rollback_epoch_before")
        after = card.get("rollback_epoch_after")
        generation_before = card.get("slot_generation_before")
        generation_after = card.get("slot_generation_after")
        if (
            isinstance(before, bool)
            or not isinstance(before, int)
            or before < 2
            or after != before + 1
        ):
            raise SpineRuntimeTransitionEffectRollbackVerifyError(
                "rollback fence did not advance exactly once"
            )
        if (
            isinstance(generation_before, bool)
            or not isinstance(generation_before, int)
            or generation_before < 1
            or generation_after != generation_before + 1
        ):
            raise SpineRuntimeTransitionEffectRollbackVerifyError(
                "runtime slot generation did not restore exactly once"
            )

        expected_id = hashlib.sha256(
            (
                f"{card['execution_digest']}|{card['execution_id']}|"
                f"{card['deployment_id']}|{card['resource_id']}|pymongo-async"
            ).encode("utf-8")
        ).hexdigest()
        if card["rollback_id"] != expected_id:
            raise SpineRuntimeTransitionEffectRollbackVerifyError(
                "effect rollback identity mismatch"
            )

        evidence = {
            "rollback_id": card["rollback_id"],
            "execution_id": card["execution_id"],
            "execution_digest": card["execution_digest"],
            "transition_id": card["transition_id"],
            "deployment_id": card["deployment_id"],
            "target_driver": card["target_driver"],
            "tenant_id": card["tenant_id"],
            "resource_id": card["resource_id"],
            "rolled_back_at": card["rolled_back_at"],
            "rollback_epoch_before": before,
            "rollback_epoch_after": after,
            "slot_generation_before": generation_before,
            "slot_generation_after": generation_after,
            "rollback_executed": card["rollback_executed"],
            "runtime_object_restored": card["runtime_object_restored"],
            "candidate_dispatcher_stopped": card["candidate_dispatcher_stopped"],
            "original_dispatcher_running": card["original_dispatcher_running"],
            "fence_compensated": card["fence_compensated"],
            "transition_executed": card["transition_executed"],
            "runtime_activated": card["runtime_activated"],
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineRuntimeTransitionEffectRollbackVerifyError(
                "effect rollback digest mismatch"
            )
        return {
            "kind": "spine_runtime_transition_effect_rollback_verify",
            "hit": True,
            "law": "compensation-verification-does-not-promote-runtime-activation",
            "citation": "VOL-134",
            "rollback_id": card["rollback_id"],
            "rollback_digest": digest,
            "execution_id": card["execution_id"],
            "verified": True,
            "rollback_executed": True,
            "runtime_object_restored": True,
            "candidate_dispatcher_stopped": True,
            "fence_compensated": True,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
