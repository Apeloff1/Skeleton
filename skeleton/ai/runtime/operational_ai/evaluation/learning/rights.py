"""Training purpose scope and license policy must be independently approved."""
from __future__ import annotations
from dataclasses import dataclass
from .dataset import TrainingRecord,LearningError

@dataclass(frozen=True,slots=True)
class RightsDecision:
    admitted:bool
    reasons:tuple[str,...]
    source_sha:str


def evaluate_rights(record:TrainingRecord,*,allowed_licenses:tuple[str,...],
                    allowed_origins:tuple[str,...],purpose:str='training')->RightsDecision:
    if purpose not in {'training','evaluation','distillation'}:
        raise LearningError('unrecognized data usage purpose')
    reasons=[]
    if record.license not in allowed_licenses:reasons.append('license-not-approved')
    if not any(record.provenance.startswith(origin) for origin in allowed_origins):
        reasons.append('origin-not-approved')
    if not record.consent_confirmed:reasons.append('consent-unknown')
    return RightsDecision(not reasons,tuple(reasons),record.source_sha)
