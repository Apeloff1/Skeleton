from __future__ import annotations
import pytest
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.runtime_contracts import GenerationConfig,RuntimeContractError
from skeleton.cortex.transformer import TinyTransformer

def _runtime() -> NativeLLMRuntime:
    model=TinyTransformer(vocab=["<unk>","hello","world"],dim=8,ctx=16,n_heads=1,n_layers=1)
    return NativeLLMRuntime(model)

def test_tokenizer_failure_is_runtime_admission_failure() -> None:
    runtime=_runtime()
    with pytest.raises(RuntimeContractError):
        tuple(runtime.stream(123,GenerationConfig(max_new_tokens=1)))  # type: ignore[arg-type]

def test_tokenizer_identity_is_bound_into_generation_receipt() -> None:
    runtime=_runtime()
    stream=runtime.stream("hello",GenerationConfig(max_new_tokens=1,seed=7))
    tuple(stream)
    assert stream.result is not None
    assert stream.result.replay_receipt.tokenizer_digest==runtime.tokenizer.digest
    assert stream.result.prompt_sequence.tokenizer_digest==runtime.tokenizer.digest
