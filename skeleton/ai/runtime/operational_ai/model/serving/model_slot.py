"""Single owner for backend lifetime, epoch and physical model drainage."""
from __future__ import annotations
from threading import RLock
from .contracts import ModelIdentity,ServingError
from .identity import EpochFence
from .admission import Slots

class ModelSlot:
    def __init__(self,backend,identity:ModelIdentity,parallel:int=1):
        if backend.model_digest!=identity.model_sha256 or backend.tokenizer_digest!=identity.tokenizer_sha256:
            raise ServingError('backend does not match model identity')
        self.backend=backend;self.fence=EpochFence(identity);self.slots=Slots(parallel)
        self._lock=RLock();self.closed=False

    def close(self,deadline_ns:int)->None:
        with self._lock:
            if self.closed:return
            self.slots.drain();self.slots.wait_empty(deadline_ns)
            try:
                self.backend.close()
            finally:self.closed=True
