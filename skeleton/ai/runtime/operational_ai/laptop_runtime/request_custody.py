"""Strict ingress request record: scope and native parameters committed by caller."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import identifier,identity_hash,utf8,nonnegative,number,digest

@dataclass(frozen=True,slots=True)
class RequestCustody:
    tenant:str
    subject:str
    model_sha256:str
    tokenizer_sha256:str
    session_id:str
    request_id:str
    prompt:str
    seed:int=0
    temperature:float=0.8
    def __post_init__(self):
        for item in (self.tenant,self.subject,self.session_id,self.request_id):
            identifier(item)
        for item in (self.model_sha256,self.tokenizer_sha256):
            identity_hash(item)
        utf8(self.prompt)
        nonnegative(self.seed,maximum=2**32-1)
        number(self.temperature,minimum=0.000000001,maximum=2)
    def sha256(self):
        return digest({"schema":"laptop-request-custody.v1",
            **{field:getattr(self,field) for field in self.__dataclass_fields__}})
