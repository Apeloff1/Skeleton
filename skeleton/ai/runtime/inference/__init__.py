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
from .native_transformer import NativeTransformerModel, build_native_transformer_adapter
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
    "NativeTransformerModel",
    "build_native_transformer_adapter",
]
