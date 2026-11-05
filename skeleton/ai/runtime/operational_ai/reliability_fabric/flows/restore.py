"""Ordered, hash-bound source/keys/journal/chat repair plan without automatic replay."""
from __future__ import annotations
from threading import RLock
from ..contracts import fail
from skeleton.ai.runtime.operational_ai.trust_gates.control.recovery_plan import RecoveryPlan

class RestoreCustody:
    def __init__(self,*,request_id,source_epoch):
        self._plan=RecoveryPlan(request_id=request_id,source_epoch=source_epoch)
        self._lock=RLock()

    @property
    def phase(self):
        return self._plan.phase

    def advance(self,phase,evidence_sha256):
        with self._lock:
            return self._plan.advance(phase,evidence_sha=evidence_sha256)

    def authorize_replay(self,*,approved,observed_model_sha,expected_model_sha):
        if approved is not True:fail("restore needs separately approved operator action")
        if observed_model_sha!=expected_model_sha:
            fail("restored model epoch different from expected source")
        if not self._plan.can_replay():
            fail("restoration has not passed all ordered custody phases")
        return {"replay_permitted":True,
                "native_inference_already_restarted":False,
                "recovery_evidence":self._plan.evidence()}
