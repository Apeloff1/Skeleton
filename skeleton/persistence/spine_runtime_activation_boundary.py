"""Witness the final pre-activation runtime boundary without activating it."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.persistence.spine_dispatch_guard import SpineDispatchGuard
from skeleton.persistence.spine_epoch_witness import SpineEpochWitness


class SpineRuntimeActivationBoundaryError(RuntimeError):
    """Final pre-activation invariant witness failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


class SpineRuntimeActivationBoundaryWitness:
    """Bind activation commitment to an untouched runtime and unmoved fence."""

    def witness(
        self,
        *,
        commitment: dict[str, Any],
        commitment_verify: dict[str, Any],
        runtime: Any,
        epoch_before: int,
        epoch_after: int,
    ) -> dict[str, Any]:
        if (
            not isinstance(commitment,dict)
            or commitment.get("kind")!="spine_runtime_activation_commit"
            or commitment.get("activation_committed") is not True
            or commitment.get("runtime_driver_selected") is not True
            or commitment.get("runtime_activated") is not False
        ):
            raise SpineRuntimeActivationBoundaryError("verified non-activating commitment is required")
        if commitment.get("runtime_object_replaced") is not False or commitment.get("dispatcher_started") is not False:
            raise SpineRuntimeActivationBoundaryError("activation commitment already changed runtime")
        commitment_digest=commitment.get("digest")
        if not isinstance(commitment_digest,str) or len(commitment_digest)!=64:
            raise SpineRuntimeActivationBoundaryError("activation commitment digest is invalid")
        if (
            not isinstance(commitment_verify,dict)
            or commitment_verify.get("kind")!="spine_runtime_activation_commit_verify"
            or commitment_verify.get("verified") is not True
            or commitment_verify.get("commitment_digest")!=commitment_digest
            or commitment_verify.get("activation_committed") is not True
            or commitment_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeActivationBoundaryError("independent commitment verification is required")

        guard=SpineDispatchGuard()
        before=guard.snapshot(runtime)
        dispatch=guard.compare(before,runtime)
        if getattr(runtime,"dispatcher_running",False) is not False:
            raise SpineRuntimeActivationBoundaryError("runtime dispatcher is running")
        epoch=SpineEpochWitness().card(epoch_before=epoch_before,epoch_after=epoch_after,side=commitment)
        if epoch.get("moved") is not False:
            raise SpineRuntimeActivationBoundaryError("activation commitment moved fence")

        evidence={
            "commitment_digest":commitment_digest,
            "commitment_id":commitment.get("commitment_id"),
            "target_driver":"pymongo-async",
            "dispatcher_identity_stable":dispatch.get("same") is True,
            "dispatcher_called":dispatch.get("called"),
            "dispatcher_running":False,
            "epoch_before":epoch_before,
            "epoch_after":epoch_after,
            "fence_moved":False,
            "activation_boundary_verified":True,
            "runtime_driver_selected":True,
            "runtime_object_replaced":False,
            "runtime_activated":False,
        }
        if evidence["dispatcher_identity_stable"] is not True or evidence["dispatcher_called"] is not False:
            raise SpineRuntimeActivationBoundaryError("dispatcher identity proof is incomplete")
        return {
            "kind":"spine_runtime_activation_boundary_witness","hit":False,
            "law":"pre-activation-boundary-proves-runtime-and-fence-unchanged","citation":"VOL-134",
            **evidence,"digest":_digest(evidence),"stored_prose":0,"completion_checkbox":False,
            "implementation_signature":False,"verification_signature":False,
        }
