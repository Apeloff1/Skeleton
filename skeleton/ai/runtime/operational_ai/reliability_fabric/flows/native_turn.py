"""Run one actual SupervisedAI native turn after caller-owned proof admission.

The durable ExecutionSpine remains authoritative for idempotent replay and
atomic transcript, outbox, hash chain and resource fences. This module never
returns an invented model completion on failure.
"""
from __future__ import annotations
from dataclasses import dataclass
from ..contracts import fail,canonical,sha256
from .preflight import inspect,Preflight
from skeleton.ai.runtime.operational_ai.laptop_runtime.result_protocol import verify_turn_receipt
from skeleton.ai.runtime.operational_ai.laptop_runtime.contracts import identifier,utf8,nonnegative,number

@dataclass(frozen=True,slots=True)
class TurnProof:
    preflight_sha256:str
    output_sha256:str
    request_id:str
    session_id:str
    replayed:bool
    prompt_tokens:int
    generated_tokens:int
    live_native_proven_by_fixture:bool=False

def complete(worker,records,*,session_id,request_id,prompt,seed=0,
             temperature=0.8):
    prepared=inspect(worker,records)
    session_id=identifier(session_id)
    request_id=identifier(request_id)
    prompt=utf8(prompt,maximum=worker.spine.limits.input_bytes)
    seed=nonnegative(seed,maximum=2**32-1)
    temperature=number(temperature,minimum=0.000000001,maximum=2)
    # The sole native inference call is made by the canonical supervisor.
    # Its SQLite request fencing, not this wrapper, owns replay authority.
    output=worker.turn(session_id,request_id,prompt,seed=seed,
                       temperature=temperature)
    receipt=verify_turn_receipt(output,model_sha256=prepared.model_sha256,
                                tokenizer_sha256=prepared.tokenizer_sha256)
    proof=TurnProof(prepared.receipt.evidence_sha256,
                    receipt["output_sha256"],request_id,session_id,
                    receipt["replayed"],receipt["prompt_tokens"],
                    receipt["generated_tokens"])
    return {"receipt":receipt,"assurance":proof}

def replay_only(worker,*,session_id,request_id,prompt,seed=0,temperature=0.8):
    session_id=identifier(session_id)
    request_id=identifier(request_id)
    prompt=utf8(prompt,maximum=worker.spine.limits.input_bytes)
    result=worker.spine.replay(session_id,request_id,prompt,
        seed=nonnegative(seed,maximum=2**32-1),
        temperature=number(temperature,minimum=0.000000001,maximum=2))
    if result is None:
        return {"found":False,"generated":False}
    identity=worker.spine.identity
    checked=verify_turn_receipt(result,model_sha256=identity.model_sha256,
                                tokenizer_sha256=identity.tokenizer_sha256)
    if not checked["replayed"]:fail("non-replayed receipt returned by replay-only path")
    return {"found":True,"generated":False,"receipt":checked}
