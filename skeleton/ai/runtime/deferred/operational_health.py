"""Operational health, dependency risk and provider failover controls.

Implements bounded runtime contracts for masterplan VOL-225..VOL-228.
The module is intentionally evidence-only: health observations inform routing
but cannot mint provider, deployment or administrative authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable, Sequence
from .contracts import sha256_json

def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip(): raise ValueError(f"{name} must be non-empty text")
    return value.strip()
def _digest(value: object, name: str) -> str:
    value=_text(value,name)
    if len(value)!=64 or any(c not in "0123456789abcdef" for c in value): raise ValueError(f"{name} must be lowercase sha256")
    return value
def _finite(value: object,name: str)->float:
    if isinstance(value,bool) or not isinstance(value,(int,float)): raise TypeError(f"{name} must be numeric")
    result=float(value)
    if not math.isfinite(result): raise ValueError(f"{name} must be finite")
    return result
def _unique(values: Iterable[str],name: str)->tuple[str,...]:
    result=tuple(_text(v,name) for v in values)
    if len(result)!=len(set(result)): raise ValueError(f"{name} must be unique")
    return result
class HealthState(str,Enum): HEALTHY="healthy"; DEGRADED="degraded"; BLOCKED="blocked"; UNKNOWN="unknown"
@dataclass(frozen=True,slots=True)
class HealthDimension:
    name:str; state:HealthState; score:float; observed_at:str; version:str; environment:str; evidence_digest:str
    def __post_init__(self):
        object.__setattr__(self,"name",_text(self.name,"name"))
        if not isinstance(self.state,HealthState): raise TypeError("state must be HealthState")
        score=_finite(self.score,"score")
        if score<0 or score>1: raise ValueError("score must be in [0,1]")
        object.__setattr__(self,"score",score)
        for n in ("observed_at","version","environment"): object.__setattr__(self,n,_text(getattr(self,n),n))
        object.__setattr__(self,"evidence_digest",_digest(self.evidence_digest,"evidence_digest"))
@dataclass(frozen=True,slots=True)
class HealthBlocker:
    blocker_id:str; dimension:str; reason:str; evidence_digest:str
    def __post_init__(self):
        for n in ("blocker_id","dimension","reason"): object.__setattr__(self,n,_text(getattr(self,n),n))
        object.__setattr__(self,"evidence_digest",_digest(self.evidence_digest,"evidence_digest"))
@dataclass(frozen=True,slots=True)
class HealthScorecard:
    component_id:str; dimensions:tuple[HealthDimension,...]; blockers:tuple[HealthBlocker,...]
    def __post_init__(self):
        object.__setattr__(self,"component_id",_text(self.component_id,"component_id"))
        names=[d.name for d in self.dimensions]
        if not names or len(names)!=len(set(names)): raise ValueError("dimensions must be non-empty and unique")
        ids=[b.blocker_id for b in self.blockers]
        if len(ids)!=len(set(ids)): raise ValueError("blocker ids must be unique")
        if set(b.dimension for b in self.blockers)-set(names): raise ValueError("blocker references unknown dimension")
    @property
    def aggregate_score(self): return sum(d.score for d in self.dimensions)/len(self.dimensions)
    @property
    def state(self):
        if self.blockers or any(d.state is HealthState.BLOCKED for d in self.dimensions): return HealthState.BLOCKED
        if any(d.state is HealthState.UNKNOWN for d in self.dimensions): return HealthState.UNKNOWN
        if any(d.state is HealthState.DEGRADED for d in self.dimensions): return HealthState.DEGRADED
        return HealthState.HEALTHY
    @property
    def identity(self): return sha256_json({"schema":"skeleton.health-scorecard.v1","component_id":self.component_id,"dimensions":[{"name":d.name,"state":d.state.value,"score":d.score,"observed_at":d.observed_at,"version":d.version,"environment":d.environment,"evidence_digest":d.evidence_digest} for d in self.dimensions],"blockers":[{"blocker_id":b.blocker_id,"dimension":b.dimension,"reason":b.reason,"evidence_digest":b.evidence_digest} for b in self.blockers]})
class DependencyKind(str,Enum): DIRECT="direct"; TRANSITIVE="transitive"; BUILD="build"; RUNTIME="runtime"
@dataclass(frozen=True,slots=True)
class DependencyRisk:
    package:str; version:str; kind:DependencyKind; critical:bool; maintained:bool; vulnerable:bool; sbom_digest:str; disposition:str|None=None
    def __post_init__(self):
        for n in ("package","version"): object.__setattr__(self,n,_text(getattr(self,n),n))
        if not isinstance(self.kind,DependencyKind): raise TypeError("kind must be DependencyKind")
        object.__setattr__(self,"sbom_digest",_digest(self.sbom_digest,"sbom_digest"))
        if self.disposition is not None: object.__setattr__(self,"disposition",_text(self.disposition,"disposition"))
        if self.critical and (not self.maintained or self.vulnerable) and self.disposition is None: raise ValueError("critical unhealthy dependency requires risk disposition")
@dataclass(frozen=True,slots=True)
class DependencyHealth:
    inventory_digest:str; dependencies:tuple[DependencyRisk,...]
    def __post_init__(self):
        object.__setattr__(self,"inventory_digest",_digest(self.inventory_digest,"inventory_digest"))
        keys=[(d.package,d.version,d.kind) for d in self.dependencies]
        if len(keys)!=len(set(keys)): raise ValueError("dependency inventory contains duplicate coordinates")
    @property
    def blockers(self): return tuple(d for d in self.dependencies if d.critical and (d.vulnerable or not d.maintained))
@dataclass(frozen=True,slots=True)
class ProviderDependency:
    provider_id:str; capability_class:str; data_boundary:str; critical:bool
    def __post_init__(self):
        for n in ("provider_id","capability_class","data_boundary"): object.__setattr__(self,n,_text(getattr(self,n),n))
@dataclass(frozen=True,slots=True)
class ProviderRisk:
    dependency:ProviderDependency; concentration:float; fallback_provider:str|None; no_fallback_disposition:str|None
    def __post_init__(self):
        concentration=_finite(self.concentration,"concentration")
        if concentration<0 or concentration>1: raise ValueError("concentration must be in [0,1]")
        object.__setattr__(self,"concentration",concentration)
        if self.fallback_provider is not None: object.__setattr__(self,"fallback_provider",_text(self.fallback_provider,"fallback_provider"))
        if self.no_fallback_disposition is not None: object.__setattr__(self,"no_fallback_disposition",_text(self.no_fallback_disposition,"no_fallback_disposition"))
        if self.dependency.critical and self.fallback_provider is None and self.no_fallback_disposition is None: raise ValueError("critical provider requires fallback or explicit no-fallback disposition")
        if self.fallback_provider==self.dependency.provider_id: raise ValueError("fallback provider must differ from primary")
@dataclass(frozen=True,slots=True)
class ProviderHealth:
    provider_id:str; healthy:bool; observed_at:str; evidence_digest:str
    def __post_init__(self):
        object.__setattr__(self,"provider_id",_text(self.provider_id,"provider_id"))
        if not isinstance(self.healthy,bool): raise TypeError("healthy must be boolean")
        object.__setattr__(self,"observed_at",_text(self.observed_at,"observed_at")); object.__setattr__(self,"evidence_digest",_digest(self.evidence_digest,"evidence_digest"))
@dataclass(frozen=True,slots=True)
class ProviderProfile:
    provider_id:str; capability_class:str; data_boundary:str
    def __post_init__(self):
        for n in ("provider_id","capability_class","data_boundary"): object.__setattr__(self,n,_text(getattr(self,n),n))
@dataclass(frozen=True,slots=True)
class ProviderOutcome:
    operation_id:str; provider_id:str; known_complete:bool
    def __post_init__(self):
        object.__setattr__(self,"operation_id",_text(self.operation_id,"operation_id")); object.__setattr__(self,"provider_id",_text(self.provider_id,"provider_id"))
        if not isinstance(self.known_complete,bool): raise TypeError("known_complete must be boolean")
@dataclass(frozen=True,slots=True)
class FailoverDecision: primary:str; selected:str|None; allowed:bool; reason:str
def decide_failover(primary:ProviderProfile,candidates:Sequence[ProviderProfile],health:Sequence[ProviderHealth],outcome:ProviderOutcome|None)->FailoverDecision:
    states={h.provider_id:h for h in health}; ph=states.get(primary.provider_id)
    if ph is None: return FailoverDecision(primary.provider_id,None,False,"primary health unknown")
    if ph.healthy: return FailoverDecision(primary.provider_id,primary.provider_id,False,"primary healthy")
    if outcome is not None and outcome.provider_id==primary.provider_id and not outcome.known_complete: return FailoverDecision(primary.provider_id,None,False,"unknown external outcome requires reconciliation")
    for c in candidates:
        ch=states.get(c.provider_id)
        if ch is None or not ch.healthy or c.capability_class!=primary.capability_class or c.data_boundary!=primary.data_boundary: continue
        return FailoverDecision(primary.provider_id,c.provider_id,True,"compatible healthy fallback")
    return FailoverDecision(primary.provider_id,None,False,"no compatible healthy fallback")