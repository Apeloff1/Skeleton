"""Compatibility-safe provider failover for VOL-228."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json

class ProviderFailoverError(ValueError): pass

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise ProviderFailoverError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ProviderFailoverError(f"{n} must be lowercase sha256")
    return v
def _digest(v:object)->str:return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class ProviderCompatibility:
    provider_id:str; capability_class:str; feature_set:tuple[str,...]; max_context_tokens:int
    def __post_init__(self):
        object.__setattr__(self,"provider_id",_token("provider_id",self.provider_id)); object.__setattr__(self,"capability_class",_token("capability_class",self.capability_class))
        features=tuple(sorted({_token("feature",f,128) for f in self.feature_set}))
        if not features: raise ProviderFailoverError("feature_set required")
        object.__setattr__(self,"feature_set",features)
        if isinstance(self.max_context_tokens,bool) or not isinstance(self.max_context_tokens,int) or self.max_context_tokens<=0: raise ProviderFailoverError("max_context_tokens must be positive")

@dataclass(frozen=True,slots=True)
class ProviderHealth:
    provider_id:str; healthy:bool; health_evidence_digest:str; risk_ppm:int
    def __post_init__(self):
        object.__setattr__(self,"provider_id",_token("provider_id",self.provider_id)); object.__setattr__(self,"health_evidence_digest",_sha("health_evidence_digest",self.health_evidence_digest))
        if not isinstance(self.healthy,bool): raise ProviderFailoverError("healthy must be boolean")
        if isinstance(self.risk_ppm,bool) or not isinstance(self.risk_ppm,int) or not 0<=self.risk_ppm<=1_000_000: raise ProviderFailoverError("risk_ppm out of range")

@dataclass(frozen=True,slots=True)
class FailoverDecision:
    requested_provider_id:str; selected_provider_id:str|None; capability_class:str; reasons:tuple[str,...]; capability_expansion:bool=False; routing_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"requested_provider_id",_token("requested_provider_id",self.requested_provider_id)); object.__setattr__(self,"capability_class",_token("capability_class",self.capability_class))
        if self.selected_provider_id is not None: object.__setattr__(self,"selected_provider_id",_token("selected_provider_id",self.selected_provider_id))
        reasons=tuple(sorted({_token("reason",r,128) for r in self.reasons})); object.__setattr__(self,"reasons",reasons)
        if self.selected_provider_id is None and not reasons: raise ProviderFailoverError("denied failover requires reasons")
        if self.capability_expansion is not False: raise ProviderFailoverError("failover cannot expand capability")
        if self.routing_authority is not False: raise ProviderFailoverError("failover evidence cannot grant routing authority")
    @property
    def digest(self)->str:return _digest({"requested_provider_id":self.requested_provider_id,"selected_provider_id":self.selected_provider_id,"capability_class":self.capability_class,"reasons":list(self.reasons),"capability_expansion":False,"routing_authority":False})

def choose_failover(*,requested:ProviderCompatibility,candidates:tuple[ProviderCompatibility,...],health:tuple[ProviderHealth,...],required_features:tuple[str,...],required_context_tokens:int)->FailoverDecision:
    health_by={h.provider_id:h for h in health}
    required=set(required_features)
    eligible=[]
    for c in candidates:
        h=health_by.get(c.provider_id)
        if c.provider_id==requested.provider_id or c.capability_class!=requested.capability_class or h is None or not h.healthy: continue
        if h.risk_ppm>=700_000: continue
        if not required.issubset(set(c.feature_set)): continue
        if c.max_context_tokens<required_context_tokens: continue
        eligible.append((h.risk_ppm,c.provider_id,c))
    if not eligible: return FailoverDecision(requested.provider_id,None,requested.capability_class,("no-compatible-healthy-provider",))
    eligible.sort(key=lambda row:(row[0],row[1]))
    return FailoverDecision(requested.provider_id,eligible[0][2].provider_id,requested.capability_class,("requested-provider-unavailable",))
