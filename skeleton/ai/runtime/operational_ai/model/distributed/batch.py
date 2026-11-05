"""Deadline- and model-compatible microbatch grouping, no padding or cross-model contamination."""
from __future__ import annotations
from dataclasses import dataclass
from .queues import InferenceJob
from .workers import WorkerError

@dataclass(frozen=True,slots=True)
class MicroBatch:
    model_sha:str
    jobs:tuple[InferenceJob,...]
    total_tokens:int

class BatchPlanner:
    def __init__(self,*,max_jobs:int=8,max_tokens:int=65536):
        if type(max_jobs) is not int or not 1<=max_jobs<=128 or type(max_tokens) is not int or not 128<=max_tokens<=1_048_576:
            raise WorkerError('invalid microbatch resource cap')
        self.max_jobs=max_jobs;self.max_tokens=max_tokens

    def group(self,jobs:tuple[InferenceJob,...])->tuple[MicroBatch,...]:
        if len(jobs)>4096:raise WorkerError('unbounded pending batch input')
        by_model={}
        for job in jobs:
            by_model.setdefault(job.model_sha,[]).append(job)
        result=[]
        for model,items in sorted(by_model.items()):
            items.sort(key=lambda j:(-j.priority,j.ordinal))
            current=[];budget=0
            for job in items:
                if job.cost_tokens>self.max_tokens:raise WorkerError('job exceeds single-batch capacity')
                if current and (len(current)>=self.max_jobs or budget+job.cost_tokens>self.max_tokens):
                    result.append(MicroBatch(model,tuple(current),budget));current=[];budget=0
                current.append(job);budget+=job.cost_tokens
            if current:result.append(MicroBatch(model,tuple(current),budget))
        return tuple(result)
