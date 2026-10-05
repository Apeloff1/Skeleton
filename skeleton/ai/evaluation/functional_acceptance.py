"""Immutable functional-AI acceptance evidence for VOL-104."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class AcceptanceError(ValueError):pass
class Criterion(str,Enum): VS001="vs001"; FAILURE="failure"; RECOVERY="recovery"; SECURITY="security"; QUALITY="quality"; STATE="state"; TOOL_GOVERNANCE="tool_governance"; PROVENANCE="provenance"; STREAMING="streaming"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise AcceptanceError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise AcceptanceError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class AcceptanceEvidence:
 evidence_id:str;criterion:Criterion;artifact_digest:str;passed:bool;negative_findings:tuple[str,...]=()
 def __post_init__(self):
  object.__setattr__(self,"evidence_id",_id(self.evidence_id,"evidence_id"));_sha(self.artifact_digest,"artifact_digest")
  if not isinstance(self.criterion,Criterion):raise AcceptanceError("criterion must be Criterion")
  if not isinstance(self.passed,bool):raise AcceptanceError("passed must be bool")
  if not isinstance(self.negative_findings,tuple) or len(self.negative_findings)>256:raise AcceptanceError("negative_findings must be bounded tuple")
  if any(not isinstance(x,str) or not x.strip() for x in self.negative_findings):raise AcceptanceError("negative finding invalid")
  object.__setattr__(self,"negative_findings",tuple(sorted(set(x.strip() for x in self.negative_findings))))
@dataclass(frozen=True,slots=True)
class FunctionalAIAcceptance:
 acceptance_id:str;source_digest:str;config_digest:str;model_digest:str;environment_digest:str;evidence:tuple[AcceptanceEvidence,...];builder_id:str
 def __post_init__(self):
  object.__setattr__(self,"acceptance_id",_id(self.acceptance_id,"acceptance_id"));object.__setattr__(self,"builder_id",_id(self.builder_id,"builder_id"))
  for f in ("source_digest","config_digest","model_digest","environment_digest"):_sha(getattr(self,f),f)
  if not isinstance(self.evidence,tuple) or any(not isinstance(x,AcceptanceEvidence) for x in self.evidence):raise AcceptanceError("evidence must be typed tuple")
  ev=tuple(sorted(self.evidence,key=lambda x:(x.criterion.value,x.evidence_id)))
  if len({x.evidence_id for x in ev})!=len(ev):raise AcceptanceError("duplicate evidence identity")
  if len({x.criterion for x in ev})!=len(ev):raise AcceptanceError("criterion must have exactly one evidence record")
  required=set(Criterion);present={x.criterion for x in ev}
  if present!=required:raise AcceptanceError("acceptance matrix incomplete")
  object.__setattr__(self,"evidence",ev)
 @property
 def digest(self):return _dig({"acceptance_id":self.acceptance_id,"source":self.source_digest,"config":self.config_digest,"model":self.model_digest,"environment":self.environment_digest,"evidence":[{"id":e.evidence_id,"criterion":e.criterion.value,"artifact":e.artifact_digest,"passed":e.passed,"negative_findings":e.negative_findings} for e in self.evidence],"builder":self.builder_id})
 @property
 def eligible(self):return all(e.passed for e in self.evidence)
@dataclass(frozen=True,slots=True)
class AcceptanceSignoff:
 acceptance_digest:str;reviewer_id:str;builder_id:str;approved:bool
 def __post_init__(self):
  _sha(self.acceptance_digest,"acceptance_digest");object.__setattr__(self,"reviewer_id",_id(self.reviewer_id,"reviewer_id"));object.__setattr__(self,"builder_id",_id(self.builder_id,"builder_id"))
  if not isinstance(self.approved,bool):raise AcceptanceError("approved must be bool")
  if self.reviewer_id==self.builder_id:raise AcceptanceError("acceptance reviewer must be independent")
def sign(bundle:FunctionalAIAcceptance,reviewer_id:str)->AcceptanceSignoff:
 if not bundle.eligible:raise AcceptanceError("failed criterion cannot be accepted")
 return AcceptanceSignoff(bundle.digest,reviewer_id,bundle.builder_id,True)

def verify_signoff(bundle:FunctionalAIAcceptance,signoff:AcceptanceSignoff)->None:
 if not isinstance(bundle,FunctionalAIAcceptance) or not isinstance(signoff,AcceptanceSignoff):raise AcceptanceError("verification inputs must be typed")
 if not signoff.approved:raise AcceptanceError("signoff is not approved")
 if not bundle.eligible:raise AcceptanceError("failed criterion cannot be verified")
 if signoff.acceptance_digest!=bundle.digest or signoff.builder_id!=bundle.builder_id:raise AcceptanceError("stale or mismatched acceptance signoff")
 if signoff.reviewer_id==bundle.builder_id:raise AcceptanceError("acceptance reviewer must be independent")
