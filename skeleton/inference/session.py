"""Deterministic provider-neutral inference session receipts for VOL-007."""
from __future__ import annotations
from dataclasses import dataclass, field
from hashlib import sha256
import json, math
from types import MappingProxyType
from typing import Mapping, Any

MAX_ATTEMPTS=8
MAX_EVENTS=4096
class InferenceContractError(ValueError): pass

def _hex(v,n):
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise InferenceContractError(f"invalid {n}")
    return v
def _id(v,n):
    if not isinstance(v,str) or not v or len(v)>256: raise InferenceContractError(f"invalid {n}")
    return v
def _digest(v): return sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

@dataclass(frozen=True)
class InferenceUsage:
    input_tokens:int=0; output_tokens:int=0; attempts:int=1
    def __post_init__(self):
        for n in ("input_tokens","output_tokens","attempts"):
            v=getattr(self,n)
            if not isinstance(v,int) or isinstance(v,bool) or v<0: raise InferenceContractError(f"invalid {n}")
        if self.attempts<1 or self.attempts>MAX_ATTEMPTS: raise InferenceContractError("attempts out of bounds")

@dataclass(frozen=True)
class ModelRequest:
    operation_id:str; request_digest:str; model:str; provider:str; max_output_tokens:int; deadline_ms:int
    def __post_init__(self):
        _id(self.operation_id,"operation_id"); _hex(self.request_digest,"request_digest"); _id(self.model,"model"); _id(self.provider,"provider")
        if not isinstance(self.max_output_tokens,int) or isinstance(self.max_output_tokens,bool) or self.max_output_tokens<=0: raise InferenceContractError("invalid max_output_tokens")
        if not isinstance(self.deadline_ms,int) or isinstance(self.deadline_ms,bool) or self.deadline_ms<=0: raise InferenceContractError("invalid deadline_ms")

@dataclass(frozen=True)
class ModelStreamEvent:
    sequence:int; kind:str; payload_digest:str
    def __post_init__(self):
        if not isinstance(self.sequence,int) or isinstance(self.sequence,bool) or self.sequence<0 or self.sequence>=MAX_EVENTS: raise InferenceContractError("invalid sequence")
        if self.kind not in {"text","structured","tool_call","usage","final","cancelled","error"}: raise InferenceContractError("invalid event kind")
        _hex(self.payload_digest,"payload_digest")

@dataclass(frozen=True)
class ModelResult:
    operation_id:str; request_digest:str; provider:str; model:str; terminal_reason:str; usage:InferenceUsage
    event_chain_digest:str; response_digest:str|None=None; authority_scope:str="inference-result-only"
    def __post_init__(self):
        _id(self.operation_id,"operation_id"); _hex(self.request_digest,"request_digest"); _id(self.provider,"provider"); _id(self.model,"model"); _hex(self.event_chain_digest,"event_chain_digest")
        if self.response_digest is not None:_hex(self.response_digest,"response_digest")
        if self.terminal_reason not in {"completed","cancelled","deadline","provider_error","policy_denied"}: raise InferenceContractError("invalid terminal reason")
        if self.terminal_reason=="completed" and self.response_digest is None: raise InferenceContractError("completed result requires response")
        if self.terminal_reason!="completed" and self.response_digest is not None: raise InferenceContractError("non-completed result cannot publish response")
        if self.authority_scope!="inference-result-only": raise InferenceContractError("inference result cannot grant execution authority")
    @property
    def result_digest(self):
        return _digest({"operation_id":self.operation_id,"request_digest":self.request_digest,"provider":self.provider,"model":self.model,"terminal_reason":self.terminal_reason,"usage":self.usage.__dict__,"event_chain_digest":self.event_chain_digest,"response_digest":self.response_digest,"authority_scope":self.authority_scope})

class InferenceSession:
    def __init__(self,request:ModelRequest):
        if not isinstance(request,ModelRequest): raise InferenceContractError("ModelRequest required")
        self.request=request; self._events=[]; self._terminal=None
    @property
    def event_chain_digest(self):
        chain=_digest({"request":self.request.request_digest,"chain":"genesis"})
        for e in self._events: chain=_digest({"prior":chain,"sequence":e.sequence,"kind":e.kind,"payload":e.payload_digest})
        return chain
    def record(self,event:ModelStreamEvent):
        if self._terminal is not None: raise InferenceContractError("session terminal")
        if not isinstance(event,ModelStreamEvent) or event.sequence!=len(self._events): raise InferenceContractError("non-contiguous event")
        if len(self._events)>=MAX_EVENTS: raise InferenceContractError("event budget exceeded")
        self._events.append(event)
        if event.kind in {"final","cancelled","error"}: self._terminal=event.kind
        return self.event_chain_digest
    def finish(self,*,reason:str,usage:InferenceUsage,response_digest:str|None=None):
        if self._terminal is None: raise InferenceContractError("terminal stream event required")
        expected={"final":"completed","cancelled":"cancelled","error":"provider_error"}[self._terminal]
        if reason!=expected and not (self._terminal=="error" and reason in {"deadline","policy_denied"}): raise InferenceContractError("terminal reason mismatch")
        return ModelResult(self.request.operation_id,self.request.request_digest,self.request.provider,self.request.model,reason,usage,self.event_chain_digest,response_digest)
