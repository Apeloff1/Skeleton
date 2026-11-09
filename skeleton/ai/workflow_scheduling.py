"""Deterministic resource-aware workflow scheduling."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _h(p,x): return p+sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
def _u(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be non-negative")

@dataclass(frozen=True)
class Worker:
    worker_id:str; generation:int; failure_domain:str; capabilities:tuple[str,...]; capacity:int; reserved:int=0
    def __post_init__(self):
        _id(self.worker_id,"worker_id");_id(self.failure_domain,"failure_domain");_u(self.generation,"generation");_u(self.capacity,"capacity");_u(self.reserved,"reserved")
        if self.reserved>self.capacity: raise ValueError("worker is over-reserved")
        if len(self.capabilities)!=len(set(self.capabilities)): raise ValueError("duplicate capability")

@dataclass(frozen=True)
class Task:
    task_id:str; required_capabilities:tuple[str,...]; units:int; base_priority:int; queued_at_ns:int; anti_affinity_domains:tuple[str,...]=()
    def __post_init__(self):
        _id(self.task_id,"task_id");_u(self.units,"units");_u(self.base_priority,"base_priority");_u(self.queued_at_ns,"queued_at_ns")
        if self.units<1: raise ValueError("task units must be positive")

@dataclass(frozen=True)
class Reservation:
    reservation_id:str; epoch:int; task_id:str; worker_id:str; worker_generation:int; units:int; effective_priority:int; evidence_id:str

def effective_priority(task,now_ns,aging_interval_ns,max_age_boost=100):
    _u(now_ns,"now_ns");_u(aging_interval_ns,"aging_interval_ns");_u(max_age_boost,"max_age_boost")
    if aging_interval_ns<1 or now_ns<task.queued_at_ns: raise ValueError("invalid scheduling clock")
    return task.base_priority+min(max_age_boost,(now_ns-task.queued_at_ns)//aging_interval_ns)

def schedule(epoch,task,workers,now_ns,evidence_id,aging_interval_ns=1_000_000_000):
    _u(epoch,"epoch");_id(evidence_id,"evidence_id")
    p=effective_priority(task,now_ns,aging_interval_ns);required=set(task.required_capabilities);anti=set(task.anti_affinity_domains)
    eligible=[w for w in workers if required<=set(w.capabilities) and w.capacity-w.reserved>=task.units and w.failure_domain not in anti]
    if not eligible: raise PermissionError("no eligible worker capacity")
    eligible.sort(key=lambda w:(w.reserved*1_000_000//max(w.capacity,1),w.failure_domain,w.worker_id,w.generation))
    w=eligible[0]
    x={"epoch":epoch,"task_id":task.task_id,"worker_id":w.worker_id,"worker_generation":w.generation,"units":task.units,"effective_priority":p,"evidence_id":evidence_id}
    return Reservation(_h("reservation-sha256:",x),epoch,task.task_id,w.worker_id,w.generation,task.units,p,evidence_id)

def validate_reservation(reservation,worker,current_epoch):
    _u(current_epoch,"current_epoch")
    if reservation.epoch!=current_epoch: raise PermissionError("stale scheduling epoch")
    if reservation.worker_id!=worker.worker_id or reservation.worker_generation!=worker.generation: raise PermissionError("stale worker generation")
    if worker.capacity-worker.reserved<reservation.units: raise PermissionError("reserved capacity is no longer available")
    return True

@dataclass(frozen=True)
class PreemptionReceipt:
    receipt_id:str; epoch:int; victim_task_id:str; replacement_task_id:str; worker_id:str; released_units:int; evidence_id:str

def preempt(epoch,victim,replacement,worker_id,released_units,evidence_id):
    _u(epoch,"epoch");_u(released_units,"released_units");_id(worker_id,"worker_id");_id(evidence_id,"evidence_id")
    if released_units<1: raise ValueError("released units must be positive")
    if replacement.effective_priority<=victim.effective_priority: raise PermissionError("preemption requires strictly higher priority")
    if victim.worker_id!=worker_id or replacement.worker_id!=worker_id: raise PermissionError("preemption reservations must share worker")
    x={"epoch":epoch,"victim_task_id":victim.task_id,"replacement_task_id":replacement.task_id,"worker_id":worker_id,"released_units":released_units,"evidence_id":evidence_id}
    return PreemptionReceipt(_h("preemption-sha256:",x),epoch,victim.task_id,replacement.task_id,worker_id,released_units,evidence_id)

def reschedule_after_loss(old,task,workers,new_epoch,now_ns,evidence_id):
    if new_epoch<=old.epoch: raise PermissionError("reschedule requires newer scheduling epoch")
    survivors=tuple(w for w in workers if not (w.worker_id==old.worker_id and w.generation==old.worker_generation))
    return schedule(new_epoch,task,survivors,now_ns,evidence_id)
