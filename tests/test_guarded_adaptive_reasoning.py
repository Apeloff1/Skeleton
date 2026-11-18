import asyncio
from dataclasses import replace
import hashlib
from types import SimpleNamespace

import pytest
from skeleton.ai.runtime.inference.adaptive_reasoning import CandidateAssessment, ReasoningPolicy, run_guarded
from skeleton.ai.runtime.inference.local import LocalInferenceRequest, LocalInferenceResult
from skeleton.context.pre_delivery_guard import TrustedContextSnapshot, PreDeliveryReceipt
from skeleton.context.sealed_sandwich import SealedContextBoundaryError


def test_adaptive_stops_after_independent_threshold():
    snapshot=TrustedContextSnapshot("a"*64,"b"*64,1,"tenant","context")
    requests=[LocalInferenceRequest("Question",seed=i,max_output_tokens=16,tool_choice="none") for i in range(3)]
    seen=[]
    class Service:
        async def _read(self,**kwargs):
            return snapshot
        async def generate(self,r,**kwargs):
            seen.append(r.seed)
            text=f"candidate {r.seed}"
            result=LocalInferenceResult(text,"model","c"*64,2,3)
            receipt=PreDeliveryReceipt(snapshot.root,None,"guard",r.digest,hashlib.sha256(text.encode()).hexdigest())
            return SimpleNamespace(result=result,receipt=receipt)
    async def assess(result,proof):
        return CandidateAssessment(proof.response_sha256,proof.request_digest,"independent","d"*64,
                                   960000 if result.text.endswith("1") else 100000,True)
    outcome=asyncio.run(run_guarded(Service(),requests,tenant_scope_id="tenant",context_id="context",
                  policy=ReasoningPolicy(maximum_reserved_tokens=48),evaluator_id="independent",assess=assess))
    assert seen==[0,1] and outcome.receipt["reserved_tokens"]==32
    assert outcome.selected.result.text=="candidate 1"


def test_adaptive_cannot_override_original_prompt():
    request=LocalInferenceRequest("original",tool_choice="none")
    with pytest.raises(ValueError,match="immutable"):
        asyncio.run(run_guarded(None,[request,replace(request,prompt="changed")],
                    tenant_scope_id="tenant",context_id="context",policy=ReasoningPolicy(),
                    evaluator_id="e",assess=lambda *args: None))
