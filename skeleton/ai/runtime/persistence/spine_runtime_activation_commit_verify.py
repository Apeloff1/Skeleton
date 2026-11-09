"""Independent verifier for P2 activation commitments."""

from __future__ import annotations
import hashlib,json
from typing import Any


class SpineRuntimeActivationCommitVerifyError(RuntimeError):
    """Activation commitment verification failed closed."""


def _digest(payload: dict[str,Any]) -> str:
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


class SpineRuntimeActivationCommitVerify:
    def verify(self,card:dict[str,Any])->dict[str,Any]:
        if not isinstance(card,dict) or card.get("kind")!="spine_runtime_activation_commit":
            raise SpineRuntimeActivationCommitVerifyError("activation commitment kind mismatch")
        if card.get("activation_committed") is not True:
            raise SpineRuntimeActivationCommitVerifyError("activation was not committed")
        if card.get("runtime_driver_selected") is not True or card.get("target_driver")!="pymongo-async":
            raise SpineRuntimeActivationCommitVerifyError("activation commitment driver state changed")
        if card.get("runtime_object_replaced") is not False or card.get("dispatcher_started") is not False:
            raise SpineRuntimeActivationCommitVerifyError("activation commitment changed runtime")
        if card.get("runtime_activated") is not False:
            raise SpineRuntimeActivationCommitVerifyError("activation commitment activated runtime")
        for f in ("commitment_id","consumption_digest","permit_id"):
            v=card.get(f)
            if not isinstance(v,str) or len(v)!=64:
                raise SpineRuntimeActivationCommitVerifyError(f"{f} is invalid")
        expected=hashlib.sha256(f"{card['consumption_digest']}|{card['permit_id']}|pymongo-async".encode()).hexdigest()
        if card["commitment_id"]!=expected:
            raise SpineRuntimeActivationCommitVerifyError("activation commitment identity mismatch")
        evidence={k:card.get(k) for k in (
            "commitment_id","consumption_digest","permit_id","target_driver","committed_at",
            "activation_committed","runtime_driver_selected","runtime_object_replaced","dispatcher_started","runtime_activated"
        )}
        digest=_digest(evidence)
        if card.get("digest")!=digest:
            raise SpineRuntimeActivationCommitVerifyError("activation commitment digest mismatch")
        return {
            "kind":"spine_runtime_activation_commit_verify","hit":False,
            "law":"activation-commitment-verification-does-not-activate-runtime","citation":"VOL-134",
            "commitment_id":card["commitment_id"],"commitment_digest":digest,"verified":True,
            "activation_committed":True,"runtime_driver_selected":True,"runtime_object_replaced":False,
            "dispatcher_started":False,"runtime_activated":False,"stored_prose":0,"completion_checkbox":False,
            "implementation_signature":False,"verification_signature":False,
        }
