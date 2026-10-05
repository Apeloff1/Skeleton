"""Champion/challenger promotion control for VOL-101."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re,math
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class ImprovementError(ValueError):pass
class PromotionStatus(str,Enum): PROMOTE="promote"; REJECT="reject"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise ImprovementError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise ImprovementError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class ImprovementCandidate:
 candidate_id:str;champion_digest:str;challenger_digest:str;experiment_scope:str;metric_ids:tuple[str,...];builder_id:str
 def __post_init__(self):
  for f in ("candidate_id","builder_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  _sha(self.champion_digest,"champion_digest");_sha(self.challenger_digest,"challenger_digest")
  if self.champion_digest==self.challenger_digest:raise ImprovementError("challenger must differ from champion")
  if not isinstance(self.experiment_scope,str) or not self.experiment_scope.strip():raise ImprovementError("isolated experiment scope required")\n  object.__setattr__(self,"experiment_scope",self.experiment_scope.strip())\n  if not isinstance(self.metric_ids,tuple) or len(self.metric_ids)>256:raise ImprovementError("metric_ids must be bounded tuple")
  metrics=tuple(sorted(set(_id(x,"metric_id") for x in self.metric_ids)))
  if not metrics:raise ImprovementError("predeclared metrics required")
  object.__setattr__(self,"metric_ids",metrics)
 @property
 def digest(self):return _dig({"candidate_id":self.candidate_id,"champion":self.champion_digest,"challenger":self.challenger_digest,"scope":self.experiment_scope,"metrics":self.metric_ids,"builder":self.builder_id})
@dataclass(frozen=True,slots=True)
class EvaluationBundle:
 candidate_digest:str;metric_values:tuple[tuple[str,float],...];safety_passed:bool;cost_passed:bool;robustness_passed:bool;evidence_digest:str
 def __post_init__(self):
  _sha(self.candidate_digest,"candidate_digest");_sha(self.evidence_digest,"evidence_digest")
  if not isinstance(self.metric_values,tuple) or len(self.metric_values)>256:raise ImprovementError("metric_values must be bounded tuple")\n  vals=tuple(sorted(self.metric_values))
  if not vals:raise ImprovementError("evaluation metrics required")
  if len({k for k,_ in vals})!=len(vals):raise ImprovementError("duplicate evaluation metric")\n  for k,v in vals:\n   _id(k,"metric_id")\n   if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v):raise ImprovementError("metric value must be finite numeric")
  for f in ("safety_passed","cost_passed","robustness_passed"):\n   if not isinstance(getattr(self,f),bool):raise ImprovementError(f"{f} must be bool")\n  object.__setattr__(self,"metric_values",vals)
@dataclass(frozen=True,slots=True)
class PromotionDecision:
 decision_id:str;candidate_digest:str;verifier_id:str;status:PromotionStatus;evaluation_digest:str;canary_digest:str|None
 def __post_init__(self):
  for f in ("decision_id","verifier_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  _sha(self.candidate_digest,"candidate_digest");_sha(self.evaluation_digest,"evaluation_digest")
  if not isinstance(self.status,PromotionStatus):raise ImprovementError("status must be PromotionStatus")\n  if self.canary_digest is not None:_sha(self.canary_digest,"canary_digest")
  if self.status is PromotionStatus.PROMOTE and self.canary_digest is None:raise ImprovementError("promotion requires canary evidence")
@dataclass(frozen=True,slots=True)
class RollbackReceipt:
 decision_id:str;promoted_digest:str;restored_digest:str;rollback_evidence_digest:str
 def __post_init__(self):
  object.__setattr__(self,"decision_id",_id(self.decision_id,"decision_id"))
  for f in ("promoted_digest","restored_digest","rollback_evidence_digest"):_sha(getattr(self,f),f)
  if self.promoted_digest==self.restored_digest:raise ImprovementError("rollback must restore distinct champion")
def decide(candidate:ImprovementCandidate,evaluation:EvaluationBundle,verifier_id:str,*,canary_digest:str|None)->PromotionDecision:
 verifier_id=_id(verifier_id,"verifier_id")
 if verifier_id==candidate.builder_id:raise ImprovementError("promotion verifier must be independent")
 if evaluation.candidate_digest!=candidate.digest:raise ImprovementError("evaluation/candidate mismatch")
 observed={k for k,_ in evaluation.metric_values}
 if observed!=set(candidate.metric_ids):raise ImprovementError("evaluation metrics differ from preregistration")
 passed=evaluation.safety_passed and evaluation.cost_passed and evaluation.robustness_passed
 status=PromotionStatus.PROMOTE if passed else PromotionStatus.REJECT
 if status is PromotionStatus.PROMOTE and canary_digest is None:raise ImprovementError("promotion requires canary evidence")
 evdig=_dig({"candidate":evaluation.candidate_digest,"metrics":evaluation.metric_values,"safety":evaluation.safety_passed,"cost":evaluation.cost_passed,"robustness":evaluation.robustness_passed,"evidence":evaluation.evidence_digest})
 return PromotionDecision("DECISION."+candidate.candidate_id,candidate.digest,verifier_id,status,evdig,canary_digest)

def validate_rollback(candidate:ImprovementCandidate,decision:PromotionDecision,receipt:RollbackReceipt)->None:
 if not isinstance(candidate,ImprovementCandidate) or not isinstance(decision,PromotionDecision) or not isinstance(receipt,RollbackReceipt):raise ImprovementError("rollback inputs must be typed")
 if decision.status is not PromotionStatus.PROMOTE:raise ImprovementError("rollback applies only to promoted candidate")
 if decision.candidate_digest!=candidate.digest or receipt.decision_id!=decision.decision_id:raise ImprovementError("rollback identity mismatch")
 if receipt.promoted_digest!=candidate.challenger_digest or receipt.restored_digest!=candidate.champion_digest:raise ImprovementError("rollback does not restore exact champion")
