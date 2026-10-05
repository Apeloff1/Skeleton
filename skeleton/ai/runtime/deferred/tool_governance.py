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
 missing=set(f"{d.target}@{d.target_version}" for d in g.dependencies if (d.target,d.target_version) not in g.available)
 graph={x:set() for x in g.available}
 for d in g.dependencies:
  source=(d.source,d.source_version);target=(d.target,d.target_version)
  if not all((d.source,d.source_version,d.target,d.target_version,d.kind)):missing.add("invalid-dependency")
  graph.setdefault(source,set()).add(target)
 visiting=set();visited=set()
 def cycle(n):
  if n in visiting:return True
  if n in visited:return False
  visiting.add(n)
  if any(cycle(x) for x in graph.get(n,())):return True
  visiting.remove(n);visited.add(n);return False
 if any(cycle(n) for n in sorted(graph) if n not in visited):missing.add("dependency-cycle")
 unavailable=tuple(sorted(missing));return ToolCompatibility(not unavailable,unavailable)
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
