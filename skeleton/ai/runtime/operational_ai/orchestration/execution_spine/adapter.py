"""Use the existing real NativeBackend or GGUFBackend without mock fallback."""
from __future__ import annotations
from typing import Protocol
from .contracts import Identity,GenerationReceipt,SpineLimits,Conflict,SpineError

class RealBackend(Protocol):
    @property
    def model_digest(self)->str:...
    @property
    def tokenizer_digest(self)->str:...
    def generate(self,messages:list[dict[str,str]],*,max_output_tokens:int,
                 seed:int,temperature:float):...

def generate(backend:RealBackend, identity:Identity, messages:tuple[dict,...],
             limits:SpineLimits,*,seed:int,temperature:float)->GenerationReceipt:
    if (backend.model_digest!=identity.model_sha256 or
        backend.tokenizer_digest!=identity.tokenizer_sha256):
        raise Conflict('pinned runtime is different model/tokenizer')
    raw=backend.generate(list(messages),max_output_tokens=limits.max_output_tokens,
                         seed=seed,temperature=temperature)
    # Do not accept string responses, dictionaries, synthetic token accounting
    # or a model-selected tool invocation in lieu of a native receipt.
    from skeleton.ai.runtime.operational_ai.model.native import Generated
    if not isinstance(raw,Generated):raise SpineError('a verifiable native Generation receipt is required')
    if raw.output_digest!=raw_output_hash(raw.text):raise Conflict('native output digest does not match text')
    return GenerationReceipt(text=raw.text,model_sha256=raw.model_digest,
        tokenizer_sha256=raw.tokenizer_digest,prompt_tokens=raw.prompt_tokens,
        generated_tokens=raw.generated_tokens,finish_reason=raw.finish_reason)

def raw_output_hash(text:str)->str:
    from hashlib import sha256
    return sha256(text.encode('utf8')).hexdigest()
