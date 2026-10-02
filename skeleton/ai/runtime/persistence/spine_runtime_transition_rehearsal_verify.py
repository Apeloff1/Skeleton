"""Independent verifier for P2 deployment transition rehearsal evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineRuntimeTransitionRehearsalVerifyError(RuntimeError):
    """Deployment transition rehearsal verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionRehearsalVerify:
    """Verify the dry run while proving no runtime transition occurred."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_runtime_transition_rehearsal":
            raise SpineRuntimeTransitionRehearsalVerifyError("transition rehearsal kind mismatch")
        if card.get("transition_rehearsed") is not True:
            raise SpineRuntimeTransitionRehearsalVerifyError("transition was not rehearsed")
        if card.get("transition_attempted") is not False:
            raise SpineRuntimeTransitionRehearsalVerifyError("transition was attempted during rehearsal")
        if card.get("transition_executed") is not False:
            raise SpineRuntimeTransitionRehearsalVerifyError("transition was executed during rehearsal")
        if card.get("runtime_driver_selected") is not True:
            raise SpineRuntimeTransitionRehearsalVerifyError("runtime driver selection disappeared")
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionRehearsalVerifyError("transition target driver changed")
        for field in ("runtime_object_replaced", "dispatcher_called", "dispatcher_running", "fence_moved", "runtime_activated"):
            if card.get(field) is not False:
                raise SpineRuntimeTransitionRehearsalVerifyError(f"rehearsal changed invariant: {field}")
        if card.get("dispatcher_identity_stable") is not True:
            raise SpineRuntimeTransitionRehearsalVerifyError("dispatcher identity is unstable")
        if card.get("epoch_before") != card.get("epoch_after"):
            raise SpineRuntimeTransitionRehearsalVerifyError("fence epoch changed during rehearsal")

        for field in ("transition_id", "handoff_digest", "boundary_digest", "handoff_nonce"):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeTransitionRehearsalVerifyError(f"{field} is invalid")
        deployment_id = card.get("deployment_id")
        if not isinstance(deployment_id, str) or not deployment_id:
            raise SpineRuntimeTransitionRehearsalVerifyError("deployment identity is missing")
        expected_id = hashlib.sha256(
            f"{card['handoff_digest']}|{deployment_id}|{card['handoff_nonce']}|pymongo-async".encode("utf-8")
        ).hexdigest()
        if card["transition_id"] != expected_id:
            raise SpineRuntimeTransitionRehearsalVerifyError("transition rehearsal identity mismatch")

        evidence = {
            "transition_id": card.get("transition_id"),
            "handoff_digest": card.get("handoff_digest"),
            "boundary_digest": card.get("boundary_digest"),
            "deployment_id": deployment_id,
            "handoff_nonce": card.get("handoff_nonce"),
            "target_driver": card.get("target_driver"),
            "epoch_before": card.get("epoch_before"),
            "epoch_after": card.get("epoch_after"),
            "dispatcher_identity_stable": card.get("dispatcher_identity_stable"),
            "dispatcher_called": card.get("dispatcher_called"),
            "dispatcher_running": card.get("dispatcher_running"),
            "fence_moved": card.get("fence_moved"),
            "transition_rehearsed": card.get("transition_rehearsed"),
            "transition_attempted": card.get("transition_attempted"),
            "transition_executed": card.get("transition_executed"),
            "runtime_driver_selected": card.get("runtime_driver_selected"),
            "runtime_object_replaced": card.get("runtime_object_replaced"),
            "runtime_activated": card.get("runtime_activated"),
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineRuntimeTransitionRehearsalVerifyError("transition rehearsal digest mismatch")

        return {
            "kind": "spine_runtime_transition_rehearsal_verify",
            "hit": False,
            "law": "transition-rehearsal-verification-does-not-activate-runtime",
            "citation": "VOL-134",
            "transition_id": card["transition_id"],
            "rehearsal_digest": digest,
            "verified": True,
            "transition_rehearsed": True,
            "transition_attempted": False,
            "transition_executed": False,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_running": False,
            "fence_moved": False,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
