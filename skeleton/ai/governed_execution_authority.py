"""Generic governed execution authority envelope."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _h(p,x):return p+sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip():raise ValueError(f"{n} is required")
def _u(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0:raise ValueError(f"{n} must be non-negative")

@dataclass(frozen=True)
class ExecutionAuthority:
    authority_id:str; transaction_id:str; workflow_id:str; step_id:str; generation:int
    worker_id:str; worker_generation:int; schedule_id:str; resource_id:str; ownership_id:str
    issued_at_ns:int; expires_at_ns:int; evidence_ids:tuple[str,...]
    @classmethod
    def issue(cls,transaction_id,workflow_id,step_id,generation,worker_id,worker_generation,schedule_id,resource_id,ownership_id,issued_at_ns,expires_at_ns,evidence_ids):
        for v,n in ((transaction_id,"transaction_id"),(workflow_id,"workflow_id"),(step_id,"step_id"),(worker_id,"worker_id"),(schedule_id,"schedule_id"),(resource_id,"resource_id"),(ownership_id,"ownership_id")):_id(v,n)
        for v,n in ((generation,"generation"),(worker_generation,"worker_generation"),(issued_at_ns,"issued_at_ns"),(expires_at_ns,"expires_at_ns")):_u(v,n)
        if expires_at_ns<=issued_at_ns:raise ValueError("authority lifetime must be positive")
        evidence=tuple(sorted(evidence_ids))
        if not evidence or len(evidence)!=len(set(evidence)):raise ValueError("unique execution evidence is required")
        for e in evidence:_id(e,"evidence_id")
        x={"transaction_id":transaction_id,"workflow_id":workflow_id,"step_id":step_id,"generation":generation,"worker_id":worker_id,"worker_generation":worker_generation,"schedule_id":schedule_id,"resource_id":resource_id,"ownership_id":ownership_id,"issued_at_ns":issued_at_ns,"expires_at_ns":expires_at_ns,"evidence_ids":evidence}
        return cls(_h("execution-authority-sha256:",x),transaction_id,workflow_id,step_id,generation,worker_id,worker_generation,schedule_id,resource_id,ownership_id,issued_at_ns,expires_at_ns,evidence)

def recompute(a):
    return ExecutionAuthority.issue(a.transaction_id,a.workflow_id,a.step_id,a.generation,a.worker_id,a.worker_generation,a.schedule_id,a.resource_id,a.ownership_id,a.issued_at_ns,a.expires_at_ns,a.evidence_ids)

def validate(a,now_ns,transaction_id,workflow_id,step_id,generation,worker_id,worker_generation,schedule_id,resource_id,ownership_id):
    _u(now_ns,"now_ns")
    if recompute(a)!=a:raise PermissionError("execution authority identity mismatch")
    expected=(transaction_id,workflow_id,step_id,generation,worker_id,worker_generation,schedule_id,resource_id,ownership_id)
    actual=(a.transaction_id,a.workflow_id,a.step_id,a.generation,a.worker_id,a.worker_generation,a.schedule_id,a.resource_id,a.ownership_id)
    if actual!=expected:raise PermissionError("execution authority context mismatch")
    if now_ns<a.issued_at_ns or now_ns>=a.expires_at_ns:raise PermissionError("execution authority is not live")
    return True

@dataclass(frozen=True)
class SpecializedAuthority:
    binding_id:str; execution_authority_id:str; kind:str; subordinate_authority_id:str; evidence_id:str
    @classmethod
    def bind(cls,execution_authority,kind,subordinate_authority_id,evidence_id):
        _id(kind,"kind");_id(subordinate_authority_id,"subordinate_authority_id");_id(evidence_id,"evidence_id")
        x={"execution_authority_id":execution_authority.authority_id,"kind":kind,"subordinate_authority_id":subordinate_authority_id,"evidence_id":evidence_id}
        return cls(_h("specialized-authority-sha256:",x),execution_authority.authority_id,kind,subordinate_authority_id,evidence_id)

@dataclass(frozen=True)
class Consumption:
    consumption_id:str; authority_id:str; operation_id:str; outcome:str; evidence_id:str

class AuthorityLedger:
    def __init__(self,records=()):
        self._by_authority={}
        for r in records:self._insert(r)
    def _insert(self,r):
        if r.outcome not in {"committed","aborted"}:raise ValueError("invalid authority outcome")
        expected=_h("authority-consumption-sha256:",{"authority_id":r.authority_id,"operation_id":r.operation_id,"outcome":r.outcome,"evidence_id":r.evidence_id})
        if expected!=r.consumption_id:raise PermissionError("invalid consumption identity")
        old=self._by_authority.get(r.authority_id)
        if old is not None and old!=r:raise PermissionError("authority consumed by conflicting operation")
        self._by_authority[r.authority_id]=r
    def consume(self,authority,operation_id,outcome,evidence_id):
        _id(operation_id,"operation_id");_id(evidence_id,"evidence_id")
        if outcome not in {"committed","aborted"}:raise ValueError("invalid authority outcome")
        x={"authority_id":authority.authority_id,"operation_id":operation_id,"outcome":outcome,"evidence_id":evidence_id}
        r=Consumption(_h("authority-consumption-sha256:",x),authority.authority_id,operation_id,outcome,evidence_id)
        self._insert(r);return r
