from dataclasses import dataclass
@dataclass(frozen=True)
class ExpirationPolicy:
 ttl:int; volatility:str
 def __post_init__(self):
  if isinstance(self.ttl,bool) or not isinstance(self.ttl,int) or self.ttl<=0:raise ValueError("positive claim TTL required")
  if self.volatility not in {"low","normal","high"}:raise ValueError("unknown volatility")
@dataclass(frozen=True)
class ClaimValidity:
 claim_id:str; observed_at:int; policy:ExpirationPolicy; lineage_id:str
 def __post_init__(self):
  if not self.claim_id or not self.lineage_id or isinstance(self.observed_at,bool) or not isinstance(self.observed_at,int) or self.observed_at<0:raise ValueError("valid claim observation identity required")
@dataclass(frozen=True)
class RevalidationRequest: claim_id:str; lineage_id:str; reason:str
def valid_at(v,now):
 if isinstance(now,bool) or not isinstance(now,int) or now<0:raise ValueError("valid evaluation time required")
 if now<v.observed_at:return False
 ttl=max(1,v.policy.ttl//2) if v.policy.volatility=="high" else v.policy.ttl
 return now-v.observed_at<=ttl
def revalidation(v,now):
 reason="observation-in-future" if now<v.observed_at else "expired"
 return None if valid_at(v,now) else RevalidationRequest(v.claim_id,v.lineage_id,reason)
