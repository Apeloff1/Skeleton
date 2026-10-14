"""Hierarchical multidimensional resource accounting."""
from dataclasses import dataclass
from hashlib import sha256
import json

def _h(p,x): return p+sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _id(v,n):
    if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} is required")
def _u(v,n):
    if isinstance(v,bool) or not isinstance(v,int) or v<0: raise ValueError(f"{n} must be non-negative")

@dataclass(frozen=True)
class Resources:
    cpu:int=0; gpu:int=0; ram_bytes:int=0; tokens:int=0
    def __post_init__(self):
        for n in ("cpu","gpu","ram_bytes","tokens"):_u(getattr(self,n),n)
    def add(self,o):return Resources(*(getattr(self,n)+getattr(o,n) for n in ("cpu","gpu","ram_bytes","tokens")))
    def sub(self,o):
        vals=[getattr(self,n)-getattr(o,n) for n in ("cpu","gpu","ram_bytes","tokens")]
        if any(v<0 for v in vals):raise PermissionError("resource accounting underflow")
        return Resources(*vals)
    def fits(self,limit):return all(getattr(self,n)<=getattr(limit,n) for n in ("cpu","gpu","ram_bytes","tokens"))

@dataclass(frozen=True)
class Quota:
    scope_id:str; parent_id:str|None; hard:Resources; burst:Resources
    def __post_init__(self):
        _id(self.scope_id,"scope_id")
        if self.parent_id is not None:_id(self.parent_id,"parent_id")

@dataclass(frozen=True)
class Reservation:
    reservation_id:str; scope_path:tuple[str,...]; generation:int; resources:Resources; deadline_ns:int; evidence_id:str
    @classmethod
    def create(cls,scope_path,generation,resources,deadline_ns,evidence_id):
        path=tuple(scope_path)
        if not path or len(path)!=len(set(path)):raise ValueError("invalid quota scope path")
        for x in path:_id(x,"scope_id")
        _u(generation,"generation");_u(deadline_ns,"deadline_ns");_id(evidence_id,"evidence_id")
        x={"scope_path":path,"generation":generation,"resources":resources.__dict__,"deadline_ns":deadline_ns,"evidence_id":evidence_id}
        return cls(_h("resource-reservation-sha256:",x),path,generation,resources,deadline_ns,evidence_id)

@dataclass(frozen=True)
class ReleaseReceipt:
    receipt_id:str; reservation_id:str; generation:int; evidence_id:str

class ResourceLedger:
    def __init__(self,quotas):
        self.quotas={q.scope_id:q for q in quotas};self.used={k:Resources() for k in self.quotas};self.active={};self.released={}
        for q in quotas:
            if q.parent_id is not None and q.parent_id not in self.quotas:raise ValueError("unknown quota parent")

    def admit(self,reservation,now_ns,burst_credits=None):
        _u(now_ns,"now_ns")
        if now_ns>=reservation.deadline_ns:raise PermissionError("reservation deadline expired")
        if reservation.reservation_id in self.active:return self.active[reservation.reservation_id]
        credits=burst_credits or {}
        for scope in reservation.scope_path:
            q=self.quotas.get(scope)
            if q is None:raise PermissionError("unknown quota scope")
            next_used=self.used[scope].add(reservation.resources)
            credit=credits.get(scope,Resources())
            allowed=q.hard.add(Resources(*(min(getattr(q.burst,n),getattr(credit,n)) for n in ("cpu","gpu","ram_bytes","tokens"))))
            if not next_used.fits(allowed):raise PermissionError("hierarchical quota exceeded")
        for scope in reservation.scope_path:self.used[scope]=self.used[scope].add(reservation.resources)
        self.active[reservation.reservation_id]=reservation;return reservation

    def release(self,reservation_id,generation,evidence_id):
        _id(reservation_id,"reservation_id");_u(generation,"generation");_id(evidence_id,"evidence_id")
        old=self.released.get(reservation_id)
        if old:
            if old.generation!=generation or old.evidence_id!=evidence_id:raise PermissionError("release replay changed")
            return old
        r=self.active.get(reservation_id)
        if r is None or r.generation!=generation:raise PermissionError("stale or unknown reservation generation")
        for scope in r.scope_path:self.used[scope]=self.used[scope].sub(r.resources)
        x={"reservation_id":reservation_id,"generation":generation,"evidence_id":evidence_id}
        receipt=ReleaseReceipt(_h("resource-release-sha256:",x),reservation_id,generation,evidence_id)
        del self.active[reservation_id];self.released[reservation_id]=receipt;return receipt

    def leaked(self,live_reservation_ids):
        live=set(live_reservation_ids)
        return tuple(sorted((r for k,r in self.active.items() if k not in live),key=lambda r:r.reservation_id))
