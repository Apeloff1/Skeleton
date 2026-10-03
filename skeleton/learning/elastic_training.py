"""Epoch/fence based elastic training recovery that rejects stale workers."""
from dataclasses import dataclass
import hashlib
class ElasticRecoveryError(ValueError): pass
@dataclass(frozen=True, slots=True)
class TrainingEpoch:
    run_id:str; sequence:int; checkpoint_digest:str; dataset_cursor_digest:str
@dataclass(frozen=True, slots=True)
class WorkerFence:
    worker_id:str; epoch_sequence:int; token:str
class ElasticRecovery:
    def __init__(self,run_id:str): self.run_id=run_id; self._epoch=None; self._fences={}
    def begin_epoch(self,*,sequence:int,checkpoint_digest:str,dataset_cursor_digest:str)->TrainingEpoch:
        if sequence<0 or len(checkpoint_digest)!=64 or len(dataset_cursor_digest)!=64: raise ElasticRecoveryError("invalid epoch identity")
        if self._epoch is not None and sequence<=self._epoch.sequence: raise ElasticRecoveryError("epoch sequence must increase")
        self._epoch=TrainingEpoch(self.run_id,sequence,checkpoint_digest,dataset_cursor_digest); self._fences={}; return self._epoch
    def fence(self,worker_id:str)->WorkerFence:
        if self._epoch is None or not worker_id: raise ElasticRecoveryError("active epoch required")
        token=hashlib.sha256(f"{self.run_id}:{self._epoch.sequence}:{worker_id}".encode()).hexdigest()
        f=WorkerFence(worker_id,self._epoch.sequence,token); self._fences[worker_id]=f; return f
    def require_current(self,fence:WorkerFence)->None:
        if self._epoch is None or fence.epoch_sequence!=self._epoch.sequence or self._fences.get(fence.worker_id)!=fence: raise ElasticRecoveryError("stale worker fence")
    def resume_identity(self)->tuple[str,str]:
        if self._epoch is None: raise ElasticRecoveryError("active epoch required")
        return self._epoch.checkpoint_digest,self._epoch.dataset_cursor_digest
