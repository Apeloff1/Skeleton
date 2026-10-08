"""Provider-neutral FLGB-02 model-runtime and native execution contracts."""
from .flgb_model_runtime import (
    ALLOWED_TRANSITIONS,
    BatchRequest,
    DeviceDescriptor,
    KVCacheEntry,
    LocalModelReceipt,
    LocalModelRequest,
    ModelIdentity,
    ModelLifecycle,
    ModelRegistry,
    ModelRuntimeError,
    Placement,
    QuantizationProfile,
    Replica,
    SpeculativeReceipt,
    TokenSequence,
    VocabularyManifest,
    WeightLoadPlan,
    WeightShard,
    plan_continuous_batches,
    plan_device_placement,
    plan_kv_admission,
    route_request,
)
from .runtime_contracts import (
    BatchGenerationRequest,
    DevicePolicy,
    DeviceReceipt,
    GenerationConfig,
    ReplayMismatch,
    ReplayReceipt,
    RuntimeArchitecture,
    RuntimeContractError,
    RuntimeEvent,
    RuntimeLimits,
    RuntimeUsage,
)

# Delay optional native transformer / Cortex imports until explicitly requested.
# Contract-only modules must load under the standard-library-only CI lane.
from importlib import import_module

_LAZY_EXPORTS = {
    "BatchGenerationResult": ".native_llm_runtime",
    "GenerationResult": ".native_llm_runtime",
    "GenerationStream": ".native_llm_runtime",
    "NativeLLMRuntime": ".native_llm_runtime",
    "CancellationToken": ".runtime_service",
    "NativeModelService": ".runtime_service",
    "NativeServiceError": ".runtime_service",
    "NativeServiceResult": ".runtime_service",
    "NativeTokenizer": ".tokenization",
    "StreamingTextFeed": ".tokenization",
    "TokenBatch": ".tokenization",
    "TokenWindow": ".tokenization",
    "TokenizerContractError": ".tokenization",
    "TokenizerLimits": ".tokenization",
    "batch_token_windows": ".tokenization",
    "deserialize_token_sequence": ".tokenization",
    "iter_context_windows": ".tokenization",
    "serialize_token_sequence": ".tokenization",
    "validate_model_snapshot": ".runtime_checkpoint",
}


def __getattr__(name: str):
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))

__all__ = [
    "ALLOWED_TRANSITIONS",
    "BatchGenerationRequest",
    "BatchGenerationResult",
    "CancellationToken",
    "BatchRequest",
    "DeviceDescriptor",
    "DevicePolicy",
    "DeviceReceipt",
    "GenerationConfig",
    "GenerationResult",
    "GenerationStream",
    "KVCacheEntry",
    "LocalModelReceipt",
    "LocalModelRequest",
    "ModelIdentity",
    "ModelLifecycle",
    "ModelRegistry",
    "ModelRuntimeError",
    "NativeLLMRuntime",
    "NativeModelService",
    "NativeServiceError",
    "NativeServiceResult",
    "NativeTokenizer",
    "Placement",
    "QuantizationProfile",
    "ReplayMismatch",
    "ReplayReceipt",
    "Replica",
    "RuntimeArchitecture",
    "RuntimeContractError",
    "RuntimeEvent",
    "RuntimeLimits",
    "RuntimeUsage",
    "SpeculativeReceipt",
    "StreamingTextFeed",
    "TokenBatch",
    "TokenSequence",
    "TokenWindow",
    "TokenizerContractError",
    "TokenizerLimits",
    "VocabularyManifest",
    "WeightLoadPlan",
    "WeightShard",
    "batch_token_windows",
    "deserialize_token_sequence",
    "iter_context_windows",
    "plan_continuous_batches",
    "plan_device_placement",
    "plan_kv_admission",
    "route_request",
    "serialize_token_sequence",
    "validate_model_snapshot",
]
