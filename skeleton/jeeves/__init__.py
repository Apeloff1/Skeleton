"""Skeleton Jeeves Package — providers, matrices, citations."""

from skeleton.jeeves.core import (
    JeevesCore,
    MemoryManager,
    Session,
    SessionMode,
    Turn,
)
from skeleton.jeeves.providers import (
    AnthropicProvider,
    LLMProvider,
    LocalEchoProvider,
    OpenAIProvider,
    get_provider,
)
from skeleton.jeeves.matrices import (
    CompressedLearnedOutcomeModel,
    KnowledgeRetentionMatrix,
    SemanticAssociationMap,
)
from skeleton.jeeves.citations import Citation, CitationEngine

__all__ = [
    "JeevesCore",
    "SessionMode",
    "Session",
    "MemoryManager",
    "Turn",
    "LLMProvider",
    "LocalEchoProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "get_provider",
    "SemanticAssociationMap",
    "CompressedLearnedOutcomeModel",
    "KnowledgeRetentionMatrix",
    "Citation",
    "CitationEngine",
]
