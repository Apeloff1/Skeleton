"""Repository-governance contracts for VOL-263..267."""
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

class Confidence(str,Enum): LOW="low"; MEDIUM="medium"; HIGH="high"
@dataclass(frozen=True,slots=True)
class LegacyArtifact:
 artifact_id:str; path:str; revision:str; digest:str
 def __post_init__(self):
  for n in ("artifact_id","path","revision"): object.__setattr__(self,n,_t(getattr(self,n),n))
  object.__setattr__(self,"digest",_d(self.digest,"digest"))
@dataclass(frozen=True,slots=True)
class IntentHypothesis:
 hypothesis_id:str; statement:str; confidence:Confidence; evidence_artifact_ids:tuple[str,...]; confirmed:bool=False
 def __post_init__(self):
  if self.confirmed and not self.evidence_artifact_ids: raise ValueError("confirmed intent requires evidence")
@dataclass(frozen=True,slots=True)
class ArchaeologyFinding:
 finding_id:str; artifact:LegacyArtifact; hypotheses:tuple[IntentHypothesis,...]
 @property
 def authoritative_intent(self)->tuple[IntentHypothesis,...]: return tuple(h for h in self.hypotheses if h.confirmed)

@dataclass(frozen=True,slots=True)
class CustodyMapping:
 source_path:str; destination_path:str; source_owner:str; destination_owner:str
 def __post_init__(self):
  for n in ("source_path","destination_path","source_owner","destination_owner"): object.__setattr__(self,n,_t(getattr(self,n),n))
  if self.source_path==self.destination_path: raise ValueError("consolidation must move custody")
@dataclass(frozen=True,slots=True)
class ConsolidationPlan:
 plan_id:str; mappings:tuple[CustodyMapping,...]; compatibility_strategy:str; import_inverted:bool=False
 def __post_init__(self):
  object.__setattr__(self,"plan_id",_t(self.plan_id,"plan_id")); object.__setattr__(self,"compatibility_strategy",_t(self.compatibility_strategy,"compatibility_strategy"))
  if not self.mappings: raise ValueError("consolidation plan requires mappings")
@dataclass(frozen=True,slots=True)
class ConsolidationEvidence:
 plan_id:str; affected_domain_digest:str; import_graph_digest:str; parity_digest:str
 def __post_init__(self):
  for n in ("affected_domain_digest","import_graph_digest","parity_digest"): object.__setattr__(self,n,_d(getattr(self,n),n))
def can_retire_source(plan:ConsolidationPlan,evidence:ConsolidationEvidence)->bool:
 return evidence.plan_id==plan.plan_id and plan.import_inverted

class OriginKind(str,Enum): AUTHORED="authored"; IMPORTED="imported"; GENERATED="generated"
@dataclass(frozen=True,slots=True)
class CodeOrigin:
 kind:OriginKind; source_identity:str; license_id:str
 def __post_init__(self):
  object.__setattr__(self,"source_identity",_t(self.source_identity,"source_identity")); object.__setattr__(self,"license_id",_t(self.license_id,"license_id"))
@dataclass(frozen=True,slots=True)
class CodeArtifact:
 artifact_id:str; digest:str; origin:CodeOrigin
 def __post_init__(self): object.__setattr__(self,"digest",_d(self.digest,"digest"))
@dataclass(frozen=True,slots=True)
class CodeTransformation:
 predecessor:CodeArtifact; successor:CodeArtifact; operation:str
 def __post_init__(self):
  object.__setattr__(self,"operation",_t(self.operation,"operation"))
  if self.successor.origin.source_identity!=self.predecessor.origin.source_identity: raise ValueError("transformation must preserve source lineage")
  if self.successor.origin.license_id!=self.predecessor.origin.license_id: raise ValueError("transformation must preserve license lineage")

class DuplicateKind(str,Enum): ACCIDENTAL="accidental"; ADAPTER="adapter"; GENERATED_MIRROR="generated_mirror"
@dataclass(frozen=True,slots=True)
class DuplicationFinding:
 finding_id:str; paths:tuple[str,...]; kind:DuplicateKind; similarity:float; ownership_evidence:str|None; dependency_evidence:str|None
 def __post_init__(self):
  if len(set(self.paths))<2: raise ValueError("duplicate finding needs distinct paths")
  if not 0<=self.similarity<=1: raise ValueError("similarity must be in [0,1]")
@dataclass(frozen=True,slots=True)
class ConvergenceProposal:
 finding:DuplicationFinding; removal_paths:tuple[str,...]
 def __post_init__(self):
  if self.finding.kind is not DuplicateKind.ACCIDENTAL and self.removal_paths: raise ValueError("intentional adapter/mirror cannot be removal proposal")
  if self.removal_paths and (not self.finding.ownership_evidence or not self.finding.dependency_evidence): raise ValueError("removal requires ownership and dependency evidence")

@dataclass(frozen=True,slots=True)
class OwnershipZone:
 zone_id:str; owner:str; path_prefixes:tuple[str,...]
@dataclass(frozen=True,slots=True)
class ModuleOwner:
 module_path:str; zone_id:str; owner:str
@dataclass(frozen=True,slots=True)
class OwnershipTransfer:
 module_path:str; from_owner:str; to_owner:str; history_digest:str; dependency_impact_digest:str
 def __post_init__(self):
  if self.from_owner==self.to_owner: raise ValueError("ownership transfer requires new owner")
  object.__setattr__(self,"history_digest",_d(self.history_digest,"history_digest")); object.__setattr__(self,"dependency_impact_digest",_d(self.dependency_impact_digest,"dependency_impact_digest"))
def resolve_owner(path:str,zones:tuple[OwnershipZone,...])->ModuleOwner:
 matches=[z for z in zones if any(path.startswith(p) for p in z.path_prefixes)]
 if len(matches)!=1: raise ValueError("production module must resolve to exactly one ownership zone")
 return ModuleOwner(path,matches[0].zone_id,matches[0].owner)
