"""Independent verifier for the final P2 pre-activation boundary witness."""

from __future__ import annotations
import hashlib,json
from typing import Any


class SpineRuntimeActivationBoundaryVerifyError(RuntimeError):
    """Activation-boundary verification failed closed."""


def _digest(payload:dict[str,Any])->str:
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


class SpineRuntimeActivationBoundaryVerify:
    def verify(self,card:dict[str,Any])->dict[str,Any]:
        if not isinstance(card,dict) or card.get("kind")!="spine_runtime_activation_boundary_witness":
            raise SpineRuntimeActivationBoundaryVerifyError("activation boundary kind mismatch")
        if card.get("activation_boundary_verified") is not True:
            raise SpineRuntimeActivationBoundaryVerifyError("activation boundary is not verified")
        if card.get("runtime_driver_selected") is not True or card.get("target_driver")!="pymongo-async":
            raise SpineRuntimeActivationBoundaryVerifyError("selected driver boundary changed")
        if card.get("dispatcher_identity_stable") is not True or card.get("dispatcher_called") is not False:
            raise SpineRuntimeActivationBoundaryVerifyError("dispatcher boundary changed")
        if card.get("dispatcher_running") is not False or card.get("runtime_object_replaced") is not False:
            raise SpineRuntimeActivationBoundaryVerifyError("runtime changed before activation")
        if card.get("fence_moved") is not False or card.get("epoch_before")!=card.get("epoch_after"):
            raise SpineRuntimeActivationBoundaryVerifyError("fence moved before activation")
        if card.get("runtime_activated") is not False:
            raise SpineRuntimeActivationBoundaryVerifyError("boundary witness activated runtime")
        for f in ("commitment_digest","commitment_id"):
            v=card.get(f)
            if not isinstance(v,str) or len(v)!=64:
                raise SpineRuntimeActivationBoundaryVerifyError(f"{f} is invalid")
        evidence={k:card.get(k) for k in (
            "commitment_digest","commitment_id","target_driver","dispatcher_identity_stable","dispatcher_called",
            "dispatcher_running","epoch_before","epoch_after","fence_moved","activation_boundary_verified",
            "runtime_driver_selected","runtime_object_replaced","runtime_activated"
        )}
        digest=_digest(evidence)
        if card.get("digest")!=digest:
            raise SpineRuntimeActivationBoundaryVerifyError("activation boundary digest mismatch")
        return {
            "kind":"spine_runtime_activation_boundary_verify","hit":False,
            "law":"boundary-verification-does-not-activate-runtime","citation":"VOL-134",
            "boundary_digest":digest,"verified":True,"activation_boundary_verified":True,
            "runtime_driver_selected":True,"dispatcher_running":False,"fence_moved":False,
            "runtime_object_replaced":False,"runtime_activated":False,"stored_prose":0,
            "completion_checkbox":False,"implementation_signature":False,"verification_signature":False,
        }
