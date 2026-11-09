"""Independent verifier for refused P2 runtime transition attempts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineRuntimeTransitionAttemptVerifyError(RuntimeError):
    """Transition attempt verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionAttemptVerify:
    """Verify one refused deployment attempt without granting runtime authority."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_runtime_transition_attempt":
            raise SpineRuntimeTransitionAttemptVerifyError("transition attempt kind mismatch")
        if card.get("transition_authorized") is not True or card.get("permit_consumed") is not True:
            raise SpineRuntimeTransitionAttemptVerifyError("transition attempt lacks consumed authority")
        if card.get("transition_attempted") is not True:
            raise SpineRuntimeTransitionAttemptVerifyError("transition was not attempted")
        if card.get("transition_executed") is not False:
            raise SpineRuntimeTransitionAttemptVerifyError("transition was executed")
        if card.get("runtime_driver_selected") is not True:
            raise SpineRuntimeTransitionAttemptVerifyError("runtime driver selection disappeared")
        for field in (
            "runtime_object_replaced",
            "dispatcher_started",
            "fence_moved",
            "runtime_activated",
        ):
            if card.get(field) is not False:
                raise SpineRuntimeTransitionAttemptVerifyError(f"transition attempt changed invariant: {field}")
        if card.get("dispatcher_identity_stable") is not True:
            raise SpineRuntimeTransitionAttemptVerifyError("dispatcher identity is unstable")
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionAttemptVerifyError("transition target driver changed")

        for field in (
            "attempt_id",
            "consumption_digest",
            "permit_id",
            "transition_id",
            "attempt_nonce",
            "result_digest",
        ):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionAttemptVerifyError(f"{field} is invalid")
        deployment_id = card.get("deployment_id")
        attempted_at = card.get("attempted_at")
        refusal_reason = card.get("refusal_reason")
        if not isinstance(deployment_id, str) or not deployment_id:
            raise SpineRuntimeTransitionAttemptVerifyError("deployment identity is missing")
        if not isinstance(attempted_at, str) or not attempted_at:
            raise SpineRuntimeTransitionAttemptVerifyError("attempt time is missing")
        if not isinstance(refusal_reason, str) or not refusal_reason:
            raise SpineRuntimeTransitionAttemptVerifyError("refusal reason is missing")

        expected_id = hashlib.sha256(
            f"{card['consumption_digest']}|{card['transition_id']}|{deployment_id}|{card['attempt_nonce']}|pymongo-async".encode("utf-8")
        ).hexdigest()
        if card["attempt_id"] != expected_id:
            raise SpineRuntimeTransitionAttemptVerifyError("transition attempt identity mismatch")

        normalized_result = {
            "kind": "spine_runtime_transition_attempt_result",
            "decision": "refuse-transition",
            "transition_id": card["transition_id"],
            "deployment_id": deployment_id,
            "target_driver": "pymongo-async",
            "attempt_nonce": card["attempt_nonce"],
            "reason": refusal_reason,
            "transition_executed": False,
            "runtime_activated": False,
        }
        if card["result_digest"] != _digest(normalized_result):
            raise SpineRuntimeTransitionAttemptVerifyError("transition attempt result digest mismatch")

        evidence = {
            "attempt_id": card["attempt_id"],
            "consumption_digest": card["consumption_digest"],
            "permit_id": card["permit_id"],
            "transition_id": card["transition_id"],
            "deployment_id": deployment_id,
            "target_driver": card["target_driver"],
            "attempt_nonce": card["attempt_nonce"],
            "attempted_at": attempted_at,
            "result_digest": card["result_digest"],
            "refusal_reason": refusal_reason,
            "transition_authorized": card["transition_authorized"],
            "permit_consumed": card["permit_consumed"],
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
            raise SpineRuntimeTransitionAttemptVerifyError("transition attempt digest mismatch")

        return {
            "kind": "spine_runtime_transition_attempt_verify",
            "hit": False,
            "law": "attempt-verification-does-not-promote-refused-transition",
            "citation": "VOL-134",
            "attempt_id": card["attempt_id"],
            "attempt_digest": digest,
            "transition_id": card["transition_id"],
            "verified": True,
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
