"""Policy registries and resumable knowledge refresh for VOL-243..246."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from .contracts import sha256_json

def _t(v:object,n:str)->str:
 if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} must be non-empty text")
 return v.strip()
def _d(v:object,n:str)->str:
 v=_t(v,n)
 if len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ValueError(f"{n} must be lowercase sha256")
 return v

@dataclass(frozen=True,slots=True)
class RouteConstraint:
 capability:str; privacy_boundary:str; max_cost:float; min_reliability:float
@dataclass(frozen=True,slots=True)
class RoutingPolicy:
 policy_id:str; revision:str; constraints:tuple[RouteConstraint,...]; fallback_chain:tuple[str,...]
 def __post_init__(self):
  object.__setattr__(self,"policy_id",_t(self.policy_id,"policy_id")); object.__setattr__(self,"revision",_t(self.revision,"revision"))
  if not self.constraints: raise ValueError("routing policy requires constraints")
  if len(self.fallback_chain)!=len(set(self.fallback_chain)): raise ValueError("fallback chain must be unique")
 @property
 def identity(self)->str: return sha256_json({"id":self.policy_id,"revision":self.revision,"constraints":[(c.capability,c.privacy_boundary,c.max_cost,c.min_reliability) for c in self.constraints],"fallback":list(self.fallback_chain)})
@dataclass(frozen=True,slots=True)
class ProviderCandidate:
 provider_id:str; capability:str; privacy_boundary:str; cost:float; reliability:float
@dataclass(frozen=True,slots=True)
class RouteDecision:
 provider_id:str|None; policy_identity:str; allowed:bool; reason:str

def route(policy:RoutingPolicy,candidates:tuple[ProviderCandidate,...])->RouteDecision:
 c=policy.constraints[0]
 by_id={x.provider_id:x for x in candidates}
 order=policy.fallback_chain or tuple(x.provider_id for x in candidates)
 for pid in order:
  x=by_id.get(pid)
  if x and x.capability==c.capability and x.privacy_boundary==c.privacy_boundary and x.cost<=c.max_cost and x.reliability>=c.min_reliability:
   return RouteDecision(pid,policy.identity,True,"compatible candidate")
 return RouteDecision(None,policy.identity,False,"no candidate satisfies policy")

class MemoryTrust(str,Enum): AUTHORITATIVE="authoritative"; INFERRED="inferred"; USER_EDITABLE="user_editable"
@dataclass(frozen=True,slots=True)
class MemoryRetention: ttl_seconds:int|None; tombstone_forever:bool=True
@dataclass(frozen=True,slots=True)
class MemoryPolicy:
 policy_id:str; trust:MemoryTrust; retention:MemoryRetention; promotion_requires_evidence:bool
@dataclass(frozen=True,slots=True)
class MemoryPromotion:
 memory_id:str; from_trust:MemoryTrust; to_trust:MemoryTrust; evidence_digest:str|None
 def __post_init__(self):
  if self.to_trust is MemoryTrust.AUTHORITATIVE and self.from_trust is not MemoryTrust.AUTHORITATIVE and not self.evidence_digest:
   raise ValueError("promotion to authoritative memory requires evidence")

@dataclass(frozen=True,slots=True)
class RetrievalFilter:
 tenant_id:str; classifications:tuple[str,...]; not_before:str|None; not_after:str|None
@dataclass(frozen=True,slots=True)
class RankingPolicy: max_source_age_seconds:int; allow_stale_degradation:bool
@dataclass(frozen=True,slots=True)
class RetrievalPolicy:
 policy_id:str; filter:RetrievalFilter; ranking:RankingPolicy
@dataclass(frozen=True,slots=True)
class RetrievalDocument:
 document_id:str; tenant_id:str; classification:str; observed_at:str; age_seconds:int; score:float
def retrieve(policy:RetrievalPolicy,docs:tuple[RetrievalDocument,...])->tuple[RetrievalDocument,...]:
 # Security filters occur before ranking.
 allowed=[d for d in docs if d.tenant_id==policy.filter.tenant_id and d.classification in policy.filter.classifications]
 fresh=[d for d in allowed if d.age_seconds<=policy.ranking.max_source_age_seconds]
 if fresh: return tuple(sorted(fresh,key=lambda d:(-d.score,d.document_id)))
 if not policy.ranking.allow_stale_degradation: return ()
 return tuple(sorted(allowed,key=lambda d:(d.age_seconds,-d.score,d.document_id)))

class RefreshState(str,Enum): PREPARED="prepared"; APPLYING="applying"; COMMITTED="committed"; ABORTED="aborted"
@dataclass(frozen=True,slots=True)
class RefreshCursor: epoch:str; offset:int; source_revision:str
@dataclass(frozen=True,slots=True)
class KnowledgeRefresh:
 refresh_id:str; previous_epoch:str; target_epoch:str; source_revision:str
 def __post_init__(self):
  for n in ("refresh_id","previous_epoch","target_epoch","source_revision"): object.__setattr__(self,n,_t(getattr(self,n),n))
  if self.previous_epoch==self.target_epoch: raise ValueError("refresh target epoch must be new")
@dataclass(frozen=True,slots=True)
class RefreshReceipt:
 refresh_id:str; state:RefreshState; cursor:RefreshCursor; history_epoch:str; projection_epoch:str

class RefreshCoordinator:
 def __init__(self,request:KnowledgeRefresh):
  self.request=request; self.cursor=RefreshCursor(request.target_epoch,0,request.source_revision); self.state=RefreshState.PREPARED
 def checkpoint(self,offset:int)->RefreshReceipt:
  if offset<self.cursor.offset: raise ValueError("refresh cursor cannot move backwards")
  if self.state in (RefreshState.COMMITTED,RefreshState.ABORTED): raise RuntimeError("refresh is terminal")
  self.cursor=RefreshCursor(self.request.target_epoch,offset,self.request.source_revision); self.state=RefreshState.APPLYING
  return self.receipt()
 def commit(self)->RefreshReceipt:
  if self.state is not RefreshState.APPLYING: raise RuntimeError("refresh must apply before commit")
  self.state=RefreshState.COMMITTED; return self.receipt()
 def abort(self)->RefreshReceipt:
  if self.state is RefreshState.COMMITTED: raise RuntimeError("committed refresh cannot abort")
  self.state=RefreshState.ABORTED; return self.receipt()
 def receipt(self)->RefreshReceipt:
  projection=self.request.target_epoch if self.state is RefreshState.COMMITTED else self.request.previous_epoch
  return RefreshReceipt(self.request.refresh_id,self.state,self.cursor,self.request.previous_epoch,projection)
