"""Tool dependency, health, discovery and result trust VOL-374..377."""
from dataclasses import dataclass
from enum import Enum
@dataclass(frozen=True,slots=True)
class ToolDependency: source:str; source_version:str; target:str; target_version:str; kind:str
@dataclass(frozen=True,slots=True)
class ToolGraph: dependencies:tuple[ToolDependency,...]; available:frozenset[tuple[str,str]]
@dataclass(frozen=True,slots=True)
class ToolCompatibility: compatible:bool; unavailable:tuple[str,...]
def tool_compatibility(g):
 missing=tuple(sorted({f"{d.target}@{d.target_version}" for d in g.dependencies if (d.target,d.target_version) not in g.available}))
 return ToolCompatibility(not missing,missing)
class ToolHealthState(str,Enum): HEALTHY="healthy"; DEGRADED="degraded"; STALE="stale"
@dataclass(frozen=True,slots=True)
class ToolProbe: transport_ok:bool; semantic_ok:bool; auth_ok:bool; quota_ok:bool; observed_at:int
@dataclass(frozen=True,slots=True)
class ToolHealth: state:ToolHealthState; probe:ToolProbe
def tool_health(p,now,max_age):
 if now-p.observed_at>max_age:return ToolHealth(ToolHealthState.STALE,p)
 return ToolHealth(ToolHealthState.HEALTHY if all((p.transport_ok,p.semantic_ok,p.auth_ok,p.quota_ok)) else ToolHealthState.DEGRADED,p)
@dataclass(frozen=True,slots=True)
class ToolCapability: name:str; version:str
@dataclass(frozen=True,slots=True)
class ToolManifest: tool_id:str; capabilities:tuple[ToolCapability,...]; signed:bool
@dataclass(frozen=True,slots=True)
class ToolDiscoveryResult: manifest:ToolManifest; validated:bool; granted_authority:frozenset[str]=frozenset()
def discover(m,source_validated):return ToolDiscoveryResult(m,m.signed and source_validated,frozenset())
@dataclass(frozen=True,slots=True)
class ToolEvidence: tool_id:str; provenance:str; independent_validation:bool
@dataclass(frozen=True,slots=True)
class ToolResultTrust: label:str; evidence:ToolEvidence
@dataclass(frozen=True,slots=True)
class ToolValidation: high_impact:bool; accepted:bool
def validate_result(t,high_impact):return ToolValidation(high_impact,(not high_impact) or t.evidence.independent_validation)
