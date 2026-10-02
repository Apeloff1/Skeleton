"""Canonical user-facing standalone-AI composition boundary."""

from .canonical import (
    CANONICAL_PRODUCT_CONTEXT_BUDGET,
    CanonicalAIResponseEnvelope,
    CanonicalAITurnRequest,
    CanonicalConversationAIRuntime,
    CanonicalProductRuntimeError,
)

__all__ = [
    "CANONICAL_PRODUCT_CONTEXT_BUDGET",
    "CanonicalAIResponseEnvelope",
    "CanonicalAITurnRequest",
    "CanonicalConversationAIRuntime",
    "CanonicalProductRuntimeError",
]
