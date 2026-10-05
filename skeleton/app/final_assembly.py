"""Current-main final-assembly evidence boundary for VOL-120."""
from __future__ import annotations
from dataclasses import dataclass
import re
_SHA=re.compile(r"^[0-9a-f]{64}$");_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_MAX_GATES=512;_MAX_RISKS=4096
class FinalAssemblyError(ValueError):pass
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise FinalAssemblyError(f"{f} must be sha256")
 return v
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise FinalAssemblyError(f"{f} must be stable identifier")
 return v
@dataclass(frozen=True,slots=True)
class FinalAssemblyPlan:
 plan_id:str;authority_id:str;head_digest:str;environment_digest:str;artifact_digest:str;gate_ids:tuple[str,...]
 def __post_init__(self):
  object.__setattr__(self,"plan_id",_id(self.plan_id,"plan_id"))
  object.__setattr__(self,"authority_id",_id(self.authority_id,"authority_id"))
  for f in ("head_digest","environment_digest","artifact_digest"):_sha(getattr(self,f),f)
  if not isinstance(self.gate_ids,tuple) or not self.gate_ids:raise FinalAssemblyError("gate_ids required")
  if len(self.gate_ids)>_MAX_GATES:raise FinalAssemblyError("gate count exceeds safety bound")
  ids=tuple(_id(x,"gate_id") for x in self.gate_ids)
  if len(set(ids))!=len(ids):raise FinalAssemblyError("duplicate assembly gate")
  object.__setattr__(self,"gate_ids",tuple(sorted(ids)))
@dataclass(frozen=True,slots=True)
class FinalAssemblyRun:
 plan_id:str;authority_id:str;head_digest:str;environment_digest:str;artifact_digest:str;passed_gate_ids:tuple[str,...];evidence_digest:str
 def __post_init__(self):
  object.__setattr__(self,"plan_id",_id(self.plan_id,"plan_id"))
  object.__setattr__(self,"authority_id",_id(self.authority_id,"authority_id"))
  for f in ("head_digest","environment_digest","artifact_digest","evidence_digest"):_sha(getattr(self,f),f)
  if not isinstance(self.passed_gate_ids,tuple):raise FinalAssemblyError("passed_gate_ids must be tuple")
  if len(self.passed_gate_ids)>_MAX_GATES:raise FinalAssemblyError("passed gate count exceeds safety bound")
  ids=tuple(_id(x,"gate_id") for x in self.passed_gate_ids)
  if len(set(ids))!=len(ids):raise FinalAssemblyError("duplicate passed gate")
  object.__setattr__(self,"passed_gate_ids",tuple(sorted(ids)))
@dataclass(frozen=True,slots=True)
class FinalAssemblyEvidence:
 run:FinalAssemblyRun;independent_verifier_id:str|None;verified_evidence_digest:str|None;unresolved_risk_ids:tuple[str,...]
 def __post_init__(self):
  if not isinstance(self.run,FinalAssemblyRun):raise FinalAssemblyError("run must be FinalAssemblyRun")
  if not isinstance(self.unresolved_risk_ids,tuple):raise FinalAssemblyError("unresolved_risk_ids must be tuple")
  if len(self.unresolved_risk_ids)>_MAX_RISKS:raise FinalAssemblyError("risk count exceeds safety bound")
  risks=tuple(_id(x,"risk_id") for x in self.unresolved_risk_ids)
  if len(set(risks))!=len(risks):raise FinalAssemblyError("duplicate unresolved risk")
  object.__setattr__(self,"unresolved_risk_ids",tuple(sorted(risks)))
  if (self.independent_verifier_id is None)!=(self.verified_evidence_digest is None):raise FinalAssemblyError("verifier identity and verified digest must be paired")
  if self.independent_verifier_id is not None:
   object.__setattr__(self,"independent_verifier_id",_id(self.independent_verifier_id,"independent_verifier_id"));_sha(self.verified_evidence_digest,"verified_evidence_digest")
def qualify(plan,evidence):
 if not isinstance(plan,FinalAssemblyPlan) or not isinstance(evidence,FinalAssemblyEvidence):raise FinalAssemblyError("typed plan and evidence required")
 run=evidence.run
 if run.plan_id!=plan.plan_id or run.authority_id!=plan.authority_id or run.head_digest!=plan.head_digest or run.environment_digest!=plan.environment_digest or run.artifact_digest!=plan.artifact_digest:raise FinalAssemblyError("assembly run does not match exact plan")
 if run.passed_gate_ids!=plan.gate_ids:raise FinalAssemblyError("all exact assembly gates must pass")
 if evidence.unresolved_risk_ids:raise FinalAssemblyError("unresolved release risks block qualification")
 if evidence.independent_verifier_id is None:raise FinalAssemblyError("independent verification required")
 if evidence.independent_verifier_id==plan.authority_id:raise FinalAssemblyError("verifier must be independent from assembly authority")
 if evidence.verified_evidence_digest!=run.evidence_digest:raise FinalAssemblyError("verified evidence digest mismatch")
 return run.evidence_digest
