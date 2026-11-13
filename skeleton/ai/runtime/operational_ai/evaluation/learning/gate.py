"""Training approval preflight with negative holds for contamination and rights."""
from __future__ import annotations
from dataclasses import dataclass
from .dataset import TrainingDataset
from .dedupe import duplicates
from .rights import evaluate_rights

@dataclass(frozen=True,slots=True)
class TrainingGate:
    permitted:bool
    reasons:tuple[str,...]
    dataset_sha:str
    count:int


def training_gate(dataset:TrainingDataset,*,allowed_licenses:tuple[str,...],
                  allowed_origins:tuple[str,...],independent_approval:bool=False,
                  heldout_input_hashes:frozenset[str]=frozenset())->TrainingGate:
    reasons=[]
    if not independent_approval:reasons.append('independent-training-approval-missing')
    if dataset.split!='train':reasons.append('non-training-partition')
    dedupe=duplicates(dataset)
    if dedupe.exact or dedupe.normalized:reasons.append('training-duplicates')
    for record in dataset.records:
        if not evaluate_rights(record,allowed_licenses=allowed_licenses,allowed_origins=allowed_origins).admitted:
            reasons.append('unauthorized-rights:'+record.sample_id)
        if record.source_sha in heldout_input_hashes:reasons.append('heldout-contamination:'+record.sample_id)
    return TrainingGate(not reasons,tuple(reasons),dataset.dataset_sha,len(dataset.records))
