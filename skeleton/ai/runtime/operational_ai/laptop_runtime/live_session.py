"""Explicit laptop session coordinator for repeated real native requests."""
from __future__ import annotations
import secrets
from .contracts import identifier,utf8,refuse
from .session_adapter import create
from .turn_bridge import TurnBridge

class LiveSession:
    def __init__(self,worker,session_id=None):
        self.worker=worker
        self.bridge=TurnBridge(worker)
        self.session_id=create(worker) if session_id is None else identifier(session_id)
        self._closed=False

    def turn(self,message,*,request_id=None,seed=0,temperature=0.8):
        if self._closed:refuse("closed laptop session")
        request_id=request_id or "r_"+secrets.token_hex(16)
        receipt=self.bridge.turn(self.session_id,identifier(request_id),
                                 utf8(message,maximum=self.worker.spine.limits.input_bytes),
                                 seed=seed,temperature=temperature)
        return {"session_id":self.session_id,"request_id":request_id,
                "receipt":receipt}

    def history(self):
        if self._closed:refuse("closed laptop session")
        return self.worker.spine.history(self.session_id)

    def close(self):
        if self._closed:return False
        self.worker.spine.close(self.session_id)
        self._closed=True
        return True
