"""October 2026 engineering-standards evidence review for VOL-221..VOL-234."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib,json
from typing import Mapping

class EngineeringStandardsReviewError(ValueError): pass

_REQUIRED=(
 "model_card","dataset_card","tool_card","agent_card","component_health","dependency_health",
 "provider_risk","provider_failover","offline_mode","air_gap","edge_deployment",
 "enterprise_deployment","identity_federation","administration_plane",
)

def _token(n:str,v:object)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>512: raise EngineeringStandardsReviewError(f"{n} must be non-empty normalized text")
    return v
def _sha(n:str,v:object)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise EngineeringStandardsReviewError(f"{n} must be lowercase sha256")
    return v
def _digest(v:object)->str:return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class EngineeringStandardsReview:
    review_id:str
    source_revision:str
    subject_id:str
    evidence_digests:Mapping[str,str]
    blocker_codes:tuple[str,...]
    producer_id:str
    independent_verifier_id:str
    status:str
    promotion_authority:bool=False
    production_authority:bool=False

    def __post_init__(self):
        object.__setattr__(self,"review_id",_token("review_id",self.review_id)); object.__setattr__(self,"subject_id",_token("subject_id",self.subject_id))
        object.__setattr__(self,"producer_id",_token("producer_id",self.producer_id)); object.__setattr__(self,"independent_verifier_id",_token("independent_verifier_id",self.independent_verifier_id))
        if self.producer_id==self.independent_verifier_id: raise EngineeringStandardsReviewError("independent verifier must differ from producer")
        revision=_token("source_revision",self.source_revision).lower()
        if len(revision)!=40 or any(c not in "0123456789abcdef" for c in revision): raise EngineeringStandardsReviewError("source_revision must be exact lowercase Git SHA")
        object.__setattr__(self,"source_revision",revision)
        evidence=dict(self.evidence_digests)
        if set(evidence)!=set(_REQUIRED): raise EngineeringStandardsReviewError("evidence set must exactly cover VOL-221..234")
        object.__setattr__(self,"evidence_digests",dict(sorted((k,_sha(k,v)) for k,v in evidence.items())))
        blockers=tuple(sorted({_token("blocker_code",b,128) for b in self.blocker_codes})); object.__setattr__(self,"blocker_codes",blockers)
        expected="ready_for_independent_closure" if not blockers else "blocked"
        if self.status!=expected: raise EngineeringStandardsReviewError("status must match blocker evidence")
        if self.promotion_authority is not False or self.production_authority is not False: raise EngineeringStandardsReviewError("review cannot grant promotion or production authority")

    @property
    def digest(self)->str:
        return _digest({"review_id":self.review_id,"source_revision":self.source_revision,"subject_id":self.subject_id,"evidence_digests":dict(self.evidence_digests),"blocker_codes":list(self.blocker_codes),"producer_id":self.producer_id,"independent_verifier_id":self.independent_verifier_id,"status":self.status,"promotion_authority":False,"production_authority":False})

def build_engineering_standards_review(*,review_id:str,source_revision:str,subject_id:str,evidence_digests:Mapping[str,str],blocker_codes:tuple[str,...],producer_id:str,independent_verifier_id:str)->EngineeringStandardsReview:
    return EngineeringStandardsReview(
        review_id,source_revision,subject_id,evidence_digests,blocker_codes,
        producer_id,independent_verifier_id,
        "ready_for_independent_closure" if not blocker_codes else "blocked",
    )
