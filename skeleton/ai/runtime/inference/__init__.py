"""Provider-independent local model execution for the Skeleton AI runtime."""

from .llama_cpp import (
    ArtifactIdentity,
    LlamaCppConfig,
    LlamaCppModel,
    LlamaCppRuntimeError,
    build_llama_cpp_adapter,
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
    "ArtifactIdentity",
    "LlamaCppConfig",
    "LlamaCppModel",
    "LlamaCppRuntimeError",
    "build_llama_cpp_adapter",
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
