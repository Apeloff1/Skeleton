"""Canonical user-facing standalone-AI composition boundary."""

from .canonical import (
    CANONICAL_PRODUCT_CONTEXT_BUDGET,
    CanonicalAIResponseEnvelope,
    CanonicalAITurnRequest,
    CanonicalConversationAIRuntime,
    CanonicalProductRuntimeError,
)
from .learning import (
    CanonicalLearningCandidate,
    CanonicalLearningHandoffError,
    CanonicalLearningPair,
    build_learning_candidate,
    build_learning_candidate_artifact,
    build_learning_candidate_from_repository,
)
from .model_program_bridge import (
    BridgedModelProgramArtifact,
    ModelProgramBridgeError,
    bridge_product_training_to_model_program,
    model_promotion_receipt_from_qualification,
    register_bridged_model_program_artifact,
)
from .qualification import (
    LearningQualificationBundle,
    LearningQualificationError,
    MirrorModelBinding,
    qualify_learning_candidate,
)

__all__ = [
    "register_bridged_model_program_artifact",
    "model_promotion_receipt_from_qualification",
    "bridge_product_training_to_model_program",
    "ModelProgramBridgeError",
    "BridgedModelProgramArtifact",
    "CANONICAL_PRODUCT_CONTEXT_BUDGET",
    "CanonicalAIResponseEnvelope",
    "CanonicalAITurnRequest",
    "CanonicalConversationAIRuntime",
    "CanonicalLearningCandidate",
    "CanonicalLearningHandoffError",
    "CanonicalLearningPair",
    "CanonicalProductRuntimeError",
    "LearningQualificationBundle",
    "LearningQualificationError",
    "MirrorModelBinding",
    "build_learning_candidate",
    "build_learning_candidate_artifact",
    "build_learning_candidate_from_repository",
    "qualify_learning_candidate",
]
