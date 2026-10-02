from __future__ import annotations
import pytest
from skeleton.persistence.spine_runtime_activation_boundary import (
    SpineRuntimeActivationBoundaryError,SpineRuntimeActivationBoundaryWitness,
)
from skeleton.persistence.spine_runtime_activation_boundary_verify import SpineRuntimeActivationBoundaryVerify

class _Runtime:
    dispatcher_running=False
    def start_dispatcher(self):
        raise AssertionError("boundary witness must not start dispatcher")

def _commit():
    return {"kind":"spine_runtime_activation_commit","digest":"c"*64,"commitment_id":"i"*64,
            "activation_committed":True,"runtime_driver_selected":True,"runtime_object_replaced":False,
            "dispatcher_started":False,"runtime_activated":False}
def _verify():
    return {"kind":"spine_runtime_activation_commit_verify","commitment_digest":"c"*64,"verified":True,
            "activation_committed":True,"runtime_driver_selected":True,"runtime_object_replaced":False,
            "dispatcher_started":False,"runtime_activated":False}

def test_final_pre_activation_boundary_proves_runtime_and_fence_unchanged():
    card=SpineRuntimeActivationBoundaryWitness().witness(
        commitment=_commit(),commitment_verify=_verify(),runtime=_Runtime(),epoch_before=7,epoch_after=7)
    checked=SpineRuntimeActivationBoundaryVerify().verify(card)
    assert card["activation_boundary_verified"] is True
    assert card["dispatcher_running"] is False
    assert card["fence_moved"] is False
    assert card["runtime_activated"] is False
    assert checked["verified"] is True

def test_boundary_fails_closed_on_running_dispatcher_or_moved_epoch():
    runtime=_Runtime(); runtime.dispatcher_running=True
    with pytest.raises(SpineRuntimeActivationBoundaryError,match="dispatcher is running"):
        SpineRuntimeActivationBoundaryWitness().witness(
            commitment=_commit(),commitment_verify=_verify(),runtime=runtime,epoch_before=7,epoch_after=7)
    with pytest.raises(Exception,match="moved the fence"):
        SpineRuntimeActivationBoundaryWitness().witness(
            commitment=_commit(),commitment_verify=_verify(),runtime=_Runtime(),epoch_before=7,epoch_after=8)
