"""Research, model and instruction operations for VOL-238..242."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Sequence
from .contracts import sha256_json

def _t(v:object,n:str)->str:
 if not isinstance(v,str) or not v.strip(): raise ValueError(f"{n} must be non-empty text")
 return v.strip()
def _d(v:object,n:str)->str:
 v=_t(v,n)
 if len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ValueError(f"{n} must be lowercase sha256")
 return v

class EvidenceState(str,Enum): VERIFIED="verified"; CONTRADICTED="contradicted"; UNVERIFIED="unverified"
@dataclass(frozen=True,slots=True)
class ResearchFindingView:
 finding_id:str; narrative:str; evidence_state:EvidenceState; source_revision:str; experiment_id:str
 def __post_init__(self):
  for n in ("finding_id","narrative","source_revision","experiment_id"): object.__setattr__(self,n,_t(getattr(self,n),n))
@dataclass(frozen=True,slots=True)
class ResearchGap: gap_id:str; reason:str
@dataclass(frozen=True,slots=True)
class ResearchDashboard:
 findings:tuple[ResearchFindingView,...]; gaps:tuple[ResearchGap,...]
 @property
 def verified_count(self)->int: return sum(f.evidence_state is EvidenceState.VERIFIED for f in self.findings)

@dataclass(frozen=True,slots=True)
class ModelDeployment:
 deployment_id:str; model_digest:str; config_digest:str; evaluation_digest:str; stage:str
 def __post_init__(self):
  object.__setattr__(self,"deployment_id",_t(self.deployment_id,"deployment_id"))
  for n in ("model_digest","config_digest","evaluation_digest"): object.__setattr__(self,n,_d(getattr(self,n),n))
  object.__setattr__(self,"stage",_t(self.stage,"stage"))
 @property
 def identity(self)->str: return sha256_json({"deployment_id":self.deployment_id,"model":self.model_digest,"config":self.config_digest,"eval":self.evaluation_digest,"stage":self.stage})
@dataclass(frozen=True,slots=True)
class ModelHealth: deployment_id:str; healthy:bool; evidence_digest:str
@dataclass(frozen=True,slots=True)
class ModelOpsDecision: deployment_id:str; promote:bool; reason:str

def decide_promotion(d:ModelDeployment,h:ModelHealth)->ModelOpsDecision:
 if h.deployment_id!=d.deployment_id: return ModelOpsDecision(d.deployment_id,False,"health/deployment mismatch")
 if not h.healthy: return ModelOpsDecision(d.deployment_id,False,"deployment unhealthy")
 return ModelOpsDecision(d.deployment_id,True,"bound evaluation and health accepted")

@dataclass(frozen=True,slots=True)
class ModelVersionFence:
 deployment_id:str; model_digest:str; config_digest:str
 def __post_init__(self):
  object.__setattr__(self,"deployment_id",_t(self.deployment_id,"deployment_id")); object.__setattr__(self,"model_digest",_d(self.model_digest,"model_digest")); object.__setattr__(self,"config_digest",_d(self.config_digest,"config_digest"))
@dataclass(frozen=True,slots=True)
class ModelRollbackPlan:
 active:ModelVersionFence; target:ModelVersionFence; reconcile_sessions:bool; invalidate_cache:bool
 def __post_init__(self):
  if self.active.deployment_id==self.target.deployment_id: raise ValueError("rollback target must be prior deployment")
  if not self.reconcile_sessions or not self.invalidate_cache: raise ValueError("rollback requires session reconciliation and cache invalidation")
@dataclass(frozen=True,slots=True)
class ModelRollbackReceipt: from_deployment:str; to_deployment:str; completed:bool; evidence_digest:str

@dataclass(frozen=True,slots=True)
class InstructionVersion:
 version_id:str; content_digest:str; intended_model_digest:str; capability:str; regression_evidence_digest:str
 def __post_init__(self):
  object.__setattr__(self,"version_id",_t(self.version_id,"version_id")); object.__setattr__(self,"capability",_t(self.capability,"capability"))
  for n in ("content_digest","intended_model_digest","regression_evidence_digest"): object.__setattr__(self,n,_d(getattr(self,n),n))
@dataclass(frozen=True,slots=True)
class InstructionAsset:
 asset_id:str; versions:tuple[InstructionVersion,...]
 def __post_init__(self):
  object.__setattr__(self,"asset_id",_t(self.asset_id,"asset_id"))
  ids=[v.version_id for v in self.versions]
  if not ids or len(ids)!=len(set(ids)): raise ValueError("instruction versions must be non-empty and unique")
@dataclass(frozen=True,slots=True)
class InstructionBinding:
 asset_id:str; version_id:str; model_digest:str; capability:str; authority_grants:tuple[str,...]=()
 def __post_init__(self):
  if self.authority_grants: raise ValueError("instruction text cannot grant authority")

def bind_instruction(asset:InstructionAsset,version_id:str,model_digest:str,capability:str)->InstructionBinding:
 matches=[v for v in asset.versions if v.version_id==version_id]
 if len(matches)!=1: raise LookupError("instruction version not found")
 v=matches[0]
 if v.intended_model_digest!=model_digest or v.capability!=capability: raise PermissionError("instruction binding context mismatch")
 return InstructionBinding(asset.asset_id,v.version_id,model_digest,capability)

@dataclass(frozen=True,slots=True)
class PromptBaseline:
 model_digest:str; config_digest:str; tool_context_digest:str; quality:float; safety:float; cost:float; nondeterminism:float
@dataclass(frozen=True,slots=True)
class PromptTest:
 test_id:str; baseline:PromptBaseline; max_quality_drop:float; max_safety_drop:float; max_cost_increase:float; max_nondeterminism_increase:float
@dataclass(frozen=True,slots=True)
class PromptRegression:
 test_id:str; passed:bool; reasons:tuple[str,...]

def evaluate_prompt(test:PromptTest,candidate:PromptBaseline)->PromptRegression:
 if (candidate.model_digest,candidate.config_digest,candidate.tool_context_digest)!=(test.baseline.model_digest,test.baseline.config_digest,test.baseline.tool_context_digest):
  return PromptRegression(test.test_id,False,("execution context changed",))
 reasons=[]
 if test.baseline.quality-candidate.quality>test.max_quality_drop: reasons.append("quality regression")
 if test.baseline.safety-candidate.safety>test.max_safety_drop: reasons.append("safety regression")
 if candidate.cost-test.baseline.cost>test.max_cost_increase: reasons.append("cost regression")
 if candidate.nondeterminism-test.baseline.nondeterminism>test.max_nondeterminism_increase: reasons.append("nondeterminism regression")
 return PromptRegression(test.test_id,not reasons,tuple(reasons))
