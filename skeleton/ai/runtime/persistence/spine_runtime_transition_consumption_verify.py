"""Independent verifier for P2 runtime transition-permit consumption."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineRuntimeTransitionConsumptionVerifyError(RuntimeError):
    """Transition consumption verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeTransitionConsumptionVerify:
    """Verify one-time permit consumption without attempting the transition."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_runtime_transition_consumption":
            raise SpineRuntimeTransitionConsumptionVerifyError("transition consumption kind mismatch")
        if card.get("transition_authorized") is not True:
            raise SpineRuntimeTransitionConsumptionVerifyError("transition is not authorized")
        if card.get("permit_consumed") is not True:
            raise SpineRuntimeTransitionConsumptionVerifyError("transition permit was not consumed")
        for field in ("transition_attempted","transition_executed","runtime_object_replaced","dispatcher_started","runtime_activated"):
            if card.get(field) is not False:
                raise SpineRuntimeTransitionConsumptionVerifyError(f"transition consumption changed invariant: {field}")
        if card.get("runtime_driver_selected") is not True:
            raise SpineRuntimeTransitionConsumptionVerifyError("runtime driver selection disappeared")
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeTransitionConsumptionVerifyError("transition target driver changed")

        for field in ("permit_id","permit_digest","rehearsal_digest","transition_id"):
            value=card.get(field)
            if not isinstance(value,str) or len(value)!=64:
                raise SpineRuntimeTransitionConsumptionVerifyError(f"{field} is invalid")
        deployment_id=card.get("deployment_id")
        consumed_at=card.get("consumed_at")
        if not isinstance(deployment_id,str) or not deployment_id:
            raise SpineRuntimeTransitionConsumptionVerifyError("deployment identity is missing")
        if not isinstance(consumed_at,str) or not consumed_at:
            raise SpineRuntimeTransitionConsumptionVerifyError("consumption time is missing")

        evidence={
            "permit_id":card.get("permit_id"),
            "permit_digest":card.get("permit_digest"),
            "rehearsal_digest":card.get("rehearsal_digest"),
            "transition_id":card.get("transition_id"),
            "deployment_id":deployment_id,
            "target_driver":card.get("target_driver"),
            "consumed_at":consumed_at,
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
            raise SpineRuntimeTransitionConsumptionVerifyError("transition consumption digest mismatch")
        return {
            "kind":"spine_runtime_transition_consumption_verify",
            "hit":False,
            "law":"transition-consumption-verification-does-not-attempt-runtime-transition",
            "citation":"VOL-134",
            "consumption_digest":digest,
            "permit_id":card["permit_id"],
            "transition_id":card["transition_id"],
            "verified":True,
            "transition_authorized":True,
            "permit_consumed":True,
            "transition_attempted":False,
            "transition_executed":False,
            "runtime_driver_selected":True,
            "runtime_activated":False,
            "stored_prose":0,
            "completion_checkbox":False,
            "implementation_signature":False,
            "verification_signature":False,
        }
