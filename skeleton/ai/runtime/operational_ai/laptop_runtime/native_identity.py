"""Real activated backend identity vs operator-approved artifact identity."""
from __future__ import annotations
from .contracts import identity_hash,refuse

def verify(backend,approved_model_sha256,expected_tokenizer_sha256):
    model=identity_hash(approved_model_sha256)
    tokenizer=identity_hash(expected_tokenizer_sha256)
    if not hasattr(backend,"generate") or not callable(backend.generate):
        refuse("real native generation port unavailable")
    if getattr(backend,"model_digest",None)!=model:
        refuse("runtime model hash differs from approved source")
    if getattr(backend,"tokenizer_digest",None)!=tokenizer:
        refuse("runtime tokenizer identity differs from activation")
    return {"status":"live-backend-identity-pinned",
            "model_sha256":model,"tokenizer_sha256":tokenizer,
            "native_generation_proved":False}
