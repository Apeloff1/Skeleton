"""Independent challenger promotion requires exact model, evaluation, and rollback evidence."""
from __future__ import annotations
from dataclasses import dataclass
from .candidate import CandidateRecord
from .dataset import LearningError

@dataclass(frozen=True,slots=True)
class PromotionEvidence:
    candidate_sha:str
    eval_sha:str
    baseline_sha:str
    safety_passed:bool
    quality_passed:bool
    rollback_verified:bool
    independent_review:bool
    canary_passed:bool


def promotion_eligibility(candidate:CandidateRecord,evidence:PromotionEvidence)->tuple[bool,tuple[str,...]]:
    reasons=[]
    if candidate.model_sha!=evidence.candidate_sha:reasons.append('candidate-identity-mismatch')
    if candidate.parent_sha!=evidence.baseline_sha:reasons.append('baseline-identity-mismatch')
    for field in ('safety_passed','quality_passed','rollback_verified','independent_review','canary_passed'):
        if getattr(evidence,field) is not True:reasons.append('missing:'+field)
    if not evidence.eval_sha or len(evidence.eval_sha)!=64:
        reasons.append('evaluation-evidence-invalid')
    return not reasons,tuple(reasons)
