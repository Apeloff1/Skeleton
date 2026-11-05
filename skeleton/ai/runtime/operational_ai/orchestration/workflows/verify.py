"""Verify native model output before durable commit and distinguish abstentions."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from .graph import WorkflowError

@dataclass(frozen=True,slots=True)
class Verification:
    status:str
    reasons:tuple[str,...]
    output_sha:str


def verify_output(text:str,*,max_bytes:int,require_nonempty:bool=True,
                  banned_markers:tuple[str,...]=())->Verification:
    if not isinstance(text,str):raise WorkflowError('model output must be text')
    raw=text.encode('utf8')
    reasons=[]
    if len(raw)>max_bytes:reasons.append('answer-budget-exceeded')
    if require_nonempty and not text.strip():reasons.append('empty-answer')
    if any(marker and marker in text for marker in banned_markers):
        reasons.append('disallowed-output-marker')
    return Verification('qualified' if not reasons else 'blocked',tuple(reasons),sha256(raw).hexdigest())
