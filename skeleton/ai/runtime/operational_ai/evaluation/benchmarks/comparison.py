"""Paired incumbent/challenger case comparison; only compare identical evidence."""
from __future__ import annotations
from dataclasses import dataclass
from .runner import BenchmarkResult
from .dataset import EvalError

@dataclass(frozen=True,slots=True)
class Comparison:
    status:str
    sample_count:int
    average_change:float
    improved:int
    regressed:int
    unchanged:int


def compare(incumbent:BenchmarkResult,challenger:BenchmarkResult,*,
            minimum_shared:int=20)->Comparison:
    if incumbent.source_sha!=challenger.source_sha or incumbent.benchmark_id!=challenger.benchmark_id:
        raise EvalError('cannot compare mismatched benchmark source identities')
    a={x.case_id:x for x in incumbent.cases if x.score is not None}
    b={x.case_id:x for x in challenger.cases if x.score is not None}
    shared=sorted(set(a)&set(b))
    if len(shared)<minimum_shared:
        return Comparison('insufficient-paired-cases',len(shared),0.0,0,0,0)
    diffs=[b[key].score.token_f1-a[key].score.token_f1 for key in shared]
    improved=sum(x>0.005 for x in diffs);regressed=sum(x<-.005 for x in diffs)
    return Comparison('paired-measured-not-promoted',len(shared),sum(diffs)/len(diffs),
        improved,regressed,len(diffs)-improved-regressed)
