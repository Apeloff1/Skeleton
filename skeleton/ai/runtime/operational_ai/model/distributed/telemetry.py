"""Numeric serving observations without leaking prompts, tokens, identities or secrets."""
from __future__ import annotations
from dataclasses import dataclass
from statistics import mean
from .workers import WorkerError

@dataclass(frozen=True,slots=True)
class ServingSample:
    input_tokens:int
    output_tokens:int
    duration_ns:int
    status:str


def summarize(samples:tuple[ServingSample,...],*,maximum:int=10_000)->dict:
    if len(samples)>maximum:raise WorkerError('too many serving observations')
    if any(type(x.input_tokens) is not int or x.input_tokens<0
           or type(x.output_tokens) is not int or x.output_tokens<0
           or type(x.duration_ns) is not int or x.duration_ns<0
           or x.status not in {'ok','blocked','failed','cancelled'} for x in samples):
        raise WorkerError('malformed serving sample')
    success=[x for x in samples if x.status=='ok']
    return {'requests':len(samples),'completed':len(success),'failed':sum(x.status=='failed' for x in samples),
            'tokens_out':sum(x.output_tokens for x in success),'mean_latency_ns':int(mean(x.duration_ns for x in success)) if success else None}
