"""Dependency-neutral identity verification for cross-plane admission artifacts."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _h(p,x):return p+sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip():raise ValueError(f"{n} is required")
def _u(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0:raise ValueError(f"{n} must be non-negative")

@dataclass(frozen=True)
class AdmissionContext:
    transaction_id:str; workflow_id:str; step_id:str; generation:int; deadline_ns:int; worker_id:str; worker_generation:int
    def __post_init__(self):
        for n in ("transaction_id","workflow_id","step_id","worker_id"):_id(getattr(self,n),n)
        for n in ("generation","deadline_ns","worker_generation"):_u(getattr(self,n),n)

def scheduling_identity(epoch,task_id,worker_id,worker_generation,units,effective_priority,evidence_id):
    for v,n in ((task_id,"task_id"),(worker_id,"worker_id"),(evidence_id,"evidence_id")):_id(v,n)
    for v,n in ((epoch,"epoch"),(worker_generation,"worker_generation"),(units,"units"),(effective_priority,"effective_priority")):_u(v,n)
    return _h("reservation-sha256:",{"epoch":epoch,"task_id":task_id,"worker_id":worker_id,"worker_generation":worker_generation,"units":units,"effective_priority":effective_priority,"evidence_id":evidence_id})

def resource_identity(scope_path,generation,resources,deadline_ns,evidence_id):
    path=tuple(scope_path);_u(generation,"generation");_u(deadline_ns,"deadline_ns");_id(evidence_id,"evidence_id")
    for x in path:_id(x,"scope_id")
    vals={n:getattr(resources,n) for n in ("cpu","gpu","ram_bytes","tokens")}
    for n,v in vals.items():_u(v,n)
    return _h("resource-reservation-sha256:",{"scope_path":path,"generation":generation,"resources":vals,"deadline_ns":deadline_ns,"evidence_id":evidence_id})

def ownership_identity(workflow_id,step_id,coordinator_epoch,worker_id,worker_generation,issued_at_ns,expires_at_ns):
    for v,n in ((workflow_id,"workflow_id"),(step_id,"step_id"),(worker_id,"worker_id")):_id(v,n)
    for v,n in ((coordinator_epoch,"coordinator_epoch"),(worker_generation,"worker_generation"),(issued_at_ns,"issued_at_ns"),(expires_at_ns,"expires_at_ns")):_u(v,n)
    return _h("step-lease-sha256:",{"workflow_id":workflow_id,"step_id":step_id,"coordinator_epoch":coordinator_epoch,"worker_id":worker_id,"worker_generation":worker_generation,"issued_at_ns":issued_at_ns,"expires_at_ns":expires_at_ns})

@dataclass(frozen=True)
class BoundArtifact:
    participant:str; artifact_id:str; evidence_id:str

def bind_schedule(ctx,r):
    expected=scheduling_identity(r.epoch,r.task_id,r.worker_id,r.worker_generation,r.units,r.effective_priority,r.evidence_id)
    if expected!=r.reservation_id:raise PermissionError("invalid scheduling reservation identity")
    if r.task_id!=ctx.step_id or r.worker_id!=ctx.worker_id or r.worker_generation!=ctx.worker_generation:raise PermissionError("scheduling reservation does not match admission context")
    return BoundArtifact("schedule",r.reservation_id,r.evidence_id)

def bind_resources(ctx,r):
    expected=resource_identity(r.scope_path,r.generation,r.resources,r.deadline_ns,r.evidence_id)
    if expected!=r.reservation_id:raise PermissionError("invalid resource reservation identity")
    if r.generation!=ctx.generation or r.deadline_ns!=ctx.deadline_ns:raise PermissionError("resource reservation does not match admission context")
    return BoundArtifact("resources",r.reservation_id,r.evidence_id)

def bind_ownership(ctx,r):
    expected=ownership_identity(r.workflow_id,r.step_id,r.coordinator_epoch,r.worker_id,r.worker_generation,r.issued_at_ns,r.expires_at_ns)
    if expected!=r.lease_id:raise PermissionError("invalid ownership lease identity")
    if r.workflow_id!=ctx.workflow_id or r.step_id!=ctx.step_id or r.worker_id!=ctx.worker_id or r.worker_generation!=ctx.worker_generation:raise PermissionError("ownership lease does not match admission context")
    if r.expires_at_ns>ctx.deadline_ns:raise PermissionError("ownership lease exceeds admission deadline")
    return BoundArtifact("ownership",r.lease_id,r.lease_id)

def prepare_identity(ctx,bound):
    if bound.participant not in {"schedule","resources","ownership","authorization"}:raise ValueError("unknown participant")
    x={"transaction_id":ctx.transaction_id,"participant":bound.participant,"generation":ctx.generation,"artifact_id":bound.artifact_id,"evidence_id":bound.evidence_id}
    return _h("admission-prepare-sha256:",x)
