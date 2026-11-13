"""Bounded reproducible evaluation against an injected *real* model adapter.

The harness never supplies a synthetic successful model result. For fixtures,
callers may inject a deterministic test backend, clearly marked non-qualifying.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib,json,time
from typing import Protocol
from .dataset import EvalCase,EvalSet,EvalError
from .metrics import eval_text,EvaluationScore

class EvaluatedModel(Protocol):
    @property
    def model_digest(self)->str:...
    def answer(self,prompt:str,seed:int,max_tokens:int)->str:...

@dataclass(frozen=True,slots=True)
class CaseResult:
    case_id:str
    category:str
    score:EvaluationScore|None
    status:str
    output_sha:str|None
    elapsed_ns:int

@dataclass(frozen=True,slots=True)
class BenchmarkResult:
    benchmark_id:str
    source_sha:str
    model_sha:str
    cases:tuple[CaseResult,...]
    duration_ns:int
    completed:int
    failures:int
    status:str

class BenchmarkRunner:
    def __init__(self,model:EvaluatedModel,*,max_tokens:int=256,
                 max_cases:int=1000,max_output_bytes:int=128_000):
        if type(max_tokens) is not int or not 1<=max_tokens<=4096:
            raise EvalError('invalid evaluation output token limit')
        if type(max_cases) is not int or not 1<=max_cases<=10_000:
            raise EvalError('invalid bounded evaluation count')
        if type(max_output_bytes) is not int or not 1<=max_output_bytes<=262144:
            raise EvalError('invalid model evaluation text byte cap')
        self.model=model;self.max_tokens=max_tokens;self.max_cases=max_cases
        self.max_bytes=max_output_bytes

    def run(self,suite:EvalSet)->BenchmarkResult:
        if not isinstance(suite,EvalSet) or len(suite.cases)>self.max_cases:
            raise EvalError('unapproved or oversized evaluation suite')
        started=time.monotonic_ns();results=[]
        for case in suite.cases:
            t0=time.monotonic_ns()
            try:
                answer=self.model.answer(case.prompt,case.seed,self.max_tokens)
                if not isinstance(answer,str) or len(answer.encode())>self.max_bytes:
                    raise EvalError('model output exceeds evaluation contract')
                score=eval_text(answer,case.expected)
                outcome=CaseResult(case.case_id,case.category,score,'measured',
                            hashlib.sha256(answer.encode()).hexdigest(),time.monotonic_ns()-t0)
            except Exception:
                outcome=CaseResult(case.case_id,case.category,None,'failed',None,time.monotonic_ns()-t0)
            results.append(outcome)
        failures=sum(x.status!='measured' for x in results)
        return BenchmarkResult(suite.set_id,suite.source_sha,self.model.model_digest,
            tuple(results),time.monotonic_ns()-started,len(results)-failures,failures,
            'measured-no-release-claim' if not failures else 'incomplete')
