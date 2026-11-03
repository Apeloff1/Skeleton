"""Bounded segment evaluator that never claims unexecuted cases have passed."""
from __future__ import annotations
from dataclasses import dataclass
from .challenge_catalog import iter_challenges,TOTAL
from .challenge_schema import Challenge
from .challenge_executor import execute,ProbeResult
from .canonical import digest,require_int,require_sha
from .errors import reject
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime


@dataclass(frozen=True,slots=True)
class ChallengeRun:
    model_sha256:str
    source_sha256:str
    start:int
    requested:int
    results:tuple[ProbeResult,...]

    @property
    def complete(self)->bool:
        return (self.start==0 and self.requested==TOTAL
                and len(self.results)==TOTAL)

    def report(self)->dict:
        return {
            "schema":"skeleton.native-supervised.challenge-run.v1",
            "model_sha256":self.model_sha256,
            "source_sha256":self.source_sha256,
            "start":self.start,"evaluated":len(self.results),
            "required_total":TOTAL,
            "complete":self.complete,
            "passed":sum(x.passed for x in self.results),
            "failed":sum(not x.passed for x in self.results),
            "cases":[x.record() for x in self.results],
            "actual_native_generation":True,
            "independent_replay_verified":False,
            "production_authorized":False,
        }


def evaluate_segment(
    runtime:NativeLLMRuntime,*,start:int=0,count:int=24,
    max_new_tokens:int=32,expected_model_sha256:str,
)->ChallengeRun:
    if type(runtime) is not NativeLLMRuntime:
        reject("challenge-real-runtime")
    require_sha(expected_model_sha256,"challenge-model")
    if runtime.model_digest!=expected_model_sha256:
        reject("challenge-model-identity")
    require_int(start,"challenge-start",0,TOTAL-1)
    require_int(count,"challenge-count",1,TOTAL)
    if start+count>TOTAL:
        reject("challenge-segment-overflow")
    cases=tuple(iter_challenges())
    if len(cases)!=TOTAL:
        reject("challenge-incomplete-source")
    dig=digest([item.record() for item in cases])
    output=[]
    for case in cases[start:start+count]:
        output.append(execute(runtime,case,max_new_tokens=max_new_tokens,
                              seed=case.ordinal))
    if len(output)!=count or any(x.model_sha256!=expected_model_sha256 for x in output):
        reject("challenge-inference-count")
    return ChallengeRun(expected_model_sha256,dig,start,count,tuple(output))
