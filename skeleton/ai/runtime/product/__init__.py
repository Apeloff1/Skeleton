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
from .qualification import (
    LearningQualificationBundle,
    LearningQualificationError,
    MirrorModelBinding,
    qualify_learning_candidate,
)

__all__ = [
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
