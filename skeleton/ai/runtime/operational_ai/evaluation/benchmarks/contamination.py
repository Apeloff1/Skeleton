"""Exact and overlap-based train/evaluation contamination controls."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from .dataset import EvalSet,EvalError
from .metrics import normalize

@dataclass(frozen=True,slots=True)
class ContaminationReport:
    clean:bool
    matching_ids:tuple[str,...]
    matched_inputs:tuple[str,...]


def check_contamination(train:EvalSet,holdout:EvalSet)->ContaminationReport:
    if train.split not in ('train','validation') or holdout.split not in ('test','holdout'):
        raise EvalError('contamination check must compare development and heldout evidence')
    ids={c.case_id for c in train.cases}
    normalized={sha256(normalize(c.prompt).encode()).hexdigest() for c in train.cases}
    matching=sorted(c.case_id for c in holdout.cases if c.case_id in ids)
    overlaps=sorted(c.case_id for c in holdout.cases if sha256(normalize(c.prompt).encode()).hexdigest() in normalized)
    return ContaminationReport(not matching and not overlaps,tuple(matching),tuple(overlaps))
