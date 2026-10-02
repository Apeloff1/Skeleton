"""Provider-independent local model execution for the Skeleton AI runtime."""

from .artifact import (
    LoadedLocalModel,
    LocalModelArtifactError,
    LocalModelArtifactReceipt,
    load_local_model_artifact,
    local_model_adapter_from_env,
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
    "CallableLocalModel",
    "LoadedLocalModel",
    "LocalInferenceCancelled",
    "LocalInferenceEngine",
    "LocalInferenceRequest",
    "LocalInferenceResult",
    "LocalInferenceScheduler",
    "LocalModelAdapter",
    "LocalModelArtifactError",
    "LocalModelArtifactReceipt",
    "LocalModelBackend",
    "LocalToolCall",
    "NumpyRecurrentLM",
    "ReferenceNGramModel",
    "load_local_model_artifact",
    "local_model_adapter_from_env",
]


def __getattr__(name: str):
    if name == "NumpyRecurrentLM":
        from .neural import NumpyRecurrentLM

        return NumpyRecurrentLM
    raise AttributeError(name)
