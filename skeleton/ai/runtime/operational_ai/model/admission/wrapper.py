"""Assert model admission at every new inference, not just at first boot."""
from __future__ import annotations
from .broker import ModelCapacityLease
from .contracts import AdmissionError


class AdmittedBackend:
    def __init__(self, backend, lease: ModelCapacityLease):
        if not isinstance(lease, ModelCapacityLease) or not lease.active:
            raise AdmissionError('a live kernel-fenced capacity reservation is mandatory')
        if not isinstance(getattr(backend,'model_digest',None),str):
            raise AdmissionError('a real model identity is required')
        if backend.model_digest != lease._entry['reservation']['model_sha256']:
            raise AdmissionError('model and resource reservation identity differ')
        self.backend=backend
        self.lease=lease
        self.lease.assert_live()

    @property
    def model_digest(self):
        return self.backend.model_digest

    @property
    def tokenizer_digest(self):
        return self.backend.tokenizer_digest

    def generate(self,*args,**kwargs):
        self.lease.assert_live()
        return self.backend.generate(*args,**kwargs)

    def admit_before_reservation(self)->dict:
        proof=self.lease.assert_live()
        gate=getattr(self.backend,'admit_before_reservation',None)
        if callable(gate):
            gate()
        else:
            from ..isolation.resource_gate import require_headroom
            require_headroom(128*1024*1024)
        return {'status':'native-model-capacity-gated','occupancy':proof}

    def __getattr__(self,name):
        if name.startswith('_'):
            raise AttributeError(name)
        return getattr(self.backend,name)
