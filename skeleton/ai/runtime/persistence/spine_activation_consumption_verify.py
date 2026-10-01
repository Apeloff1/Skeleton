"""Independent verifier for P2 activation-permit consumption."""

from __future__ import annotations
import hashlib, json
from typing import Any


class SpineActivationConsumptionVerifyError(RuntimeError):
    """Activation consumption verification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


class SpineActivationConsumptionVerify:
    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card,dict) or card.get("kind")!="spine_activation_consumption":
            raise SpineActivationConsumptionVerifyError("activation consumption kind mismatch")
        if card.get("activation_authorized") is not True or card.get("permit_consumed") is not True:
            raise SpineActivationConsumptionVerifyError("activation authority was not consumed")
        if card.get("runtime_driver_selected") is not True:
            raise SpineActivationConsumptionVerifyError("runtime driver is not selected")
        if card.get("runtime_object_replaced") is not False or card.get("dispatcher_started") is not False:
            raise SpineActivationConsumptionVerifyError("consumption changed runtime")
        if card.get("runtime_activated") is not False or card.get("target_driver")!="pymongo-async":
            raise SpineActivationConsumptionVerifyError("consumption activated or retargeted runtime")
        for f in ("permit_id","permit_digest","activation_gate_digest"):
            v=card.get(f)
            if not isinstance(v,str) or len(v)!=64:
                raise SpineActivationConsumptionVerifyError(f"{f} is invalid")
        evidence={k:card.get(k) for k in (
            "permit_id","permit_digest","activation_gate_digest","target_driver","consumed_at",
            "activation_authorized","permit_consumed","runtime_driver_selected","runtime_object_replaced",
            "dispatcher_started","runtime_activated"
        )}
        digest=_digest(evidence)
        if card.get("digest")!=digest:
            raise SpineActivationConsumptionVerifyError("activation consumption digest mismatch")
        return {
            "kind":"spine_activation_consumption_verify","hit":False,
            "law":"activation-consumption-verification-does-not-activate-runtime","citation":"VOL-134",
            "consumption_digest":digest,"permit_id":card["permit_id"],"verified":True,
            "activation_authorized":True,"permit_consumed":True,"runtime_driver_selected":True,
            "runtime_object_replaced":False,"dispatcher_started":False,"runtime_activated":False,
            "stored_prose":0,"completion_checkbox":False,"implementation_signature":False,"verification_signature":False,
        }
