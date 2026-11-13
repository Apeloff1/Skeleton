"""Caller/model-bound admission adapter for context_packing; no external side effects."""
from __future__ import annotations
from ..engine import validate
from ..contracts import fail

def inspect(record,*,tenant,subject,model_sha256):
    if type(record) is not dict:fail("bounded operator record required")
    identity=record.get("identity")
    if type(identity) is not dict:fail("missing identity")
    if (identity.get("tenant")!=tenant or identity.get("subject")!=subject
        or identity.get("model_sha256")!=model_sha256):
        fail("caller or model epoch differs from trusted source")
    return validate("context_packing",record)
