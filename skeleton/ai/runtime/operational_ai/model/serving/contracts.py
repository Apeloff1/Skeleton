"""Native-serving contracts with strict request and receipt boundaries."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import math
import re

ID=re.compile(r"^[A-Za-z0-9_-]{1,96}$")
SHA=re.compile(r"^[0-9a-f]{64}$")

class ServingError(RuntimeError):
    pass


def required_id(value:str,name:str)->str:
    if not isinstance(value,str) or not ID.fullmatch(value):
        raise ServingError(f"invalid {name} identifier")
    return value


def hash_bytes(data:bytes)->str:
    return sha256(data).hexdigest()

@dataclass(frozen=True,slots=True)
class ModelIdentity:
    model_sha256:str
    tokenizer_sha256:str
    epoch:int

    def __post_init__(self):
        if not SHA.fullmatch(self.model_sha256) or not SHA.fullmatch(self.tokenizer_sha256):
            raise ServingError("model and tokenizer must be SHA-256 pinned")
        if type(self.epoch) is not int or not 0<=self.epoch<2**63:
            raise ServingError("invalid model epoch")

@dataclass(frozen=True,slots=True)
class Request:
    tenant:str
    request_id:str
    messages:tuple[tuple[str,str],...]
    max_tokens:int
    seed:int
    temperature:float
    deadline_ns:int

    def __post_init__(self):
        required_id(self.tenant,'tenant');required_id(self.request_id,'request')
        if (not self.messages or len(self.messages)>512 or
            any(role not in ('system','user','assistant') or not isinstance(text,str)
                or len(text.encode('utf8'))>65536 for role,text in self.messages)):
            raise ServingError("invalid bounded messages")
        if sum(len(t.encode('utf8')) for _,t in self.messages)>262144:
            raise ServingError("request context too large")
        if type(self.max_tokens) is not int or not 1<=self.max_tokens<=4096:
            raise ServingError("invalid requested output tokens")
        if type(self.seed) is not int or not 0<=self.seed<2**32:
            raise ServingError("invalid seed")
        if type(self.temperature) not in (int,float) or not math.isfinite(self.temperature) or not 0<self.temperature<=2:
            raise ServingError("invalid sampling temperature")
        if type(self.deadline_ns) is not int or self.deadline_ns<=0:
            raise ServingError("invalid deadline")

    def to_messages(self)->list[dict[str,str]]:
        return [{'role':role,'content':text} for role,text in self.messages]
