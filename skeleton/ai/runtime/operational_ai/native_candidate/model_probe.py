"""Read-only native model identity snapshot before allocating gradients."""
from __future__ import annotations
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from .strict import sha
from .errors import deny


def inspect_native(runtime: NativeLLMRuntime, *, model_sha256: str,
                   tokenizer_sha256: str) -> dict:
    sha(model_sha256, "model")
    sha(tokenizer_sha256, "tokenizer")
    if type(runtime) is not NativeLLMRuntime:
        deny("probe-real-native-required")
    runtime.assert_model_unchanged()
    if runtime.model_digest != model_sha256 or runtime.tokenizer.digest != tokenizer_sha256:
        deny("probe-model-mismatch")
    return {
        "schema": "skeleton.native-candidate.native-probe.v1",
        "model_sha256": runtime.model_digest,
        "tokenizer_sha256": runtime.tokenizer.digest,
        "logical_model_bytes": runtime.model_bytes,
        "context_limit": runtime.limits.max_context,
        "native_checkpoint_available": True,
        "gradient_run_complete": False,
        "model_quality_certified": False,
    }
