"""Temporal, hypothesis and causal knowledge integrity for VOL-247/249/250."""
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

@dataclass(frozen=True,slots=True)
class ValidityInterval:
 valid_from:int; valid_to:int|None
 def __post_init__(self):
  if isinstance(self.valid_from,bool) or not isinstance(self.valid_from,int): raise TypeError("valid_from must be integer")
  if self.valid_to is not None and (not isinstance(self.valid_to,int) or self.valid_to<=self.valid_from): raise ValueError("valid_to must be after valid_from")

@dataclass(frozen=True,slots=True)
class TemporalClaim:
 claim_id:str; subject:str; predicate:str; value:str; validity:ValidityInterval; recorded_at:int; evidence_digest:str
 def __post_init__(self):
  for n in ("claim_id","subject","predicate","value"): object.__setattr__(self,n,_t(getattr(self,n),n))
  object.__setattr__(self,"evidence_digest",_d(self.evidence_digest,"evidence_digest"))
  if self.recorded_at<0: raise ValueError("recorded_at must be non-negative")

@dataclass(frozen=True,slots=True)
class KnowledgeRevision:
 revision_id:str; claim:TemporalClaim; supersedes:str|None
 def __post_init__(self):
  object.__setattr__(self,"revision_id",_t(self.revision_id,"revision_id"))
  if self.supersedes is not None: object.__setattr__(self,"supersedes",_t(self.supersedes,"supersedes"))

class TemporalKnowledge:
 def __init__(self): self._revisions:list[KnowledgeRevision]=[]
 def append(self,r:KnowledgeRevision)->None:
  if any(x.revision_id==r.revision_id for x in self._revisions): raise ValueError("duplicate revision")
  if r.supersedes is not None and not any(x.revision_id==r.supersedes for x in self._revisions): raise ValueError("superseded revision missing")
  self._revisions.append(r)
 def as_of(self,recorded_at:int,valid_at:int)->tuple[KnowledgeRevision,...]:
  candidates=[r for r in self._revisions if r.claim.recorded_at<=recorded_at and r.claim.validity.valid_from<=valid_at and (r.claim.validity.valid_to is None or valid_at<r.claim.validity.valid_to)]
  superseded={r.supersedes for r in candidates if r.supersedes}
  return tuple(r for r in candidates if r.revision_id not in superseded)
 @property
 def history(self)->tuple[KnowledgeRevision,...]: return tuple(self._revisions)

class HypothesisStatus(str,Enum): OPEN="open"; SUPPORTED="supported"; FALSIFIED="falsified"
class EvidenceDirection(str,Enum): SUPPORTS="supports"; CONTRADICTS="contradicts"
@dataclass(frozen=True,slots=True)
class Hypothesis:
 hypothesis_id:str; statement:str; plausibility:float; status:HypothesisStatus=HypothesisStatus.OPEN
 def __post_init__(self):
  object.__setattr__(self,"hypothesis_id",_t(self.hypothesis_id,"hypothesis_id")); object.__setattr__(self,"statement",_t(self.statement,"statement"))
  if not 0<=self.plausibility<=1: raise ValueError("plausibility must be in [0,1]")
@dataclass(frozen=True,slots=True)
class HypothesisEvidence:
 evidence_id:str; hypothesis_id:str; direction:EvidenceDirection; artifact_digest:str; method:str
 def __post_init__(self):
  for n in ("evidence_id","hypothesis_id","method"): object.__setattr__(self,n,_t(getattr(self,n),n))
  object.__setattr__(self,"artifact_digest",_d(self.artifact_digest,"artifact_digest"))
class HypothesisEngine:
 def __init__(self,hypotheses:Sequence[Hypothesis]):
  self.hypotheses={h.hypothesis_id:h for h in hypotheses}; self.evidence:list[HypothesisEvidence]=[]
 def add_evidence(self,e:HypothesisEvidence)->None:
  if e.hypothesis_id not in self.hypotheses: raise LookupError("unknown hypothesis")
  if any(x.evidence_id==e.evidence_id for x in self.evidence): raise ValueError("duplicate evidence")
  self.evidence.append(e)
 def resolve(self,hypothesis_id:str)->HypothesisStatus:
  ev=[e for e in self.evidence if e.hypothesis_id==hypothesis_id]
  if any(e.direction is EvidenceDirection.CONTRADICTS for e in ev): return HypothesisStatus.FALSIFIED
  if ev and all(e.direction is EvidenceDirection.SUPPORTS for e in ev): return HypothesisStatus.SUPPORTED
  return HypothesisStatus.OPEN

class CausalMethod(str,Enum): OBSERVATIONAL="observational"; RANDOMIZED="randomized"; QUASI_EXPERIMENTAL="quasi_experimental"; SIMULATED="simulated"
@dataclass(frozen=True,slots=True)
class CausalClaim:
 claim_id:str; cause:str; effect:str; method:CausalMethod; evidence_digest:str; assumptions:tuple[str,...]
 def __post_init__(self):
  for n in ("claim_id","cause","effect"): object.__setattr__(self,n,_t(getattr(self,n),n))
  object.__setattr__(self,"evidence_digest",_d(self.evidence_digest,"evidence_digest"))
  if not self.assumptions: raise ValueError("causal claim requires explicit assumptions")
@dataclass(frozen=True,slots=True)
class CausalGraph:
 claims:tuple[CausalClaim,...]
 def __post_init__(self):
  ids=[c.claim_id for c in self.claims]
  if len(ids)!=len(set(ids)): raise ValueError("causal claim ids must be unique")
@dataclass(frozen=True,slots=True)
class InterventionResult:
 intervention_id:str; claim_id:str; method:CausalMethod; observed:bool; result_digest:str
 def __post_init__(self):
  object.__setattr__(self,"intervention_id",_t(self.intervention_id,"intervention_id")); object.__setattr__(self,"claim_id",_t(self.claim_id,"claim_id")); object.__setattr__(self,"result_digest",_d(self.result_digest,"result_digest"))
  if self.method is CausalMethod.SIMULATED and self.observed: raise ValueError("simulated intervention cannot be labeled observed")
