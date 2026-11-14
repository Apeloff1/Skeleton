"""Concrete adapter into Skeleton's existing executable native transformer.

Generation is never synthesized here. A live NativeChatEngine is required;
no hosted inference or mock fallback is provided in production.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING,Any
from ..authority.canonical import ContractViolation,require_small_text,require_digest,sha256

if TYPE_CHECKING:
    from skeleton.ai.model_runtime.chat_engine import NativeChatEngine


@dataclass(frozen=True, slots=True)
class Generated:
    text: str
    prompt_tokens: int
    generated_tokens: int
    output_digest: str
    model_digest: str
    tokenizer_digest: str
    finish_reason: str

    def __post_init__(self)->None:
        require_small_text(self.text,field="generated answer",maximum=262144)
        for key in ("output_digest","model_digest","tokenizer_digest"):
            require_digest(getattr(self,key),field=key)
        for key in ("prompt_tokens","generated_tokens"):
            if type(getattr(self,key)) is not int or getattr(self,key)<0:
                raise ContractViolation("invalid generation usage")
        if type(self.finish_reason) is not str or not 1<=len(self.finish_reason)<=64 or not self.finish_reason.isascii():
            raise ContractViolation("unrecognized generation finish reason")


class NativeBackend:
    """The native runtime and its tokenizer remain authoritative."""
    def __init__(self,engine:"NativeChatEngine"):
        from skeleton.ai.model_runtime.chat_engine import NativeChatEngine
        if not isinstance(engine,NativeChatEngine):
            raise ContractViolation("native model engine required")
        self.engine=engine

    @property
    def model_digest(self)->str:
        return self.engine.runtime.model_digest

    @property
    def tokenizer_digest(self)->str:
        return self.engine.runtime.tokenizer.digest

    def generate(self,messages:list[dict[str,str]],*,max_output_tokens:int=128,
                 seed:int=0,temperature:float=1.0)->Generated:
        from skeleton.ai.model_runtime.chat_protocol import ChatTranscript
        from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig
        from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError
        try:
            transcript=ChatTranscript.parse(messages)
            config=GenerationConfig(max_new_tokens=max_output_tokens,
                                    seed=seed,temperature=temperature)
            result=self.engine.generate(transcript,config)
            generation=result.generation
            text=generation.text
            # The lower native replay receipt binds token IDs, text and stop
            # reason; the operational gateway and SQLite journal instead bind
            # the exact UTF-8 answer bytes. Verify the lower receipt before
            # translating those distinct digest contracts.
            from skeleton.ai.model_runtime.flgb_model_runtime import digest_json
            native_receipt_digest = digest_json({
                "generated_ids": list(generation.generated_ids),
                "text": text,
                "finish_reason": generation.finish_reason,
            })
            if generation.output_digest != native_receipt_digest:
                raise ContractViolation("native token/text replay receipt mismatch")
            return Generated(text=text,prompt_tokens=result.prompt_tokens,
                             generated_tokens=len(generation.generated_ids),
                             output_digest=sha256(text.encode("utf-8")),
                             model_digest=self.model_digest,
                             tokenizer_digest=self.tokenizer_digest,
                             finish_reason=generation.finish_reason)
        except RuntimeContractError as exc:
            raise ContractViolation(f"native model rejected operation: {exc}") from exc


def from_checkpoint(catalog:"Any",model_name:str)->NativeBackend:
    """Activate exactly the verified, bounded local bytes, with no path re-open."""
    from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
    from skeleton.ai.model_runtime.chat_engine import NativeChatEngine
    artifact,raw=catalog.verified_bytes(model_name)
    # Existing checkpoint parser verifies model architecture, weights,
    # tokenizer and checksum. Data remains bound to the held input bytes.
    backend=NativeBackend(NativeChatEngine(NativeLLMRuntime.restore_json(raw)))
    if (artifact.tokenizer_sha256 is not None and
        artifact.tokenizer_sha256!=backend.tokenizer_digest):
        raise ContractViolation("tokenizer identity changed on activation")
    return backend
