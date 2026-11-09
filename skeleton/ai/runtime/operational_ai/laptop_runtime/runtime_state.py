"""No synthetic readiness transitions: state changes require independent observation."""
from __future__ import annotations
from threading import RLock
from .contracts import refuse

class RuntimeState:
    _ALLOWED={
        "uninitialized":frozenset({"install-verified","held"}),
        "install-verified":frozenset({"native-loaded","held"}),
        "native-loaded":frozenset({"serving","held"}),
        "serving":frozenset({"draining","held"}),
        "draining":frozenset({"stopped","held"}),
        "held":frozenset({"stopped"}),
        "stopped":frozenset(),
    }
    def __init__(self):
        self._lock=RLock();self._state="uninitialized";self._seq=0
        self._proofs=[]
    def transition(self,next_state,*,evidence_sha256):
        from .contracts import identity_hash
        identity_hash(evidence_sha256)
        if evidence_sha256=="0"*64:refuse("empty state-transition evidence")
        with self._lock:
            if next_state not in self._ALLOWED[self._state]:
                refuse("unapproved or skipped runtime transition")
            if evidence_sha256 in self._proofs:
                refuse("reused state transition evidence")
            self._seq+=1;self._state=next_state
            self._proofs.append(evidence_sha256)
            return {"state":self._state,"sequence":self._seq}
    def snapshot(self):
        with self._lock:
            return {"state":self._state,"sequence":self._seq}
