"""Independent verifier for P2 runtime transition permits."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineRuntimeTransitionPermitVerifyError(RuntimeError):
    """Transition permit verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionPermitVerify:
    """Verify execution authority without attempting or executing transition."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_runtime_transition_permit":
            raise SpineRuntimeTransitionPermitVerifyError("transition permit kind mismatch")
        if card.get("transition_authorized") is not True:
            raise SpineRuntimeTransitionPermitVerifyError("transition is not authorized")
        if card.get("permit_consumed") is not False:
            raise SpineRuntimeTransitionPermitVerifyError("transition permit was already consumed")
        for field in ("transition_attempted","transition_executed","runtime_object_replaced","dispatcher_started","runtime_activated"):
            if card.get(field) is not False:
                raise SpineRuntimeTransitionPermitVerifyError(f"transition permit changed invariant: {field}")
        if card.get("runtime_driver_selected") is not True:
            raise SpineRuntimeTransitionPermitVerifyError("runtime driver selection disappeared")
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionPermitVerifyError("transition target driver changed")

        for field in ("permit_id","rehearsal_digest","transition_id","execution_nonce"):
            value=card.get(field)
            if not isinstance(value,str) or len(value)!=64:
                raise SpineRuntimeTransitionPermitVerifyError(f"{field} is invalid")
        deployment_id=card.get("deployment_id")
        if not isinstance(deployment_id,str) or not deployment_id:
            raise SpineRuntimeTransitionPermitVerifyError("deployment identity is missing")
        expected=hashlib.sha256(
            f"{card['rehearsal_digest']}|{card['transition_id']}|{deployment_id}|{card['execution_nonce']}|pymongo-async".encode("utf-8")
        ).hexdigest()
        if card["permit_id"]!=expected:
            raise SpineRuntimeTransitionPermitVerifyError("transition permit identity mismatch")

        evidence={
            "permit_id":card.get("permit_id"),
            "rehearsal_digest":card.get("rehearsal_digest"),
            "transition_id":card.get("transition_id"),
            "deployment_id":deployment_id,
            "execution_nonce":card.get("execution_nonce"),
            "target_driver":card.get("target_driver"),
            "issued_at":card.get("issued_at"),
            "valid_until":card.get("valid_until"),
            "transition_authorized":card.get("transition_authorized"),
            "permit_consumed":card.get("permit_consumed"),
            "transition_attempted":card.get("transition_attempted"),
            "transition_executed":card.get("transition_executed"),
            "runtime_driver_selected":card.get("runtime_driver_selected"),
            "runtime_object_replaced":card.get("runtime_object_replaced"),
            "dispatcher_started":card.get("dispatcher_started"),
            "runtime_activated":card.get("runtime_activated"),
        }
        digest=_digest(evidence)
        if card.get("digest")!=digest:
            raise SpineRuntimeTransitionPermitVerifyError("transition permit digest mismatch")
        return {
            "kind":"spine_runtime_transition_permit_verify",
            "hit":False,
            "law":"transition-permit-verification-does-not-execute-runtime",
            "citation":"VOL-134",
            "permit_id":card["permit_id"],
            "permit_digest":digest,
            "verified":True,
            "transition_authorized":True,
            "permit_consumed":False,
            "transition_attempted":False,
            "transition_executed":False,
            "runtime_driver_selected":True,
            "runtime_activated":False,
            "stored_prose":0,
            "completion_checkbox":False,
            "implementation_signature":False,
            "verification_signature":False,
        }
