"""Provider-independent local model execution for the Skeleton AI runtime."""

from .artifact import (
    LoadedLocalModel,
    LocalModelArtifactError,
    LocalModelArtifactReceipt,
    load_local_model_artifact,
    write_local_model_artifact,
)
from .deployment import (
    LocalModelDeployment,
    LocalModelDeploymentError,
    QUALIFICATION_SCHEMA,
    SCHEMA as LOCAL_MODEL_DEPLOYMENT_SCHEMA,
    load_local_model_adapter,
    qualify_local_model_deployment,
    qualify_local_model_deployment_sync,
)
from .llama_cpp import (
    ArtifactIdentity,
    GgufHeader,
    LlamaCppConfig,
    LlamaCppModel,
    LlamaCppRuntimeError,
    build_llama_cpp_adapter,
    inspect_gguf,
)
from .local import (
    CallableLocalModel,
    LocalInferenceCancelled,
    LocalInferenceEngine,
    LocalInferenceRequest,
    LocalInferenceResult,
    LocalInferenceScheduler,
    LocalModelAdapter,
    LocalModelBackend,
    LocalToolCall,
    ReferenceNGramModel,
)

__all__ = [
    "NativeRuntimeBackendError",
    "NativeRuntimeLocalModel",
    "NativeTransformerModel",
    "build_native_transformer_adapter",
    "LoadedLocalModel",
    "LocalModelArtifactError",
    "LocalModelArtifactReceipt",
    "load_local_model_artifact",
    "write_local_model_artifact",
    "LocalModelDeployment",
    "LocalModelDeploymentError",
    "LOCAL_MODEL_DEPLOYMENT_SCHEMA",
    "QUALIFICATION_SCHEMA",
    "load_local_model_adapter",
    "qualify_local_model_deployment",
    "qualify_local_model_deployment_sync",
    "ArtifactIdentity",
    "GgufHeader",
    "LlamaCppConfig",
    "LlamaCppModel",
    "LlamaCppRuntimeError",
    "build_llama_cpp_adapter",
    "inspect_gguf",
    "CallableLocalModel",
    "LocalInferenceCancelled",
    "LocalInferenceEngine",
    "LocalInferenceRequest",
    "LocalInferenceResult",
    "LocalInferenceScheduler",
    "LocalModelAdapter",
    "LocalModelBackend",
    "LocalToolCall",
    "ReferenceNGramModel",
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
    value = getattr(_inference_import_module(module, __name__), name)
    globals()[name] = value
    return value
