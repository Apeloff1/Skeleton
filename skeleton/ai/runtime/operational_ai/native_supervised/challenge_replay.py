"""Independently re-execute a bounded native challenge run from pinned weights.

A JSON result alone is not actual-inference proof: only this replay can
substantiate the deterministic inference receipts. Latency is intentionally
not compared, but all model/output/usage/finish identities must match.
"""
from __future__ import annotations
from dataclasses import dataclass
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from .challenge_runner import ChallengeRun
from .challenge_catalog import iter_challenges,TOTAL
from .challenge_executor import execute
from .canonical import digest,require_int
from .errors import reject


@dataclass(frozen=True,slots=True)
class ReplayAudit:
    model_sha256:str
    tokenizer_sha256:str
    source_sha256:str
    evaluated:int
    matching:int
    mismatched_ids:tuple[str,...]
    evidence_sha256:str

    def record(self)->dict:
        return {
            "schema":"skeleton.native-supervised.challenge-replay.v1",
            **{name:getattr(self,name) for name in self.__dataclass_fields__},
            "real_native_recomputation":True,
            "full_768_replayed":self.evaluated==TOTAL,
            "replay_clean":self.evaluated==self.matching,
            "release_certified":False,
        }


def reexecute(
    runtime:NativeLLMRuntime,original:ChallengeRun,*,
    max_new_tokens:int=32,
)->ReplayAudit:
    if type(runtime) is not NativeLLMRuntime or type(original) is not ChallengeRun:
        reject("replay-contract")
    require_int(max_new_tokens,"replay-new-tokens",1,256)
    runtime.assert_model_unchanged()
    if original.model_sha256!=runtime.model_digest:
        reject("replay-model-sha")
    all_cases=tuple(iter_challenges())
    if len(all_cases)!=TOTAL or original.source_sha256!=digest([
        case.record() for case in all_cases
    ]):
        reject("replay-case-source")
    begin=original.start
    if not 0<=begin<TOTAL or not 1<=len(original.results)<=TOTAL-begin:
        reject("replay-segment")
    mismatched=[]
    observed=[]
    for index,record in enumerate(original.results):
        case=all_cases[begin+index]
        computed=execute(runtime,case,max_new_tokens=max_new_tokens,seed=case.ordinal)
        stable=(
            "case_id","domain","severity","case_sha256","prompt_sha256",
            "expected_sha256","actual_sha256","model_sha256",
            "tokenizer_sha256","replay_receipt_sha256","passed",
            "prompt_tokens","generated_tokens","finish_reason",
        )
        if any(getattr(record,name)!=getattr(computed,name) for name in stable):
            mismatched.append(case.case_id)
        observed.append({key:getattr(computed,key) for key in stable})
    return ReplayAudit(
        runtime.model_digest,runtime.tokenizer.digest,
        original.source_sha256,len(original.results),
        len(original.results)-len(mismatched),tuple(mismatched),
        digest(observed),
    )
