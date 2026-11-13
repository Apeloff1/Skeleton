"""Ordered fail-closed recovery state machine: inspect before replay."""
from __future__ import annotations
from threading import RLock
from ..contracts import fail

class RecoveryPlan:
    PHASES=("created","inventory-verified","keys-verified","journal-verified",
            "chat-verified","restart-approved","restored")
    def __init__(self,*,request_id,source_epoch):
        if type(request_id) is not str or not request_id or len(request_id)>96:
            fail("invalid recovery identity")
        if type(source_epoch) is not int or source_epoch<1:
            fail("missing recovery source epoch")
        self.request_id=request_id;self.source_epoch=source_epoch
        self._lock=RLock();self._index=0;self._evidence={}

    @property
    def phase(self):
        with self._lock: return self.PHASES[self._index]

    def advance(self,phase,*,evidence_sha):
        import re
        if type(evidence_sha) is not str or re.fullmatch("[0-9a-f]{64}",evidence_sha) is None:
            fail("recovery requires digest-bound evidence")
        with self._lock:
            if self._index==len(self.PHASES)-1: fail("recovery already terminal")
            expected=self.PHASES[self._index+1]
            if phase!=expected: fail("recovery phase skipped or reordered")
            if evidence_sha=="0"*64: fail("empty evidence")
            if evidence_sha in self._evidence.values(): fail("reused recovery evidence")
            self._evidence[phase]=evidence_sha
            self._index+=1
            return {"phase":phase,"phase_index":self._index}

    def can_replay(self):
        with self._lock:
            return self._index==len(self.PHASES)-1

    def evidence(self):
        with self._lock:
            return dict(self._evidence)
