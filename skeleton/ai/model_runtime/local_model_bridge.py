"""Local-model bridge contracts plus the executable native LLM boundary."""
from __future__ import annotations

from hashlib import sha256

from .flgb_model_runtime import LocalModelReceipt, LocalModelRequest, ModelRuntimeError
from .native_llm_runtime import GenerationResult, NativeLLMRuntime
from .runtime_service import (
    CancellationToken,
    NativeModelService,
    NativeServiceError,
    NativeServiceResult,
)
from .runtime_contracts import (
    DevicePolicy,
    GenerationConfig,
    ReplayReceipt,
    RuntimeContractError,
    RuntimeLimits,
)


def execute_local_request(
    runtime: NativeLLMRuntime,
    request: LocalModelRequest,
    prompt: str,
    config: GenerationConfig | None = None,
) -> tuple[GenerationResult, LocalModelReceipt]:
    """Execute one inference-only bridge request against the admitted native model.

    The control-plane request is bound to the runtime's canonical ModelIdentity
    and to the exact UTF-8 prompt digest. The function never widens authority;
    LocalModelRequest enforces inference-only and this bridge returns receipts
    rather than performing external side effects.
    """
    if not isinstance(runtime, NativeLLMRuntime):
        raise RuntimeContractError("NativeLLMRuntime required")
    if not isinstance(request, LocalModelRequest):
        raise RuntimeContractError("LocalModelRequest required")
    if not isinstance(prompt, str):
        raise RuntimeContractError("prompt must be a string")

    identity = runtime.model_identity.identity_digest
    if request.model_identity_digest != identity:
        raise RuntimeContractError("local-model request identity mismatch")

    input_digest = sha256(prompt.encode("utf-8")).hexdigest()
    if request.input_digest != input_digest:
        raise RuntimeContractError("local-model request input digest mismatch")

    cfg = config or GenerationConfig(
        max_new_tokens=min(request.max_output_tokens, runtime.limits.max_new_tokens)
    )
    if not isinstance(cfg, GenerationConfig):
        raise RuntimeContractError("GenerationConfig required")
    if cfg.max_new_tokens > request.max_output_tokens:
        raise RuntimeContractError("generation exceeds local-model output budget")

    result = runtime.generate(prompt, cfg)
    receipt = LocalModelReceipt(
        operation_id=request.operation_id,
        model_identity_digest=identity,
        terminal_reason="completed",
        output_digest=result.output_digest,
        usage_digest=result.usage.digest,
    )
    return result, receipt


__all__ = [
    "DevicePolicy",
    "NativeServiceResult",
    "NativeServiceError",
    "NativeModelService",
    "CancellationToken",
    "GenerationConfig",
    "GenerationResult",
    "LocalModelReceipt",
    "LocalModelRequest",
    "ModelRuntimeError",
    "NativeLLMRuntime",
    "ReplayReceipt",
    "RuntimeContractError",
    "RuntimeLimits",
    "execute_local_request",
]
