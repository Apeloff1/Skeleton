"""Actor-model-session-bound idempotent request fingerprint."""
from __future__ import annotations
from .contracts import identifier,utf8,number,nonnegative,digest,identity_hash

def fingerprint(*,tenant,subject,model_sha256,tokenizer_sha256,
                session_id,request_id,prompt,seed=0,temperature=0.8):
    return digest({
        "schema":"laptop-runtime-request.v1",
        "tenant":identifier(tenant,"tenant"),
        "subject":identifier(subject,"subject"),
        "model_sha256":identity_hash(model_sha256),
        "tokenizer_sha256":identity_hash(tokenizer_sha256),
        "session_id":identifier(session_id),"request_id":identifier(request_id),
        "prompt":utf8(prompt),"seed":nonnegative(seed,maximum=2**32-1),
        "temperature":number(temperature,minimum=0.000000001,maximum=2)})
