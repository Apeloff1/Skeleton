"""Mandatory consistency between requested caller, active service and proof."""
from __future__ import annotations
from .identity import ActiveModel
from .contracts import identifier,identity_hash,refuse

def enforce(worker,*,tenant,subject,model_sha256,tokenizer_sha256):
    active=ActiveModel.from_supervisor(worker)
    if active.tenant!=identifier(tenant) or active.subject!=identifier(subject):
        refuse("cross-principal local model request")
    if (active.model_sha256!=identity_hash(model_sha256) or
        active.tokenizer_sha256!=identity_hash(tokenizer_sha256)):
        refuse("model epoch or tokenizer mismatch")
    return {"scope_bound":True,"active":active.to_record()}
