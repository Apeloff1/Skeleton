"""Evidence-bound scientific research contracts for VOL-099."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class ResearchError(ValueError): pass
class Outcome(str,Enum):
 SUPPORTS="supports"; CONTRADICTS="contradicts"; AMBIGUOUS="ambiguous"; NEGATIVE="negative"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v): raise ResearchError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v): raise ResearchError(f"{f} must be sha256")
 return v
def _digest(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class ResearchQuestion:
 question_id:str; question:str; claim_scope:str; limitations:tuple[str,...]
 def __post_init__(self):
  object.__setattr__(self,"question_id",_id(self.question_id,"question_id"))
  if not self.question.strip() or not self.claim_scope.strip() or not self.limitations: raise ResearchError("question scope and limitations required")
@dataclass(frozen=True,slots=True)
class EvidenceNode:
 evidence_id:str; source_id:str; source_digest:str; method:str; claim_ids:tuple[str,...]; outcome:Outcome
 def __post_init__(self):
  for f in ("evidence_id","source_id"): object.__setattr__(self,f,_id(getattr(self,f),f))
  _sha(self.source_digest,"source_digest")
  if not self.method.strip() or not self.claim_ids: raise ResearchError("method and claim relationships required")
  object.__setattr__(self,"claim_ids",tuple(sorted(set(_id(x,"claim_id") for x in self.claim_ids))))
 @property
 def digest(self): return _digest({"evidence_id":self.evidence_id,"source_id":self.source_id,"source_digest":self.source_digest,"method":self.method,"claim_ids":self.claim_ids,"outcome":self.outcome.value})
@dataclass(frozen=True,slots=True)
class ExperimentPlan:
 experiment_id:str; hypothesis:str; metric_ids:tuple[str,...]; success_rule:str; max_trials:int
 def __post_init__(self):
  object.__setattr__(self,"experiment_id",_id(self.experiment_id,"experiment_id"))
  if not self.hypothesis.strip() or not self.success_rule.strip(): raise ResearchError("preregistered hypothesis and success rule required")
  object.__setattr__(self,"metric_ids",tuple(sorted(set(_id(x,"metric_id") for x in self.metric_ids))))
  if not self.metric_ids or isinstance(self.max_trials,bool) or not isinstance(self.max_trials,int) or not 1<=self.max_trials<=10000: raise ResearchError("experiment metrics/trial budget invalid")
 @property
 def digest(self): return _digest({"experiment_id":self.experiment_id,"hypothesis":self.hypothesis,"metric_ids":self.metric_ids,"success_rule":self.success_rule,"max_trials":self.max_trials})
@dataclass(frozen=True,slots=True)
class ReproductionRecord:
 reproduction_id:str; evidence_digest:str; experiment_digest:str; metric_values:tuple[tuple[str,float],...]; outcome:Outcome; trial_count:int
 def __post_init__(self):
  object.__setattr__(self,"reproduction_id",_id(self.reproduction_id,"reproduction_id"));_sha(self.evidence_digest,"evidence_digest");_sha(self.experiment_digest,"experiment_digest")
  vals=tuple(sorted(self.metric_values))
  if not vals: raise ResearchError("reproduction metrics required")
  for k,v in vals: _id(k,"metric_id"); json.dumps(v,allow_nan=False)
  object.__setattr__(self,"metric_values",vals)
  if self.trial_count<1: raise ResearchError("trial_count must be positive")
@dataclass(frozen=True,slots=True)
class ResearchConclusion:
 conclusion_id:str; question_id:str; claim_id:str; evidence_digests:tuple[str,...]; outcomes:tuple[Outcome,...]; statement:str; limitations:tuple[str,...]
 def __post_init__(self):
  for f in ("conclusion_id","question_id","claim_id"): object.__setattr__(self,f,_id(getattr(self,f),f))
  for d in self.evidence_digests: _sha(d,"evidence_digest")
  if not self.evidence_digests or len(self.evidence_digests)!=len(self.outcomes): raise ResearchError("conclusion requires outcome-bound evidence")
  if not self.statement.strip() or not self.limitations: raise ResearchError("conclusion statement and limitations required")
  if any(o in (Outcome.CONTRADICTS,Outcome.AMBIGUOUS,Outcome.NEGATIVE) for o in self.outcomes) and "conflicting_or_negative_evidence" not in self.limitations: raise ResearchError("conclusion must disclose conflicting/negative evidence")
class EvidenceGraph:
 def __init__(self): self.nodes={}
 def add(self,node):
  prior=self.nodes.get(node.evidence_id)
  if prior is not None and prior!=node: raise ResearchError("evidence identity immutable")
  self.nodes[node.evidence_id]=node
 def for_claim(self,claim_id):
  _id(claim_id,"claim_id"); return tuple(sorted((n for n in self.nodes.values() if claim_id in n.claim_ids),key=lambda n:n.evidence_id))
