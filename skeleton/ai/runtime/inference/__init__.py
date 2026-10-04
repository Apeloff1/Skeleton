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
    "LOCAL_MODEL_DEPLOYMENT_SCHEMA",
    "QUALIFICATION_SCHEMA",
    "ArtifactIdentity",
    "CallableLocalModel",
    "GgufHeader",
    "LlamaCppConfig",
    "LlamaCppModel",
    "LlamaCppRuntimeError",
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
    "LocalModelDeployment",
    "LocalModelDeploymentError",
    "LocalToolCall",
    "ReferenceNGramModel",
    "build_llama_cpp_adapter",
    "inspect_gguf",
    "load_local_model_adapter",
    "load_local_model_artifact",
    "qualify_local_model_deployment",
    "qualify_local_model_deployment_sync",
    "write_local_model_artifact",
]
