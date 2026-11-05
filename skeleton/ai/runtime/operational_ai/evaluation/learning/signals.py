"""Measured feedback signals cannot directly modify production inference weights."""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from .dataset import LearningError

@dataclass(frozen=True,slots=True)
class Feedback:
    operation_id:str
    candidate_sha:str
    metric_id:str
    value:float
    baseline:float
    evidence_sha:str
    approved:bool

    def __post_init__(self):
        if not all(isinstance(x,str) and x for x in (self.operation_id,self.metric_id)):
            raise LearningError('missing feedback identity')
        if not all(isinstance(x,str) and len(x)==64 for x in (self.candidate_sha,self.evidence_sha)):
            raise LearningError('feedback missing provenance identities')
        if not all(isinstance(x,(int,float)) and isfinite(x) for x in (self.value,self.baseline)):
            raise LearningError('feedback must be finite measured numbers')
        if type(self.approved) is not bool:
            raise LearningError('feedback review status must be explicit')


def aggregate_feedback(items:tuple[Feedback,...],*,minimum:int=10)->dict:
    if not items:return {'status':'insufficient','count':0}
    if len({(x.operation_id,x.metric_id) for x in items})!=len(items):
        raise LearningError('duplicate feedback events')
    measured=[x for x in items if x.approved]
    if len(measured)<minimum:
        return {'status':'insufficient','count':len(measured)}
    deltas=[x.value-x.baseline for x in measured]
    return {'status':'measured-not-promoted','count':len(measured),
            'mean_change':sum(deltas)/len(deltas),'regressions':sum(x<0 for x in deltas)}
