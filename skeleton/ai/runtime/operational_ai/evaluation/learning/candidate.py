"""Candidate models are immutable quarantine objects until independent promotion."""
from __future__ import annotations
from dataclasses import dataclass
from .dataset import LearningError
import re

_SHA=re.compile(r'^[0-9a-f]{64}$')

@dataclass(frozen=True,slots=True)
class CandidateRecord:
    candidate_id:str
    model_sha:str
    parent_sha:str
    dataset_sha:str
    training_recipe_sha:str
    checkpoint_sha:str
    status:str='quarantined'

    def __post_init__(self):
        for name in ('model_sha','parent_sha','dataset_sha','training_recipe_sha','checkpoint_sha'):
            if not _SHA.fullmatch(getattr(self,name)):
                raise LearningError('candidate requires pinned full SHA')
        if self.status!='quarantined':
            raise LearningError('new candidate must start in quarantine')

class CandidateRegistry:
    def __init__(self):self._items={}

    def admit(self,candidate:CandidateRecord)->bool:
        existing=self._items.get(candidate.candidate_id)
        if existing:
            if existing!=candidate:raise LearningError('candidate identity reused with divergent bytes')
            return False
        self._items[candidate.candidate_id]=candidate
        return True

    def get(self,candidate_id:str)->CandidateRecord:
        if candidate_id not in self._items:raise LearningError('candidate not registered')
        return self._items[candidate_id]
