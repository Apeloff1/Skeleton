"""Authenticated identities for immutable serving receipts (digest, not signatures)."""
from __future__ import annotations
from dataclasses import dataclass
import json
from hashlib import sha256
from .contracts import ModelIdentity,ServingError,required_id,SHA

@dataclass(frozen=True,slots=True)
class Receipt:
    tenant:str
    request_id:str
    model:ModelIdentity
    input_sha256:str
    output_sha256:str
    prompt_tokens:int
    generated_tokens:int
    finish_reason:str
    elapsed_ns:int

    def __post_init__(self):
        required_id(self.tenant,'tenant');required_id(self.request_id,'request')
        if not SHA.fullmatch(self.input_sha256) or not SHA.fullmatch(self.output_sha256):
            raise ServingError('serving content identity absent')
        if (any(type(v) is not int or v<0 for v in (self.prompt_tokens,self.generated_tokens,self.elapsed_ns))
            or not isinstance(self.finish_reason,str) or len(self.finish_reason)>64):
            raise ServingError('serving receipt invalid')

    @property
    def digest(self)->str:
        record={'tenant':self.tenant,'request':self.request_id,'model':self.model.model_sha256,
                'tokenizer':self.model.tokenizer_sha256,'epoch':self.model.epoch,
                'input':self.input_sha256,'output':self.output_sha256,
                'prompt_tokens':self.prompt_tokens,'generated_tokens':self.generated_tokens,
                'finish_reason':self.finish_reason,'elapsed_ns':self.elapsed_ns}
        return sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()
