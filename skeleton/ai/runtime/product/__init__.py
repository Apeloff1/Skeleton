"""User-facing standalone-AI composition layer."""

from .canonical import (
    CANONICAL_PRODUCT_CONTEXT_BUDGET,
    CanonicalAIResponseEnvelope,
    CanonicalAITurnRequest,
    CanonicalConversationAIRuntime,
    CanonicalProductRuntimeError,
)
from .context import CompiledContext, ContextCompiler, ContextRecord, ConversationMessage
from .session import (
    AIResponseEnvelope,
    AISessionSpec,
    AITurnRequest,
    ConversationAIRuntime,
    SQLiteSessionRepository,
)

__all__ = [
    "AIResponseEnvelope",
    "AISessionSpec",
    "AITurnRequest",
    "CANONICAL_PRODUCT_CONTEXT_BUDGET",
    "CanonicalAIResponseEnvelope",
    "CanonicalAITurnRequest",
    "CanonicalConversationAIRuntime",
    "CanonicalProductRuntimeError",
    "CompiledContext",
    "ContextCompiler",
    "ContextRecord",
    "ConversationAIRuntime",
    "ConversationMessage",
    "SQLiteSessionRepository",
]
