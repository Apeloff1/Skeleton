"""Evidence-bound component and dependency health for VOL-225/226."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json

class HealthScorecardError(ValueError): pass

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise HealthScorecardError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise HealthScorecardError(f"{n} must be lowercase sha256")
    return v
def _ppm(n:str,v:object)->int:
    if isinstance(v,bool) or not isinstance(v,int) or not 0<=v<=1_000_000: raise HealthScorecardError(f"{n} must be within [0,1000000]")
    return v
def _digest(v:object)->str: return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class HealthDimension:
    dimension_id:str; score_ppm:int; evidence_digest:str; weight_ppm:int
    def __post_init__(self):
        object.__setattr__(self,"dimension_id",_token("dimension_id",self.dimension_id)); object.__setattr__(self,"score_ppm",_ppm("score_ppm",self.score_ppm)); object.__setattr__(self,"weight_ppm",_ppm("weight_ppm",self.weight_ppm)); object.__setattr__(self,"evidence_digest",_sha("evidence_digest",self.evidence_digest))
        if self.weight_ppm==0: raise HealthScorecardError("weight_ppm must be positive")

@dataclass(frozen=True,slots=True)
class ComponentHealthScorecard:
    component_id:str; dimensions:tuple[HealthDimension,...]; score_ppm:int; status:str; evidence_only:bool=True
    def __post_init__(self):
        object.__setattr__(self,"component_id",_token("component_id",self.component_id))
        if not self.dimensions: raise HealthScorecardError("dimensions required")
        ids=[d.dimension_id for d in self.dimensions]
        if len(ids)!=len(set(ids)): raise HealthScorecardError("dimension ids must be unique")
        total=sum(d.weight_ppm for d in self.dimensions); expected=round(sum(d.score_ppm*d.weight_ppm for d in self.dimensions)/total)
        if self.score_ppm!=expected: raise HealthScorecardError("score_ppm must match weighted evidence")
        expected_status="healthy" if expected>=900_000 else ("degraded" if expected>=700_000 else "unhealthy")
        if self.status!=expected_status: raise HealthScorecardError("status must match score")
        if self.evidence_only is not True: raise HealthScorecardError("scorecard is evidence-only")
        object.__setattr__(self,"dimensions",tuple(sorted(self.dimensions,key=lambda d:d.dimension_id)))
    @classmethod
    def build(cls,component_id:str,dimensions:tuple[HealthDimension,...])->"ComponentHealthScorecard":
        total=sum(d.weight_ppm for d in dimensions)
        if total<=0: raise HealthScorecardError("positive dimension weight required")
        score=round(sum(d.score_ppm*d.weight_ppm for d in dimensions)/total)
        status="healthy" if score>=900_000 else ("degraded" if score>=700_000 else "unhealthy")
        return cls(component_id,dimensions,score,status)
    @property
    def digest(self)->str: return _digest({"component_id":self.component_id,"dimensions":[{"id":d.dimension_id,"score_ppm":d.score_ppm,"weight_ppm":d.weight_ppm,"evidence":d.evidence_digest} for d in self.dimensions],"score_ppm":self.score_ppm,"status":self.status,"evidence_only":True})

@dataclass(frozen=True,slots=True)
class DependencyFinding:
    dependency_id:str; severity:str; finding_id:str; evidence_digest:str; backlog_key:str
    def __post_init__(self):
        for n in ("dependency_id","finding_id","backlog_key"): object.__setattr__(self,n,_token(n,getattr(self,n)))
        sev=_token("severity",self.severity,32)
        if sev not in {"low","medium","high","critical"}: raise HealthScorecardError("unknown dependency severity")
        object.__setattr__(self,"severity",sev); object.__setattr__(self,"evidence_digest",_sha("evidence_digest",self.evidence_digest))

@dataclass(frozen=True,slots=True)
class DependencyHealthReport:
    sbom_digest:str; findings:tuple[DependencyFinding,...]; healthy:bool; unresolved_critical:int
    def __post_init__(self):
        object.__setattr__(self,"sbom_digest",_sha("sbom_digest",self.sbom_digest))
        keys=[(f.dependency_id,f.finding_id) for f in self.findings]
        if len(keys)!=len(set(keys)): raise HealthScorecardError("dependency findings must be unique")
        critical=sum(1 for f in self.findings if f.severity=="critical")
        if self.unresolved_critical!=critical: raise HealthScorecardError("unresolved_critical must match findings")
        expected=not any(f.severity in {"high","critical"} for f in self.findings)
        if self.healthy!=expected: raise HealthScorecardError("healthy must match finding severity")
        object.__setattr__(self,"findings",tuple(sorted(self.findings,key=lambda f:(f.dependency_id,f.finding_id))))
    @property
    def digest(self)->str: return _digest({"sbom_digest":self.sbom_digest,"findings":[{"dependency":f.dependency_id,"severity":f.severity,"finding":f.finding_id,"evidence":f.evidence_digest,"backlog":f.backlog_key} for f in self.findings],"healthy":self.healthy,"unresolved_critical":self.unresolved_critical})
