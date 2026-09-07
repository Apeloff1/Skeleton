"""Skeleton Jeeves Package — with provider abstraction."""

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
]
