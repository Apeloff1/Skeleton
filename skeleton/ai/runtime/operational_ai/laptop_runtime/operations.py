"""Closed operation registry and byte ceilings for the real local AI API."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import refuse

@dataclass(frozen=True,slots=True)
class Operation:
    name:str
    required:tuple[str,...]
    optional:tuple[str,...]=()
    mutates:bool=False
    native_inference:bool=False
    max_request_bytes:int=65536

_ALLOWED=(
    Operation("create",(),(),True),
    Operation("turn",("session_id","request_id","prompt"),("seed","temperature"),True,True),
    Operation("history",("session_id",)),
    Operation("replay",("session_id","request_id","prompt"),("seed","temperature")),
    Operation("close",("session_id",),(),True),
    Operation("status",()),
    Operation("doctor",()),
    Operation("identity",()),
    Operation("outbox_pending",(),("limit",)),
    Operation("outbox_ack",("event_key","event_sha256"),(),True),
)
_BY_NAME={op.name:op for op in _ALLOWED}
assert len(_BY_NAME)==len(_ALLOWED)

def operations():
    return tuple(op.name for op in _ALLOWED)

def get(name):
    if type(name) is not str or name not in _BY_NAME:
        refuse("unknown or unapproved AI operation")
    return _BY_NAME[name]

def shape(name,payload):
    from .contracts import exact
    op=get(name)
    exact(payload,op.required,op.optional)
    return op

def schema():
    return {"schema":"skeleton.operational-ai.laptop-api.v1",
            "transport":"bearer-loopback-only",
            "model":"real-local-native-gguf",
            "memory_authority":"not-in-API",
            "tool_authority":"never-from-model-output",
            "operations":{op.name:{
                "required":list(op.required),"optional":list(op.optional),
                "mutates":op.mutates,"may_generate":op.native_inference}
                for op in _ALLOWED}}
