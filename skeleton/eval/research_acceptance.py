"""Research-system acceptance contracts for VOL-106."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class ResearchAcceptanceError(ValueError):pass
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise ResearchAcceptanceError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise ResearchAcceptanceError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class ClaimEvidenceCoverage:
 claim_id:str;evidence_digests:tuple[str,...];contradiction_digests:tuple[str,...];uncertainty_recorded:bool;negative_results_preserved:bool
 def __post_init__(self):
  object.__setattr__(self,"claim_id",_id(self.claim_id,"claim_id"))
  if not isinstance(self.evidence_digests,tuple) or not isinstance(self.contradiction_digests,tuple):raise ResearchAcceptanceError("evidence collections must be tuples")\n  if len(self.evidence_digests)>256 or len(self.contradiction_digests)>256:raise ResearchAcceptanceError("evidence collection too large")\n  for d in self.evidence_digests+self.contradiction_digests:_sha(d,"evidence_digest")
  if len(set(self.evidence_digests))!=len(self.evidence_digests) or len(set(self.contradiction_digests))!=len(self.contradiction_digests):raise ResearchAcceptanceError("duplicate evidence digest")\n  if set(self.evidence_digests)&set(self.contradiction_digests):raise ResearchAcceptanceError("evidence cannot be both support and contradiction")\n  if not isinstance(self.uncertainty_recorded,bool) or not isinstance(self.negative_results_preserved,bool):raise ResearchAcceptanceError("coverage flags must be bool")\n  if not self.evidence_digests:raise ResearchAcceptanceError("claim requires supporting evidence")
 @property
 def complete(self):return self.uncertainty_recorded and self.negative_results_preserved
@dataclass(frozen=True,slots=True)
class ReproductionEvidence:
 reproduction_id:str;claim_id:str;method_digest:str;result_digest:str;reproducer_id:str;original_researcher_id:str;reproduced:bool
 def __post_init__(self):
  for f in ("reproduction_id","claim_id","reproducer_id","original_researcher_id"):object.__setattr__(self,f,_id(getattr(self,f),f))
  _sha(self.method_digest,"method_digest");_sha(self.result_digest,"result_digest")
  if not isinstance(self.reproduced,bool):raise ResearchAcceptanceError("reproduced must be bool")\n  if self.reproducer_id==self.original_researcher_id:raise ResearchAcceptanceError("reproduction must be independent")
@dataclass(frozen=True,slots=True)
class ResearchAcceptance:
 acceptance_id:str;conclusion_digest:str;coverage:tuple[ClaimEvidenceCoverage,...];reproductions:tuple[ReproductionEvidence,...];high_impact:bool;reviewer_id:str;researcher_id:str
 def __post_init__(self):
  object.__setattr__(self,"acceptance_id",_id(self.acceptance_id,"acceptance_id"));_sha(self.conclusion_digest,"conclusion_digest")
  object.__setattr__(self,"reviewer_id",_id(self.reviewer_id,"reviewer_id"));object.__setattr__(self,"researcher_id",_id(self.researcher_id,"researcher_id"))
  if self.high_impact and self.reviewer_id==self.researcher_id:raise ResearchAcceptanceError("high-impact conclusion requires independent review")
  if not isinstance(self.high_impact,bool):raise ResearchAcceptanceError("high_impact must be bool")\n  if not isinstance(self.coverage,tuple) or not isinstance(self.reproductions,tuple):raise ResearchAcceptanceError("acceptance collections must be tuples")\n  if any(not isinstance(x,ClaimEvidenceCoverage) for x in self.coverage) or any(not isinstance(x,ReproductionEvidence) for x in self.reproductions):raise ResearchAcceptanceError("acceptance evidence must be typed")\n  claims=[c.claim_id for c in self.coverage]
  if not claims or len(set(claims))!=len(claims):raise ResearchAcceptanceError("claim coverage must be nonempty and unique")
 @property
 def eligible(self):
  if not all(c.complete for c in self.coverage):return False
  by_claim={r.claim_id for r in self.reproductions if r.reproduced}
  return all(c.claim_id in by_claim for c in self.coverage)
 @property
 def digest(self):return _dig({"id":self.acceptance_id,"conclusion":self.conclusion_digest,"coverage":[[c.claim_id,c.evidence_digests,c.contradiction_digests,c.uncertainty_recorded,c.negative_results_preserved] for c in self.coverage],"reproductions":[[r.reproduction_id,r.claim_id,r.method_digest,r.result_digest,r.reproducer_id,r.reproduced] for r in self.reproductions],"high_impact":self.high_impact,"reviewer":self.reviewer_id,"researcher":self.researcher_id})
