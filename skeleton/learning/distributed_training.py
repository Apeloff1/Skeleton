"""Explicit distributed-training topology, timeout and replica-state contracts."""
from dataclasses import dataclass
class DistributedTrainingError(ValueError): pass
@dataclass(frozen=True, slots=True)
class TrainingTopology:
    world_size:int; data_parallel:int; model_parallel:int; collective_timeout_s:int
    def __post_init__(self):
        if min(self.world_size,self.data_parallel,self.model_parallel,self.collective_timeout_s)<1: raise DistributedTrainingError("topology values must be positive")
        if self.data_parallel*self.model_parallel!=self.world_size: raise DistributedTrainingError("parallel topology must exactly cover world_size")
@dataclass(frozen=True, slots=True)
class TrainingWorker:
    worker_id:str; rank:int; epoch:int; fence_token:str
@dataclass(frozen=True, slots=True)
class CollectiveState:
    step:int; replica_digest:str; participants:tuple[int,...]
class DistributedTrainingCoordinator:
    def __init__(self,topology:TrainingTopology): self.topology=topology; self._workers={}; self._states={}
    def join(self,worker:TrainingWorker)->None:
        if not worker.worker_id or not 0<=worker.rank<self.topology.world_size or len(worker.fence_token)<16: raise DistributedTrainingError("invalid worker identity")
        if any(w.rank==worker.rank and w.worker_id!=worker.worker_id for w in self._workers.values()): raise DistributedTrainingError("rank already owned")
        self._workers[worker.worker_id]=worker
    def record_collective(self,*,step:int,replica_digest:str,participants:tuple[int,...])->CollectiveState:
        expected=tuple(range(self.topology.world_size))
        if participants!=expected or len(replica_digest)!=64 or step<0: raise DistributedTrainingError("collective is incomplete or invalid")
        old=self._states.get(step)
        if old is not None and old.replica_digest!=replica_digest: raise DistributedTrainingError("silent replica divergence detected")
        state=CollectiveState(step,replica_digest,participants); self._states[step]=state; return state
