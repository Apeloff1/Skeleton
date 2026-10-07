"""End-to-end evidence-to-generation spine for verified crawler context.

This is deliberately a composition boundary: crawler governance, FLGB-03
retrieval/context, and FLGB-02 native inference retain their own authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac

from skeleton.ai.model_runtime.native_llm_runtime import GenerationResult, NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig, RuntimeContractError

from .context_bridge import CrawlContextBundle


class EvidenceGenerationError(RuntimeContractError):
    pass


@dataclass(frozen=True)
class EvidenceGenerationReceipt:
    context_source_digest: str
    context_text_digest: str
    model_identity_digest: str
    prompt_sequence_digest: str
    runtime_request_digest: str
    output_digest: str
    replay_receipt_digest: str

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if not isinstance(value, str) or len(value) != 64 or any(
                ch not in "0123456789abcdef" for ch in value
            ):
                raise EvidenceGenerationError(f"invalid {name}")


@dataclass(frozen=True)
class EvidenceGenerationResult:
    receipt: EvidenceGenerationReceipt
    generation: GenerationResult

    def __post_init__(self) -> None:
        if not hmac.compare_digest(self.receipt.output_digest, self.generation.output_digest):
            raise EvidenceGenerationError("generation output receipt mismatch")
        if not hmac.compare_digest(
            self.receipt.prompt_sequence_digest, self.generation.prompt_sequence.digest
        ):
            raise EvidenceGenerationError("generation prompt receipt mismatch")
        if not hmac.compare_digest(
            self.receipt.replay_receipt_digest, self.generation.replay_receipt.digest
        ):
            raise EvidenceGenerationError("generation replay receipt mismatch")


def generate_from_crawl_context(
    runtime: NativeLLMRuntime,
    bundle: CrawlContextBundle,
    config: GenerationConfig,
) -> EvidenceGenerationResult:
    if not isinstance(runtime, NativeLLMRuntime):
        raise EvidenceGenerationError("NativeLLMRuntime required")
    if not isinstance(bundle, CrawlContextBundle):
        raise EvidenceGenerationError("CrawlContextBundle required")
    if not isinstance(config, GenerationConfig):
        raise EvidenceGenerationError("GenerationConfig required")
    observed_text = sha256(bundle.text.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(observed_text, bundle.text_digest):
        raise EvidenceGenerationError("crawl context text mutated before inference")

    generation = runtime.generate(bundle.text, config)
    replay = generation.replay_receipt
    if not hmac.compare_digest(replay.model_digest, runtime.model_digest):
        raise EvidenceGenerationError("runtime model identity drift")
    if not hmac.compare_digest(replay.tokenizer_digest, runtime.tokenizer.digest):
        raise EvidenceGenerationError("runtime tokenizer identity drift")

    receipt = EvidenceGenerationReceipt(
        context_source_digest=bundle.compiled.source_digest,
        context_text_digest=bundle.text_digest,
        model_identity_digest=runtime.model_identity.identity_digest,
        prompt_sequence_digest=generation.prompt_sequence.digest,
        runtime_request_digest=replay.request_digest,
        output_digest=generation.output_digest,
        replay_receipt_digest=replay.digest,
    )
    return EvidenceGenerationResult(receipt, generation)


__all__ = [
    "EvidenceGenerationError",
    "EvidenceGenerationReceipt",
    "EvidenceGenerationResult",
    "generate_from_crawl_context",
]
