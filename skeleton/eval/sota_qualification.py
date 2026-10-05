"""Evidence-bound SOTA-candidate qualification for VOL-107."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,re,math
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class QualificationError(ValueError):pass
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise QualificationError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise QualificationError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class SOTACandidateClaim:
 claim_id:str;candidate_digest:str;benchmark_id:str;task_scope:str;population_scope:str;metric_id:str;researcher_id:str
 def __post_init__(self):
  for f in ("claim_id","benchmark_id","metric_id","researcher_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  _sha(self.candidate_digest,"candidate_digest")
  if not isinstance(self.task_scope,str) or not isinstance(self.population_scope,str) or not self.task_scope.strip() or not self.population_scope.strip():raise QualificationError("claim scope must be explicit")\n  object.__setattr__(self,"task_scope",self.task_scope.strip());object.__setattr__(self,"population_scope",self.population_scope.strip())
 @property
 def digest(self):return _dig([self.claim_id,self.candidate_digest,self.benchmark_id,self.task_scope,self.population_scope,self.metric_id,self.researcher_id])
@dataclass(frozen=True,slots=True)
class BaselineComparison:
 claim_digest:str;baseline_id:str;baseline_digest:str;candidate_score:float;baseline_score:float;effect_size:float;confidence_low:float;contamination_checked:bool
 def __post_init__(self):
  _sha(self.claim_digest,"claim_digest");object.__setattr__(self,"baseline_id",_id(self.baseline_id,"baseline_id"));_sha(self.baseline_digest,"baseline_digest")
  for v in (self.candidate_score,self.baseline_score,self.effect_size,self.confidence_low):\n   if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v):raise QualificationError("comparison statistics must be finite numeric")\n  if not isinstance(self.contamination_checked,bool):raise QualificationError("contamination_checked must be bool")
 @property
 def supported(self):return self.contamination_checked and self.candidate_score>self.baseline_score and self.effect_size>0 and self.confidence_low>0
@dataclass(frozen=True,slots=True)
class QualificationEvidence:
 claim_digest:str;comparison:BaselineComparison;replay_digest:str;replayer_id:str;researcher_id:str;robustness_digest:str;security_digest:str;latency_digest:str;cost_digest:str;operations_digest:str
 def __post_init__(self):
  _sha(self.claim_digest,"claim_digest")
  for f in ("replayer_id","researcher_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  for f in ("replay_digest","robustness_digest","security_digest","latency_digest","cost_digest","operations_digest"):_sha(getattr(self,f),f)
  if self.comparison.claim_digest!=self.claim_digest:raise QualificationError("baseline comparison targets wrong claim")
  if self.replayer_id==self.researcher_id:raise QualificationError("benchmark replay must be independent")
 @property
 def qualified(self):return self.comparison.supported
