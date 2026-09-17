"""Safe repository-backlog automation primitives."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .backlog_index import (
    DependencyRecord,
    ReferenceRecord,
    RepositoryIndex,
    RepositoryIndexBuilder,
    SymbolRecord,
)
from .backlog_reader import Document, Index, RepositoryReader

if TYPE_CHECKING:
    from .chatgpt_adapter import ChatGPTReasoner, ReasoningRequest, ReasoningResult

_REASONING_EXPORTS = frozenset({"ChatGPTReasoner", "ReasoningRequest", "ReasoningResult"})


def __getattr__(name: str) -> Any:
    """Load the optional model adapter only when a reasoning export is requested."""
    if name not in _REASONING_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from . import chatgpt_adapter

    value = getattr(chatgpt_adapter, name)
    globals()[name] = value
    return value


__all__ = [
    "ChatGPTReasoner",
    "DependencyRecord",
    "Document",
    "Index",
    "ReasoningRequest",
    "ReasoningResult",
    "ReferenceRecord",
    "RepositoryIndex",
    "RepositoryIndexBuilder",
    "RepositoryReader",
    "SymbolRecord",
]
