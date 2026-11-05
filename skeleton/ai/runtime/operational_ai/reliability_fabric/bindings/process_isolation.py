"""Bind process_isolation input evidence to actual caller/model identity."""
from __future__ import annotations
from ..contracts import fail
from ..engine import validate

def inspect(record,*,tenant,subject,model_sha256):
    if type(record) is not dict:fail("expected operator evidence record")
    identity=record.get("identity")
    if type(identity) is not dict:fail("missing subject identity")
    if (identity.get("tenant")!=tenant or identity.get("subject")!=subject
        or identity.get("model_sha256")!=model_sha256):
        fail("evidence not bound to active caller and pinned model")
    return validate("process_isolation",record)
