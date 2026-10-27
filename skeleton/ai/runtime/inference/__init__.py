"""Provider-independent local model execution for the Skeleton AI runtime."""

from .artifact import (
    LoadedLocalModel,
    LocalModelArtifactError,
    LocalModelArtifactReceipt,
    load_local_model_artifact,
    write_local_model_artifact,
)
from .deployment import (
    QUALIFICATION_SCHEMA,
    LocalModelDeployment,
    LocalModelDeploymentError,
    load_local_model_adapter,
    qualify_local_model_deployment,
    qualify_local_model_deployment_sync,
)
from .deployment import (
    SCHEMA as LOCAL_MODEL_DEPLOYMENT_SCHEMA,
)
from .llama_cpp import (
    ArtifactIdentity,
    ConsumerHardwareBudget,
    ConsumerLlamaPlan,
    GgufHeader,
    LlamaCppConfig,
    LlamaCppModel,
    LlamaCppRuntimeError,
    build_llama_cpp_adapter,
    detect_consumer_hardware_budget,
    estimate_gqa_kv_bytes_per_token,
    inspect_gguf,
    plan_consumer_llama_cpp,
)
from .local import (
    CallableLocalModel,
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceOverloaded,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalInferenceScheduler,
    LocalModelAdapter,
    LocalModelBackend,
    LocalToolCall,
    ReferenceNGramModel,
)

__all__ = [
    "LOCAL_MODEL_DEPLOYMENT_SCHEMA",
    "QUALIFICATION_SCHEMA",
    "ArtifactIdentity",
    "CallableLocalModel",
    "ConsumerHardwareBudget",
    "ConsumerLlamaPlan",
    "GgufHeader",
    "LlamaCppConfig",
    "LlamaCppModel",
    "LlamaCppRuntimeError",
    "LoadedLocalModel",
    "LocalInferenceCancelled",
    "LocalInferenceEngine",
    "LocalInferenceOverloaded",
    "LocalInferenceRequest",
    "LocalInferenceResult",
    "LocalInferenceScheduler",
    "LocalModelAdapter",
    "LocalModelArtifactError",
    "LocalModelArtifactReceipt",
    "LocalModelBackend",
    "LocalModelDeployment",
    "LocalModelDeploymentError",
    "LocalToolCall",
    "NativeRuntimeBackendError",
    "NativeRuntimeLocalModel",
    "NativeTransformerModel",
    "ReferenceNGramModel",
    "build_llama_cpp_adapter",
    "build_native_transformer_adapter",
    "detect_consumer_hardware_budget",
    "estimate_gqa_kv_bytes_per_token",
    "inspect_gguf",
    "load_local_model_adapter",
    "load_local_model_artifact",
    "plan_consumer_llama_cpp",
    "qualify_local_model_deployment",
    "qualify_local_model_deployment_sync",
    "write_local_model_artifact",
]


# The executable native transformer depends on Cortex; import only when selected.
from importlib import import_module as _inference_import_module

_NATIVE_EXPORTS = {
    "NativeTransformerModel": ".native_transformer",
    "build_native_transformer_adapter": ".native_transformer",
}


def __getattr__(name: str):
    if name in {"NativeRuntimeBackendError", "NativeRuntimeLocalModel"}:
        from importlib import import_module

        result = getattr(import_module(".native_runtime", __name__), name)
        globals()[name] = result
        return result
    module = _NATIVE_EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    # Both admitted exports share one known implementation owner. Never feed
    # a dispatch-table value into an executable import operation.
    value = getattr(_inference_import_module(".native_transformer", __name__), name)
    globals()[name] = value
    return value
