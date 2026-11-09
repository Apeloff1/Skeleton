"""Independent verifier for P2 runtime activation eligibility."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineRuntimeActivationGateVerifyError(RuntimeError):
    """Activation-gate verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeActivationGateVerify:
    """Verify activation eligibility while activation remains false."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_runtime_activation_gate":
            raise SpineRuntimeActivationGateVerifyError("activation gate kind mismatch")
        if card.get("activation_eligible") is not True:
            raise SpineRuntimeActivationGateVerifyError("activation is not eligible")
        if card.get("runtime_driver_selected") is not True:
            raise SpineRuntimeActivationGateVerifyError("runtime driver is not selected")
        if card.get("target_driver") != "pymongo-async":
            raise SpineRuntimeActivationGateVerifyError("activation target driver changed")
        if card.get("deployment_driver_connected") is not True:
            raise SpineRuntimeActivationGateVerifyError("deployment driver is not connected")
        if card.get("bootstrap_replay_equivalent") is not True:
            raise SpineRuntimeActivationGateVerifyError("bootstrap replay proof is missing")
        if card.get("dispatcher_identity_stable") is not True:
            raise SpineRuntimeActivationGateVerifyError("dispatcher identity is unstable")
        if card.get("dispatcher_called") is not False:
            raise SpineRuntimeActivationGateVerifyError("activation gate called dispatcher")
        if card.get("runtime_object_replaced") is not False:
            raise SpineRuntimeActivationGateVerifyError("activation gate replaced runtime object")
        if card.get("dispatcher_started") is not False:
            raise SpineRuntimeActivationGateVerifyError("activation gate started dispatcher")
        if card.get("runtime_activated") is not False:
            raise SpineRuntimeActivationGateVerifyError("activation gate activated runtime")

        for field in ("selection_digest", "qualification_digest"):
            value = card.get(field)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeActivationGateVerifyError(f"{field} is invalid")

        evidence = {
            "selection_digest": card.get("selection_digest"),
            "qualification_digest": card.get("qualification_digest"),
            "target_driver": card.get("target_driver"),
            "driver_distribution": card.get("driver_distribution"),
            "driver_class": card.get("driver_class"),
            "deployment_driver_connected": card.get("deployment_driver_connected"),
            "bootstrap_replay_equivalent": card.get("bootstrap_replay_equivalent"),
            "dispatcher_identity_stable": card.get("dispatcher_identity_stable"),
            "dispatcher_called": card.get("dispatcher_called"),
            "activation_eligible": card.get("activation_eligible"),
            "runtime_driver_selected": card.get("runtime_driver_selected"),
            "runtime_object_replaced": card.get("runtime_object_replaced"),
            "dispatcher_started": card.get("dispatcher_started"),
            "runtime_activated": card.get("runtime_activated"),
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpineRuntimeActivationGateVerifyError("activation gate digest mismatch")

        return {
            "kind": "spine_runtime_activation_gate_verify",
            "hit": False,
            "law": "activation-gate-verification-does-not-activate-runtime",
            "citation": "VOL-134",
            "activation_gate_digest": digest,
            "verified": True,
            "activation_eligible": True,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_started": False,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
