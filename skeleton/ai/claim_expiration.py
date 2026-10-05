from dataclasses import dataclass
@dataclass(frozen=True)
class ExpirationPolicy: ttl:int; volatility:str
@dataclass(frozen=True)
class ClaimValidity: claim_id:str; observed_at:int; policy:ExpirationPolicy; lineage_id:str
@dataclass(frozen=True)
class RevalidationRequest: claim_id:str; lineage_id:str; reason:str
def valid_at(v,now):
 ttl=v.policy.ttl//2 if v.policy.volatility=="high" else v.policy.ttl
 return now-v.observed_at<=ttl
def revalidation(v,now):
 return None if valid_at(v,now) else RevalidationRequest(v.claim_id,v.lineage_id,"expired")
