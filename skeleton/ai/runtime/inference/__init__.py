"""Provider-independent local model execution for the Skeleton AI runtime."""

from .artifact import (
    LoadedLocalModel,
    LocalModelArtifactError,
    LocalModelArtifactReceipt,
    load_local_model_artifact,
    local_model_adapter_from_env,
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
from .multiview import (
    CameraCoveragePlan,
    CameraCoveragePolicy,
    CameraView,
    CameraViewError,
    build_camera_coverage,
    stratified_camera_subset,
)
from .training_allocation import (
    AdaptiveMethodAllocation,
    MethodAllocationScore,
    MethodValidationObservation,
    TrainingAllocationError,
    TrainingAllocationPolicy,
    allocate_training_methods,
    observe_mirror_validation,
)
from .training_methods import (
    DEFAULT_TEXT_METHODS,
    CompiledTrainingDocument,
    MethodWeight,
    MultiMethodTrainingPlan,
    TrainingEfficiencyPolicy,
    TrainingExample,
    TrainingMethod,
    TrainingMethodError,
    compile_training_plan,
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
    "observe_mirror_validation",
    "allocate_training_methods",
    "TrainingAllocationPolicy",
    "TrainingAllocationError",
    "MethodValidationObservation",
    "MethodAllocationScore",
    "AdaptiveMethodAllocation",
    "stratified_camera_subset",
    "compile_training_plan",
    "build_camera_coverage",
    "TrainingMethodError",
    "TrainingMethod",
    "TrainingExample",
    "TrainingEfficiencyPolicy",
    "MultiMethodTrainingPlan",
    "MethodWeight",
    "DEFAULT_TEXT_METHODS",
    "CompiledTrainingDocument",
    "CameraViewError",
    "CameraView",
    "CameraCoveragePolicy",
    "CameraCoveragePlan",
    "ArtifactIdentity",
    "CallableLocalModel",
    "GgufHeader",
    "LoadedLocalModel",
    "LOCAL_MODEL_DEPLOYMENT_SCHEMA",
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
    "LlamaCppConfig",
    "LlamaCppModel",
    "LlamaCppRuntimeError",
    "NumpyRecurrentLM",
    "QUALIFICATION_SCHEMA",
    "ReferenceNGramModel",
    "build_llama_cpp_adapter",
    "inspect_gguf",
    "load_local_model_adapter",
    "load_local_model_artifact",
    "local_model_adapter_from_env",
    "qualify_local_model_deployment",
    "qualify_local_model_deployment_sync",
]


def __getattr__(name: str):
    if name == "NumpyRecurrentLM":
        from .neural import NumpyRecurrentLM

        return NumpyRecurrentLM
    raise AttributeError(name)
