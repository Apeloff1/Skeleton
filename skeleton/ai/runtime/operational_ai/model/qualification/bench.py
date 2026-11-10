"""Actual native-model endurance probe, without fallback or user-data retention.

On any failure or timeout, stop. Never retry a potentially completed native call.
This is a burn-in observation, not an accuracy, safety, or device certificate.
"""
from __future__ import annotations
from hashlib import sha256
import time
from .contracts import BurnInPolicy,QualificationHeld
from skeleton.ai.runtime.operational_ai.authority.canonical import ContractViolation
from .latency import summarize
from .records import trial_record

_SYSTEM='You are an offline native runtime under a local stability probe. No tools.'
_PROMPTS=(
    'State a short harmless observation about your offline operation.',
    'Describe how a local model processes a short user request.',
    'Explain why native model computation does not imply network access.',
    'Provide a concise note about deterministic local inference receipts.',
)


def measure(backend, policy:BurnInPolicy,*,clock=time.monotonic_ns) -> dict:
    if not isinstance(policy,BurnInPolicy):raise QualificationHeld('validated trial policy required')
    model=getattr(backend,'model_digest',None)
    tokenizer=getattr(backend,'tokenizer_digest',None)
    if (not isinstance(model,str) or len(model)!=64 or
        not isinstance(tokenizer,str) or len(tokenizer)!=64):
        raise QualificationHeld('pinned real model and tokenizer identities required')
    results=[]
    latencies=[]
    tokens=[]
    for index in range(1,policy.trials+1):
        gate=getattr(backend,'admit_before_reservation',None)
        if not callable(gate):
            raise QualificationHeld('native model lacks a live capacity gate')
        gate()  # always before spending native compute
        prompt=_PROMPTS[(index-1)%len(_PROMPTS)]
        inputs=[{'role':'system','content':_SYSTEM},{'role':'user','content':prompt}]
        begin=clock()
        try:
            receipt=backend.generate(inputs,max_output_tokens=policy.max_output_tokens,
                                     seed=42+index,temperature=0.5)
        except ContractViolation:
            # A malformed model receipt is a qualification hold, never a pass.
            # Do not stringify provider-controlled exception content, retry
            # an already-started native call, or manufacture an output.
            raise QualificationHeld('native generated receipt rejected') from None
        except BaseException:
            # No retry. The isolated model child must be shutdown by its
            # enclosing context manager; the request is not considered good.
            raise
        elapsed=clock()-begin
        if elapsed<=0 or elapsed>policy.inference_ms*1_000_000:
            raise QualificationHeld('native generation missed monotonic deadline')
        recorded=trial_record(index,elapsed,receipt,model,tokenizer,policy.max_output_tokens)
        if recorded['generated_tokens']<policy.minimum_generated_tokens:
            raise QualificationHeld('native token floor was not met')
        results.append(recorded)
        latencies.append(elapsed)
        tokens.append(recorded['generated_tokens'])
    summary=summarize(latencies,tokens)
    if summary['p99_ns']>policy.maximum_p99_ms*1_000_000:
        raise QualificationHeld('observed p99 native response latency exceeded operator ceiling')
    return {'schema':'skeleton.native-gguf-endurance.v1',
            'status':'backend-receipts-observed-not-release-certified',
            'model_sha256':model,'tokenizer_sha256':tokenizer,
            'policy':policy.record(), 'summary':summary,
            'trials':results,
            'claims_excluded':['model-quality','rights','GPU-qualification',
                               'device-compatibility','full-release','consumer-install']}
