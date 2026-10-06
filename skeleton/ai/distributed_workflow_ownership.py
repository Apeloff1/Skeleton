"""Fenced distributed workflow ownership and orphan adoption."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _h(p,x): return p+sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
def _u(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be non-negative")

@dataclass(frozen=True)
class CoordinatorEpoch:
    epoch_id:str; workflow_id:str; coordinator_id:str; epoch:int; issued_at_ns:int
    @classmethod
    def create(cls,workflow_id,coordinator_id,epoch,issued_at_ns):
        _id(workflow_id,"workflow_id");_id(coordinator_id,"coordinator_id");_u(epoch,"epoch");_u(issued_at_ns,"issued_at_ns")
        x={"workflow_id":workflow_id,"coordinator_id":coordinator_id,"epoch":epoch,"issued_at_ns":issued_at_ns}
        return cls(_h("coordinator-epoch-sha256:",x),workflow_id,coordinator_id,epoch,issued_at_ns)

@dataclass(frozen=True)
class StepLease:
    lease_id:str; workflow_id:str; step_id:str; coordinator_epoch:int; worker_id:str; worker_generation:int; issued_at_ns:int; expires_at_ns:int
    @classmethod
    def issue(cls,epoch,step_id,worker_id,worker_generation,issued_at_ns,expires_at_ns):
        _id(step_id,"step_id");_id(worker_id,"worker_id");_u(worker_generation,"worker_generation");_u(issued_at_ns,"issued_at_ns");_u(expires_at_ns,"expires_at_ns")
        if expires_at_ns<=issued_at_ns: raise ValueError("step lease must have positive lifetime")
        x={"workflow_id":epoch.workflow_id,"step_id":step_id,"coordinator_epoch":epoch.epoch,"worker_id":worker_id,"worker_generation":worker_generation,"issued_at_ns":issued_at_ns,"expires_at_ns":expires_at_ns}
        return cls(_h("step-lease-sha256:",x),epoch.workflow_id,step_id,epoch.epoch,worker_id,worker_generation,issued_at_ns,expires_at_ns)

@dataclass(frozen=True)
class Heartbeat:
    heartbeat_id:str; lease_id:str; worker_id:str; worker_generation:int; observed_at_ns:int
    @classmethod
    def create(cls,lease,observed_at_ns):
        _u(observed_at_ns,"observed_at_ns")
        if observed_at_ns<lease.issued_at_ns or observed_at_ns>=lease.expires_at_ns: raise PermissionError("heartbeat outside live lease")
        x={"lease_id":lease.lease_id,"worker_id":lease.worker_id,"worker_generation":lease.worker_generation,"observed_at_ns":observed_at_ns}
        return cls(_h("heartbeat-sha256:",x),lease.lease_id,lease.worker_id,lease.worker_generation,observed_at_ns)

@dataclass(frozen=True)
class TakeoverReceipt:
    receipt_id:str; workflow_id:str; step_id:str; old_lease_id:str; new_lease_id:str; new_epoch:int; evidence_id:str

def validate_execution(epoch,lease,worker_id,worker_generation,now_ns):
    _id(worker_id,"worker_id");_u(worker_generation,"worker_generation");_u(now_ns,"now_ns")
    if lease.workflow_id!=epoch.workflow_id or lease.coordinator_epoch!=epoch.epoch: raise PermissionError("stale coordinator ownership")
    if lease.worker_id!=worker_id or lease.worker_generation!=worker_generation: raise PermissionError("stale worker ownership")
    if now_ns<lease.issued_at_ns or now_ns>=lease.expires_at_ns: raise PermissionError("step lease is not live")
    return True

def adopt_orphan(old_epoch,old_lease,last_heartbeat,new_epoch,new_worker_id,new_worker_generation,now_ns,evidence_id,lease_duration_ns):
    _id(evidence_id,"evidence_id");_u(now_ns,"now_ns");_u(lease_duration_ns,"lease_duration_ns")
    if lease_duration_ns<1: raise ValueError("lease duration must be positive")
    if old_lease.workflow_id!=old_epoch.workflow_id or old_lease.coordinator_epoch!=old_epoch.epoch: raise PermissionError("old lease does not match old epoch")
    if new_epoch.workflow_id!=old_epoch.workflow_id or new_epoch.epoch<=old_epoch.epoch: raise PermissionError("takeover requires newer coordinator epoch")
    if last_heartbeat is not None:
        if last_heartbeat.lease_id!=old_lease.lease_id or last_heartbeat.worker_id!=old_lease.worker_id or last_heartbeat.worker_generation!=old_lease.worker_generation: raise PermissionError("foreign heartbeat evidence")
        if last_heartbeat.observed_at_ns>=old_lease.expires_at_ns: raise PermissionError("invalid heartbeat chronology")
    if now_ns<old_lease.expires_at_ns: raise PermissionError("live owner cannot be adopted")
    new=StepLease.issue(new_epoch,old_lease.step_id,new_worker_id,new_worker_generation,now_ns,now_ns+lease_duration_ns)
    x={"workflow_id":old_lease.workflow_id,"step_id":old_lease.step_id,"old_lease_id":old_lease.lease_id,"new_lease_id":new.lease_id,"new_epoch":new_epoch.epoch,"evidence_id":evidence_id}
    return new,TakeoverReceipt(_h("takeover-sha256:",x),old_lease.workflow_id,old_lease.step_id,old_lease.lease_id,new.lease_id,new_epoch.epoch,evidence_id)

def reconcile_leases(leases):
    leases=tuple(leases);seen={}
    for lease in leases:
        key=(lease.workflow_id,lease.step_id,lease.coordinator_epoch)
        old=seen.get(key)
        if old and old.lease_id!=lease.lease_id: raise PermissionError("split-brain step ownership")
        seen[key]=lease
    return tuple(sorted(seen.values(),key=lambda x:(x.workflow_id,x.step_id,x.coordinator_epoch)))
