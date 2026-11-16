"""Bounded adaptive test-time compute under the existing canonical guard.

Only pre-authorized immutable requests are eligible. No candidate text is
injected as instructions or delegated to tools; no self-assessed authority.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import hashlib
import json
import math
import time
from typing import Awaitable, Callable, Sequence

from skeleton.context.pre_delivery_guard import DeliveryContract
from skeleton.context.sealed_sandwich import SealedContextBoundaryError, SealedContextReplayError
from .local import LocalInferenceRequest, LocalInferenceResult


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def pin(value):
    return isinstance(value,str) and len(value)==64 and all(ch in "0123456789abcdef" for ch in value)


@dataclass(frozen=True)
class ReasoningPolicy:
    max_attempts: int = 4
    maximum_reserved_tokens: int = 2048
    target_score_ppm: int = 950000
    minimum_score_ppm: int = 750000
    max_seconds: int = 120
    minimum_distinct_candidates: int = 1

    def __post_init__(self):
        for value,lo,hi in ((self.max_attempts,1,8),(self.maximum_reserved_tokens,1,32768),
                            (self.minimum_score_ppm,0,1000000),(self.target_score_ppm,0,1000000),
                            (self.max_seconds,1,1800),(self.minimum_distinct_candidates,1,self.max_attempts)):
            if type(value) is not int or not lo<=value<=hi:
                raise ValueError("invalid adaptive reasoning budget")
        if self.minimum_score_ppm>self.target_score_ppm:
            raise ValueError("reasoning quality thresholds inverted")


@dataclass(frozen=True)
class CandidateAssessment:
    response_sha256: str
    request_sha256: str
    evaluator_id: str
    evidence_sha256: str
    score_ppm: int
    eligible: bool

    def __post_init__(self):
        if not all(pin(x) for x in (self.response_sha256,self.request_sha256,self.evidence_sha256)):
            raise ValueError("assessment lacks bound evidence")
        if not isinstance(self.evaluator_id,str) or not 1<=len(self.evaluator_id)<=128:
            raise ValueError("independent evaluator identity required")
        if type(self.score_ppm) is not int or not 0<=self.score_ppm<=1000000 or type(self.eligible) is not bool:
            raise ValueError("invalid assessment score")


@dataclass(frozen=True)
class AdaptiveGeneration:
    selected: object
    receipt: dict


async def run_guarded(service, requests: Sequence[LocalInferenceRequest], *,
                      tenant_scope_id: str, context_id: str,
                      policy: ReasoningPolicy, evaluator_id: str,
                      assess: Callable[..., Awaitable[CandidateAssessment]],
                      contract: DeliveryContract=DeliveryContract(), deadline=None):
    """Try independently authorized variants until evidence or budget closes.

    All scoring is delegated to an app-owned independent verifier, never the
    generator. The verifier must not return raw candidate text to a client.
    """
    if not isinstance(policy,ReasoningPolicy) or not callable(assess) or not 1<=len(requests)<=policy.max_attempts:
        raise ValueError("bounded trusted reasoning plan required")
    if not isinstance(evaluator_id,str) or not 1<=len(evaluator_id)<=128:
        raise ValueError("trusted evaluator ID required")
    if any(not isinstance(r,LocalInferenceRequest) or r.tools or r.structured_output_schema is not None or r.tool_choice!="none" for r in requests):
        raise ValueError("adaptive reasoning accepts tool-free guarded text requests only")
    if contract.format!="text":
        raise ValueError("adaptive text reasoning does not rewrite structured contracts")
    baseline=requests[0]
    # Only the sampling effort can differ. User input, authority root and
    # original instructions are never altered by a rejected completion.
    for r in requests:
        if replace(r,seed=baseline.seed,max_output_tokens=baseline.max_output_tokens,
                   temperature=baseline.temperature,top_k=baseline.top_k,
                   top_p=baseline.top_p,min_p=baseline.min_p).digest!=baseline.digest:
            raise ValueError("reasoning candidate changed immutable source")
    if len({r.digest for r in requests})!=len(requests):
        raise ValueError("duplicate adaptive request")
    if deadline is not None and (type(deadline) not in {int,float} or not math.isfinite(deadline)):
        raise ValueError("invalid monotonic deadline")
    stop=min(deadline if deadline is not None else math.inf,time.monotonic()+policy.max_seconds)
    baseline_snapshot=None
    authorized={}
    async with asyncio.timeout_at(stop):
        for r in requests:
            snapshot=await service._read(tenant_scope_id=tenant_scope_id,context_id=context_id,
                                         request_digest=r.digest,deadline=stop)
            if baseline_snapshot is None:
                baseline_snapshot=snapshot
            if snapshot!=baseline_snapshot:
                raise SealedContextReplayError("adaptive candidates do not share canonical authority")
            authorized[r.digest]=snapshot
    records=[]
    selected=None
    best=-1
    reserved=0
    distinct=set()
    reason="attempt_limit"
    for r in requests:
        if time.monotonic()>=stop:
            reason="deadline"
            break
        if reserved+r.max_output_tokens>policy.maximum_reserved_tokens:
            reason="token_budget"
            break
        reserved+=r.max_output_tokens
        async with asyncio.timeout_at(stop):
            current=await service._read(tenant_scope_id=tenant_scope_id,context_id=context_id,
                                        request_digest=r.digest,deadline=stop)
            if current!=authorized[r.digest]:
                raise SealedContextReplayError("adaptive source changed before dispatch")
            generated=await service.generate(r,tenant_scope_id=tenant_scope_id,context_id=context_id,
                                             contract=contract,deadline=stop)
            result=generated.result
            if (not isinstance(result,LocalInferenceResult) or result.tool_calls or
                    result.finish_reason not in {"completed","length"} or not isinstance(result.text,str) or
                    not result.text.strip() or result.output_tokens>r.max_output_tokens):
                raise SealedContextBoundaryError("adaptive candidate is incomplete")
            response=hashlib.sha256(result.text.encode()).hexdigest()
            proof=generated.receipt
            if proof.request_digest!=r.digest or proof.context_root!=current.root or proof.response_sha256!=response:
                raise SealedContextBoundaryError("adaptive guard receipt binding mismatch")
            try:
                verdict=await assess(result,proof)
            except Exception:
                raise SealedContextBoundaryError("independent reasoning verifier unavailable") from None
            if (not isinstance(verdict,CandidateAssessment) or verdict.evaluator_id!=evaluator_id
                or verdict.request_sha256!=r.digest or verdict.response_sha256!=response
                or evaluator_id in {result.model_id,result.model_digest}):
                raise SealedContextBoundaryError("adaptive assessment identity mismatch")
            records.append({"request_sha256":r.digest,"response_sha256":response,
                            "score_ppm":verdict.score_ppm,"eligible":verdict.eligible,
                            "evidence_sha256":verdict.evidence_sha256,
                            "reserved_tokens":r.max_output_tokens,"output_tokens":result.output_tokens})
            if verdict.eligible:
                distinct.add(response)
                if verdict.score_ppm>best:
                    best=verdict.score_ppm
                    selected=(r,generated,response)
            if best>=policy.target_score_ppm and len(distinct)>=policy.minimum_distinct_candidates:
                reason="target_met"
                break
    if selected is None or best<policy.minimum_score_ppm or len(distinct)<policy.minimum_distinct_candidates:
        raise SealedContextBoundaryError("adaptive reasoning did not meet independent evidence floor")
    chosen,result,response=selected
    current=await service._read(tenant_scope_id=tenant_scope_id,context_id=context_id,
                                request_digest=chosen.digest,deadline=stop)
    if current!=authorized[chosen.digest]:
        raise SealedContextReplayError("adaptive source changed before delivery")
    receipt={"schema":"skeleton.guarded-adaptive-reasoning.v1",
             "context_root":current.root,"snapshot_version":current.snapshot_version,
             "evaluator_id":evaluator_id,"reserved_tokens":reserved,"attempts":records,
             "selected_response_sha256":response,"selected_request_sha256":chosen.digest,
             "stop_reason":reason,"score_ppm":best}
    receipt["receipt_sha256"]=digest(receipt)
    return AdaptiveGeneration(result,receipt)
