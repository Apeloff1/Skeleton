"""Deterministic evaluation evidence and non-authoritative promotion eligibility."""
from __future__ import annotations
from dataclasses import dataclass, field
import hmac, math
from types import MappingProxyType
from typing import Mapping
from .registry import ModelArtifact, canonical_digest
from .publication import TrainingCompletion, PublicationError

MAX_EVAL_METRICS=128

class EvaluationError(PublicationError): pass

@dataclass(frozen=True)
class EvaluationEvidence:
    artifact_digest:str
    completion_digest:str
    suite_digest:str
    metrics:Mapping[str,float]=field(default_factory=dict)
    passed:bool=False
    authority_scope:str="evidence-only"
    def __post_init__(self):
        for name in ("artifact_digest","completion_digest","suite_digest"):
            v=getattr(self,name)
            if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise EvaluationError(f"invalid {name}")
        if not isinstance(self.passed,bool): raise EvaluationError("passed must be bool")
        if self.authority_scope!="evidence-only": raise EvaluationError("evaluation cannot grant execution authority")
        if len(self.metrics)>MAX_EVAL_METRICS: raise EvaluationError("too many evaluation metrics")
        clean={}
        for k,v in sorted(self.metrics.items()):
            if not isinstance(k,str) or not k or len(k)>128: raise EvaluationError("invalid metric name")
            if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v): raise EvaluationError("invalid metric")
            clean[k]=float(v)
        object.__setattr__(self,"metrics",MappingProxyType(clean))
    @property
    def evidence_digest(self):
        return canonical_digest({"artifact_digest":self.artifact_digest,"completion_digest":self.completion_digest,"suite_digest":self.suite_digest,"metrics":dict(self.metrics),"passed":self.passed,"authority_scope":self.authority_scope})

@dataclass(frozen=True)
class PromotionEligibility:
    artifact_digest:str
    completion_digest:str
    evaluation_digest:str
    eligible:bool
    authority_scope:str="eligibility-only"
    def __post_init__(self):
        for name in ("artifact_digest","completion_digest","evaluation_digest"):
            v=getattr(self,name)
            if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise EvaluationError(f"invalid {name}")
        if not isinstance(self.eligible,bool): raise EvaluationError("eligible must be bool")
        if self.authority_scope!="eligibility-only": raise EvaluationError("eligibility cannot grant execution authority")
    @property
    def eligibility_digest(self):
        return canonical_digest({"artifact_digest":self.artifact_digest,"completion_digest":self.completion_digest,"evaluation_digest":self.evaluation_digest,"eligible":self.eligible,"authority_scope":self.authority_scope})

def assess_eligibility(artifact:ModelArtifact,completion:TrainingCompletion,evidence:EvaluationEvidence)->PromotionEligibility:
    if not isinstance(artifact,ModelArtifact) or not isinstance(completion,TrainingCompletion) or not isinstance(evidence,EvaluationEvidence):
        raise EvaluationError("typed artifact, completion and evidence required")
    if not hmac.compare_digest(artifact.artifact_digest,evidence.artifact_digest): raise EvaluationError("evaluation artifact mismatch")
    if not hmac.compare_digest(completion.completion_digest,evidence.completion_digest): raise EvaluationError("evaluation completion mismatch")
    if not hmac.compare_digest(artifact.training_run_digest,completion.run_digest): raise EvaluationError("artifact completion lineage mismatch")
    if not hmac.compare_digest(artifact.evaluation_digest,evidence.suite_digest): raise EvaluationError("evaluation suite mismatch")
    return PromotionEligibility(artifact.artifact_digest,completion.completion_digest,evidence.evidence_digest,evidence.passed)
