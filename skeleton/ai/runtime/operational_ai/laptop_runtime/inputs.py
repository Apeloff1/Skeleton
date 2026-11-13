"""Per-operation typed input validation before calling the actual ExecutionSpine."""
from __future__ import annotations
from .contracts import exact,utf8,identifier,number,nonnegative,identity_hash,refuse
from .operations import shape

def normalize(operation,payload,limits):
    shape(operation,payload)
    obj=dict(payload)
    if "session_id" in obj:
        obj["session_id"]=identifier(obj["session_id"],"session ID")
    if "request_id" in obj:
        obj["request_id"]=identifier(obj["request_id"],"request ID")
    if "prompt" in obj:
        obj["prompt"]=utf8(obj["prompt"],maximum=limits.input_bytes)
    if "system" in obj:
        obj["system"]=utf8(obj["system"],maximum=8192)
    if "seed" in obj:
        obj["seed"]=nonnegative(obj["seed"],maximum=2**32-1)
    if "temperature" in obj:
        obj["temperature"]=number(obj["temperature"],minimum=0.000000001,maximum=2)
    if "limit" in obj:
        obj["limit"]=nonnegative(obj["limit"],maximum=32)
        if obj["limit"]==0:refuse("zero result limit denied")
    if "event_key" in obj:
        obj["event_key"]=identifier(obj["event_key"],"outbox key")
    if "event_sha256" in obj:
        obj["event_sha256"]=identity_hash(obj["event_sha256"])
    return obj
