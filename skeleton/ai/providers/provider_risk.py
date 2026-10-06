"""Provider dependency and risk evidence for VOL-227."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json

class ProviderRiskError(ValueError): pass
_DIMENSIONS=("availability","security","privacy","regulatory","lock_in")

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise ProviderRiskError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ProviderRiskError(f"{n} must be lowercase sha256")
    return v
def _ppm(n:str,v:object)->int:
    if isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=1_000_000: raise ProviderRiskError(f"{n} must be within [0,1000000]")
    return v
def _digest(v:object)->str:return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class ProviderDependency:
    provider_id:str; capability_class:str; critical:bool; contract_digest:str
    def __post_init__(self):
        object.__setattr__(self,"provider_id",_token("provider_id",self.provider_id)); object.__setattr__(self,"capability_class",_token("capability_class",self.capability_class)); object.__setattr__(self,"contract_digest",_sha("contract_digest",self.contract_digest))
        if not isinstance(self.critical,bool): raise ProviderRiskError("critical must be boolean")

@dataclass(frozen=True,slots=True)
class ProviderRiskAssessment:
    provider_id:str; capability_class:str; dimension_risk_ppm:tuple[tuple[str,int],...]; max_risk_ppm:int; failover_required:bool; evidence_digest:str; routing_authority:bool=False
    def __post_init__(self):
        object.__setattr__(self,"provider_id",_token("provider_id",self.provider_id)); object.__setattr__(self,"capability_class",_token("capability_class",self.capability_class)); object.__setattr__(self,"evidence_digest",_sha("evidence_digest",self.evidence_digest))
        rows=tuple(sorted(( _token("dimension",n,64), _ppm("risk_ppm",v)) for n,v in self.dimension_risk_ppm))
        names=[n for n,_ in rows]
        if tuple(names)!=tuple(sorted(_DIMENSIONS)): raise ProviderRiskError("risk dimensions must exactly cover availability/security/privacy/regulatory/lock_in")
        object.__setattr__(self,"dimension_risk_ppm",rows)
        expected=max(v for _,v in rows)
        if self.max_risk_ppm!=expected: raise ProviderRiskError("max_risk_ppm must match dimension evidence")
        if self.failover_required!=(expected>=700_000): raise ProviderRiskError("failover_required must match risk threshold")
        if self.routing_authority is not False: raise ProviderRiskError("risk assessment cannot grant routing authority")
    @property
    def digest(self)->str:return _digest({"provider_id":self.provider_id,"capability_class":self.capability_class,"dimension_risk_ppm":list(self.dimension_risk_ppm),"max_risk_ppm":self.max_risk_ppm,"failover_required":self.failover_required,"evidence_digest":self.evidence_digest,"routing_authority":False})

def assess_provider_risk(*,dependency:ProviderDependency,dimension_risk_ppm:dict[str,int],evidence_digest:str)->ProviderRiskAssessment:
    rows=tuple((name,dimension_risk_ppm[name]) for name in _DIMENSIONS if name in dimension_risk_ppm)
    if len(rows)!=len(_DIMENSIONS): raise ProviderRiskError("all provider risk dimensions are required")
    maximum=max(v for _,v in rows)
    return ProviderRiskAssessment(dependency.provider_id,dependency.capability_class,rows,maximum,maximum>=700_000,evidence_digest)
