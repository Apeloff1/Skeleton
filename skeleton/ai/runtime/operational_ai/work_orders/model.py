"""Immutable model/tenant/request binding, prompt digest only, never prompt text."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import identifier,digest_id,uint,temperature,prompt,hash_bytes,fingerprint,refuse

@dataclass(frozen=True,slots=True)
class WorkOrder:
    job_id:str
    tenant:str
    subject:str
    model_sha256:str
    tokenizer_sha256:str
    session_id:str
    request_id:str
    prompt_sha256:str
    seed:int=0
    sampler_temperature:float=0.8
    max_output_tokens:int=256

    def __post_init__(self):
        for f in ("job_id","tenant","subject","session_id","request_id"):
            identifier(getattr(self,f),f)
        for f in ("model_sha256","tokenizer_sha256","prompt_sha256"):
            digest_id(getattr(self,f))
        uint(self.seed,maximum=2**32-1)
        temperature(self.sampler_temperature)
        uint(self.max_output_tokens,maximum=8192)
        if self.max_output_tokens<1:refuse("zero output tokens")
    @classmethod
    def bind(cls,*,job_id,tenant,subject,model_sha256,tokenizer_sha256,
             session_id,request_id,prompt_text,seed=0,
             sampler_temperature=0.8,max_output_tokens=256):
        sha=hash_bytes(prompt(prompt_text).encode("utf-8"))
        return cls(job_id,tenant,subject,model_sha256,tokenizer_sha256,
                   session_id,request_id,sha,seed,temperature(sampler_temperature),
                   max_output_tokens)
    def record(self):
        return {"schema":"offline-ai-work-order.v2",**{
            name:getattr(self,name) for name in self.__dataclass_fields__}}
    def request_sha256(self):
        return fingerprint(self.record())
    def confirm_prompt(self,value):
        if hash_bytes(prompt(value).encode("utf-8"))!=self.prompt_sha256:
            refuse("prompt differs from queued byte identity")
        return value
    def confirm_worker(self,worker):
        try:active=worker.spine.identity;limits=worker.spine.limits;backend=worker.spine.backend
        except AttributeError:refuse("canonical supervised AI required")
        if (active.tenant!=self.tenant or active.subject!=self.subject
            or active.model_sha256!=self.model_sha256
            or active.tokenizer_sha256!=self.tokenizer_sha256
            or backend.model_digest!=self.model_sha256
            or backend.tokenizer_digest!=self.tokenizer_sha256):
            refuse("operator/tenant/model/tokenizer not bound to active GGUF")
        if self.max_output_tokens>limits.max_output_tokens:
            refuse("model output request exceeds native worker ceiling")
        return True
