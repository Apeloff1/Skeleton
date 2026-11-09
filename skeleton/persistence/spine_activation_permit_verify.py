"""Independent verifier for P2 activation permits."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineActivationPermitVerifyError(RuntimeError):
    """Activation permit verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


class SpineActivationPermitVerify:
    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_activation_permit":
            raise SpineActivationPermitVerifyError("activation permit kind mismatch")
        if card.get("activation_authorized") is not True or card.get("permit_consumed") is not False:
            raise SpineActivationPermitVerifyError("activation permit authority state is invalid")
        if card.get("runtime_driver_selected") is not True:
            raise SpineActivationPermitVerifyError("runtime driver is not selected")
        if card.get("runtime_object_replaced") is not False or card.get("dispatcher_started") is not False:
            raise SpineActivationPermitVerifyError("activation permit changed runtime")
        if card.get("runtime_activated") is not False or card.get("target_driver") != "pymongo-async":
            raise SpineActivationPermitVerifyError("activation permit activated or retargeted runtime")
        for field in ("permit_id", "activation_gate_digest", "activation_nonce"):
            value=card.get(field)
            if not isinstance(value,str) or len(value)!=64:
                raise SpineActivationPermitVerifyError(f"{field} is invalid")
        expected=hashlib.sha256(f"{card['activation_gate_digest']}|{card['activation_nonce']}|pymongo-async".encode("utf-8")).hexdigest()
        if card["permit_id"] != expected:
            raise SpineActivationPermitVerifyError("activation permit identity mismatch")
        evidence={k:card.get(k) for k in (
            "permit_id","activation_gate_digest","activation_nonce","target_driver","issued_at","valid_until",
            "activation_authorized","permit_consumed","runtime_driver_selected","runtime_object_replaced",
            "dispatcher_started","runtime_activated"
        )}
        digest=_digest(evidence)
        if card.get("digest") != digest:
            raise SpineActivationPermitVerifyError("activation permit digest mismatch")
        return {
            "kind":"spine_activation_permit_verify","hit":False,
            "law":"activation-permit-verification-does-not-activate-runtime","citation":"VOL-134",
            "permit_id":card["permit_id"],"permit_digest":digest,"verified":True,
            "activation_authorized":True,"permit_consumed":False,"runtime_driver_selected":True,
            "runtime_object_replaced":False,"dispatcher_started":False,"runtime_activated":False,
            "stored_prose":0,"completion_checkbox":False,"implementation_signature":False,"verification_signature":False,
        }
