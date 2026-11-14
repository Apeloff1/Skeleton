"""Model identity verification after restoring private trusted checkpoint bytes."""
from __future__ import annotations
from pathlib import Path
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from .artifact_store import read
from .canonical import require_sha
from .errors import reject


def restore(
    directory:Path,checkpoint_sha256:str,*,expected_model_sha256:str,
    expected_tokenizer_sha256:str,
)->NativeLLMRuntime:
    for label,value in (("model",expected_model_sha256),
                        ("tokenizer",expected_tokenizer_sha256)):
        require_sha(value,label)
    raw=read(directory,checkpoint_sha256)
    runtime=NativeLLMRuntime.restore_json(raw.decode("utf-8"))
    if runtime.model_digest!=expected_model_sha256:
        reject("checkpoint-model-identity")
    if runtime.tokenizer.digest!=expected_tokenizer_sha256:
        reject("checkpoint-tokenizer-identity")
    runtime.assert_model_unchanged()
    return runtime
