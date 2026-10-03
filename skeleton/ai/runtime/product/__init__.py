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
)

__all__ = [
    "CANONICAL_PRODUCT_CONTEXT_BUDGET",
    "CanonicalAIResponseEnvelope",
    "CanonicalAITurnRequest",
    "CanonicalConversationAIRuntime",
    "CanonicalProductRuntimeError",
    "CanonicalLearningCandidate",
    "CanonicalLearningHandoffError",
    "CanonicalLearningPair",
    "build_learning_candidate",
    "build_learning_candidate_artifact",
]
