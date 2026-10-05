"""Exact-revision research/evaluation evidence bundle for VOL-210..VOL-220."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
from typing import Mapping

class ResearchEvaluationReviewError(ValueError): pass

_REQUIRED=(
    "research_agent_team","literature_watch","citation_graph","reproduction_package",
    "experiment_comparison","statistical_analysis","model_eval","agent_eval",
    "long_horizon","contamination_audit","human_evaluation",
)

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise ResearchEvaluationReviewError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise ResearchEvaluationReviewError(f"{n} must be lowercase sha256")
    return v
def _digest(v:object)->str: return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class ResearchEvaluationReview:
    review_id:str
    source_revision:str
    subject_id:str
    evidence_digests:Mapping[str,str]
    blockers:tuple[str,...]
    status:str
    independent_verifier_id:str
    producer_id:str
    promotion_authority:bool=False

    def __post_init__(self):
        object.__setattr__(self,"review_id",_token("review_id",self.review_id))
        object.__setattr__(self,"subject_id",_token("subject_id",self.subject_id))
        object.__setattr__(self,"independent_verifier_id",_token("independent_verifier_id",self.independent_verifier_id))
        object.__setattr__(self,"producer_id",_token("producer_id",self.producer_id))
        if self.independent_verifier_id==self.producer_id: raise ResearchEvaluationReviewError("verifier must be independent from producer")
        rev=_token("source_revision",self.source_revision).lower()
        if len(rev)!=40 or any(c not in "0123456789abcdef" for c in rev): raise ResearchEvaluationReviewError("source_revision must be a 40-character lowercase Git SHA")
        object.__setattr__(self,"source_revision",rev)
        evidence=dict(self.evidence_digests)
        if set(evidence)!=set(_REQUIRED): raise ResearchEvaluationReviewError("evidence_digests must contain the exact VOL-210..220 evidence set")
        object.__setattr__(self,"evidence_digests",dict(sorted((k,_sha(k,v)) for k,v in evidence.items())))
        blockers=tuple(sorted({_token("blocker",b) for b in self.blockers}))
        object.__setattr__(self,"blockers",blockers)
        expected="ready_for_independent_closure" if not blockers else "blocked"
        if self.status!=expected: raise ResearchEvaluationReviewError("status must match blocker evidence")
        if self.promotion_authority is not False: raise ResearchEvaluationReviewError("review cannot grant promotion authority")

    @property
    def digest(self)->str:
        return _digest({
            "review_id":self.review_id,
            "source_revision":self.source_revision,
            "subject_id":self.subject_id,
            "evidence_digests":dict(self.evidence_digests),
            "blockers":list(self.blockers),
            "status":self.status,
            "independent_verifier_id":self.independent_verifier_id,
            "producer_id":self.producer_id,
            "promotion_authority":False,
        })

def build_research_evaluation_review(*,review_id:str,source_revision:str,subject_id:str,evidence_digests:Mapping[str,str],blockers:tuple[str,...],independent_verifier_id:str,producer_id:str)->ResearchEvaluationReview:
    return ResearchEvaluationReview(
        review_id=review_id,source_revision=source_revision,subject_id=subject_id,
        evidence_digests=evidence_digests,blockers=blockers,
        status="ready_for_independent_closure" if not blockers else "blocked",
        independent_verifier_id=independent_verifier_id,producer_id=producer_id,
    )
