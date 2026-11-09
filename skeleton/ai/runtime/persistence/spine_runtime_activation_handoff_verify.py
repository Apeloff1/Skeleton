"""Independent verifier for P2 runtime activation handoff evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineRuntimeActivationHandoffVerifyError(RuntimeError):
    """Activation handoff verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeActivationHandoffVerify:
    """Verify deployment handoff without performing a runtime transition."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_runtime_activation_handoff":
            raise SpineRuntimeActivationHandoffVerifyError("activation handoff kind mismatch")
        if card.get("deployment_receipt_authenticated") is not True:
            raise SpineRuntimeActivationHandoffVerifyError("deployment receipt is not authenticated")
        if card.get("handoff_ready") is not True:
            raise SpineRuntimeActivationHandoffVerifyError("activation handoff is not ready")
        if card.get("runtime_driver_selected") is not True:
            raise SpineRuntimeActivationHandoffVerifyError("runtime driver is not selected")
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeActivationHandoffVerifyError("handoff target driver changed")
        for field in ("runtime_object_replaced", "dispatcher_started", "dispatcher_running", "fence_moved", "runtime_activated"):
            if card.get(field) is not False:
                raise SpineRuntimeActivationHandoffVerifyError(f"handoff changed invariant: {field}")
        for field in ("boundary_digest", "commitment_id", "handoff_nonce"):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeActivationHandoffVerifyError(f"{field} is invalid")
        if not isinstance(card.get("deployment_id"), str) or not card.get("deployment_id"):
            raise SpineRuntimeActivationHandoffVerifyError("deployment identity is missing")
        if not isinstance(card.get("handoff_expires_at"), str) or not card.get("handoff_expires_at"):
            raise SpineRuntimeActivationHandoffVerifyError("handoff expiry is missing")

        evidence = {
            "boundary_digest": card.get("boundary_digest"),
            "commitment_id": card.get("commitment_id"),
            "deployment_id": card.get("deployment_id"),
            "handoff_nonce": card.get("handoff_nonce"),
            "target_driver": card.get("target_driver"),
            "handoff_expires_at": card.get("handoff_expires_at"),
            "deployment_receipt_authenticated": card.get("deployment_receipt_authenticated"),
            "handoff_ready": card.get("handoff_ready"),
            "runtime_driver_selected": card.get("runtime_driver_selected"),
            "runtime_object_replaced": card.get("runtime_object_replaced"),
            "dispatcher_started": card.get("dispatcher_started"),
            "dispatcher_running": card.get("dispatcher_running"),
            "fence_moved": card.get("fence_moved"),
            "runtime_activated": card.get("runtime_activated"),
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineRuntimeActivationHandoffVerifyError("activation handoff digest mismatch")

        return {
            "kind": "spine_runtime_activation_handoff_verify",
            "hit": False,
            "law": "handoff-verification-does-not-activate-runtime",
            "citation": "VOL-134",
            "handoff_digest": digest,
            "boundary_digest": card["boundary_digest"],
            "verified": True,
            "handoff_ready": True,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_started": False,
            "dispatcher_running": False,
            "fence_moved": False,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
