"""Hierarchical quota accounting for tenants, queues and worker classes."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Quota:
    max_queued:int=10000; max_leased:int=1000; max_payload_bytes:int=1048576
    def __post_init__(self):
        if min(self.max_queued,self.max_leased,self.max_payload_bytes)<1: raise ValueError("quota limits must be positive")
@dataclass(slots=True)
class Usage:
    queued:int=0; leased:int=0; payload_bytes:int=0
class QuotaExceeded(ValueError): pass
class QuotaLedger:
    def __init__(self, default:Quota|None=None): self.default=default or Quota(); self._limits={}; self._usage={}
    def configure(self, scope:str, quota:Quota): self._limits[scope]=quota
    def usage(self, scope:str)->Usage: return self._usage.setdefault(scope,Usage())
    def reserve(self, scope:str, *, queued:int=0, leased:int=0, payload_bytes:int=0)->Usage:
        u=self.usage(scope); q=self._limits.get(scope,self.default)
        nq,nl,np=u.queued+queued,u.leased+leased,u.payload_bytes+payload_bytes
        if nq<0 or nl<0 or np<0: raise QuotaExceeded("quota accounting underflow")
        if nq>q.max_queued: raise QuotaExceeded(f"queued quota exceeded: {scope}")
        if nl>q.max_leased: raise QuotaExceeded(f"leased quota exceeded: {scope}")
        if np>q.max_payload_bytes: raise QuotaExceeded(f"payload quota exceeded: {scope}")
        u.queued,u.leased,u.payload_bytes=nq,nl,np; return u
    def release(self,scope:str,**amounts:int)->Usage:
        return self.reserve(scope,queued=-amounts.get("queued",0),leased=-amounts.get("leased",0),payload_bytes=-amounts.get("payload_bytes",0))
    def snapshot(self)->dict[str,dict[str,int]]:
        return {k:{"queued":v.queued,"leased":v.leased,"payload_bytes":v.payload_bytes} for k,v in sorted(self._usage.items())}
