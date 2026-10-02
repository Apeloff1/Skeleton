"""Provider-independent local model execution for the Skeleton AI runtime."""

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
    "LocalModelDeployment",
    "LocalModelDeploymentError",
    "LOCAL_MODEL_DEPLOYMENT_SCHEMA",
    "QUALIFICATION_SCHEMA",
    "load_local_model_adapter",
    "qualify_local_model_deployment",
    "qualify_local_model_deployment_sync",
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
