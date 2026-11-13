"""Canonical typed boundary for the independently verifiable execution spine."""
from __future__ import annotations
from dataclasses import dataclass, field
from hashlib import sha256
import json, math, re
from typing import Any

_TOKEN=re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SHA=re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_ROLES={"system","developer","user","assistant"}

class SpineError(RuntimeError):
    """Fail-closed boundary or custody violation."""

class Busy(SpineError): pass
class Conflict(SpineError): pass
class IntegrityFailure(SpineError): pass
class Cancelled(SpineError): pass


def identifier(value: str, label: str = "identifier") -> str:
    if not isinstance(value,str) or not _TOKEN.fullmatch(value):
        raise SpineError(f"invalid {label}")
    return value

def hexdigest(value:str,label:str="digest") -> str:
    if not isinstance(value,str) or not _SHA.fullmatch(value):
        raise SpineError(f"invalid {label}")
    return value

def canonical(value:Any,*,ceiling:int=1_048_576)->bytes:
    if type(ceiling) is not int or not 1<=ceiling<=16_777_216:
        raise SpineError("invalid canonicalization ceiling")
    try:
        raw=json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
    except (TypeError,ValueError,UnicodeError,OverflowError,RecursionError) as exc:
        raise SpineError("value is not canonically serializable") from exc
    if len(raw)>ceiling: raise SpineError("canonical value exceeds budget")
    return raw

def digest(value:Any)->str: return sha256(canonical(value)).hexdigest()

@dataclass(frozen=True, slots=True)
class Identity:
    tenant:str
    subject:str
    model_sha256:str
    tokenizer_sha256:str
    def __post_init__(self):
        identifier(self.tenant,'tenant'); identifier(self.subject,'subject')
        hexdigest(self.model_sha256,'model');hexdigest(self.tokenizer_sha256,'tokenizer')
    def as_dict(self): return {"tenant":self.tenant,"subject":self.subject,
        "model_sha256":self.model_sha256,"tokenizer_sha256":self.tokenizer_sha256}
    def key(self)->str:return digest(self.as_dict())

@dataclass(frozen=True, slots=True)
class SpineLimits:
    input_bytes:int=32768
    response_bytes:int=131072
    max_output_tokens:int=512
    context_tokens:int=4096
    deadline_ms:int=120_000
    max_pending:int=512
    max_history:int=128
    max_sources:int=6
    def __post_init__(self):
        specs={"input_bytes":(1,1_048_576),"response_bytes":(1,2_097_152),
            "max_output_tokens":(1,8192),"context_tokens":(64,131072),
            "deadline_ms":(10,600_000),"max_pending":(1,4096),
            "max_history":(1,4096),"max_sources":(0,32)}
        for name,(lo,hi) in specs.items():
            v=getattr(self,name)
            if type(v) is not int or not lo<=v<=hi: raise SpineError(f"invalid {name}")
        if self.max_output_tokens >=self.context_tokens: raise SpineError('output exceeds context ceiling')

@dataclass(frozen=True,slots=True)
class InferenceRequest:
    identity:Identity
    session:str
    request_id:str
    prompt:str
    seed:int=0
    temperature:float=0.8
    def __post_init__(self):
        if not isinstance(self.identity,Identity):raise SpineError('identity required')
        identifier(self.session,'session');identifier(self.request_id,'request')
        if not isinstance(self.prompt,str) or not self.prompt.strip():raise SpineError('nonempty user prompt required')
        if type(self.seed) is not int or not 0<=self.seed<2**32:raise SpineError('invalid seed')
        if type(self.temperature) not in (int,float) or not math.isfinite(self.temperature) or not 0<self.temperature<=2: raise SpineError('invalid temperature')
        if len(self.prompt.encode('utf8'))>1_048_576:raise SpineError('prompt hard ceiling')
    def bound_digest(self)->str:
        return digest({"schema":"spine.request.v1","identity":self.identity.as_dict(),
            "session":self.session,"prompt":self.prompt,"seed":self.seed,"temperature":float(self.temperature)})

@dataclass(frozen=True,slots=True)
class GenerationReceipt:
    text:str
    model_sha256:str
    tokenizer_sha256:str
    prompt_tokens:int
    generated_tokens:int
    finish_reason:str
    def __post_init__(self):
        if not isinstance(self.text,str) or not self.text.strip():raise SpineError('empty generation not accepted')
        hexdigest(self.model_sha256,'output model');hexdigest(self.tokenizer_sha256,'output tokenizer')
        for name in ('prompt_tokens','generated_tokens'):
            if type(getattr(self,name)) is not int or getattr(self,name)<0: raise SpineError(f'invalid {name}')
        if self.finish_reason not in ('stop','length','eos'):raise SpineError('unsupported finish reason')
    def output_digest(self):return sha256(self.text.encode('utf8')).hexdigest()
