"""Deterministic resource-capped challenge batch plan with no skipped cases."""
from __future__ import annotations
from dataclasses import dataclass
from .challenge_catalog import iter_challenges,TOTAL
from .canonical import digest,require_int
from .errors import reject


@dataclass(frozen=True,slots=True)
class EvaluationBatch:
    ordinal:int
    start:int
    count:int
    source_sha256:str

    def record(self)->dict:
        return {name:getattr(self,name) for name in self.__dataclass_fields__}


def allocate(*,max_cases:int=24)->tuple[EvaluationBatch,...]:
    require_int(max_cases,"batch-size",1,96)
    cases=tuple(iter_challenges())
    if len(cases)!=TOTAL:
        reject("evaluation-batch-source")
    result=[]
    for start in range(0,TOTAL,max_cases):
        chunk=cases[start:start+max_cases]
        result.append(EvaluationBatch(
            len(result),start,len(chunk),
            digest([case.record() for case in chunk]),
        ))
    if sum(item.count for item in result)!=TOTAL:
        reject("evaluation-batch-coverage")
    return tuple(result)


def verify_plan(batches:tuple[EvaluationBatch,...])->dict:
    if type(batches) is not tuple or not batches:
        reject("evaluation-batch-plan")
    cases=tuple(iter_challenges())
    pointer=0
    for ordinal,batch in enumerate(batches):
        if type(batch) is not EvaluationBatch or batch.ordinal!=ordinal:
            reject("evaluation-batch-order")
        if batch.start!=pointer or not 1<=batch.count<=96:
            reject("evaluation-batch-gap")
        segment=cases[pointer:pointer+batch.count]
        if batch.source_sha256!=digest([case.record() for case in segment]):
            reject("evaluation-batch-source-drift")
        pointer+=batch.count
    if pointer!=TOTAL:
        reject("evaluation-batch-partial")
    return {
        "schema":"skeleton.native-supervised.eval-batch-proof.v1",
        "batches":len(batches),"source_cases":TOTAL,
        "planned_source_sha256":digest([item.record() for item in batches]),
        "native_execution_claimed":False,
    }
