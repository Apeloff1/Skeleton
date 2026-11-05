"""Verify finite native model weights and authoritative source identity."""
from __future__ import annotations
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from .canonical import require_sha
from .errors import reject


def inspect(runtime:NativeLLMRuntime,*,expected_model_sha256:str,
            expected_tokenizer_sha256:str)->dict:
    require_sha(expected_model_sha256,"model")
    require_sha(expected_tokenizer_sha256,"tokenizer")
    if type(runtime) is not NativeLLMRuntime:
        reject("model-health-native")
    runtime.assert_model_unchanged()
    if runtime.model_digest!=expected_model_sha256:
        reject("model-health-digest")
    if runtime.tokenizer.digest!=expected_tokenizer_sha256:
        reject("model-health-tokenizer")
    health=runtime.model.validate_finite_weights()
    if health.get("healthy") is not True or health.get("nonfinite_count")!=0:
        reject("model-health-nonfinite")
    return {
        "schema":"skeleton.native-supervised.model-health.v1",
        "model_sha256":runtime.model_digest,
        "tokenizer_sha256":runtime.tokenizer.digest,
        "parameters_checked":health["checked_parameters"],
        "finite":True,
        "full_quality_qualified":False,
        "serving_authorized":False,
    }
