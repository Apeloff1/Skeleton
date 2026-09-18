"""Safe repository-backlog automation primitives."""

from .backlog_index import (
    DependencyRecord,
    ReferenceRecord,
    RepositoryIndex,
    RepositoryIndexBuilder,
    SymbolRecord,
)
from .backlog_reader import Document, Index, RepositoryReader

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


def __getattr__(name: str):
    """Load the optional model adapter only when its symbols are requested."""
    if name in {"ChatGPTReasoner", "ReasoningRequest", "ReasoningResult"}:
        from .chatgpt_adapter import ChatGPTReasoner, ReasoningRequest, ReasoningResult

        return {
            "ChatGPTReasoner": ChatGPTReasoner,
            "ReasoningRequest": ReasoningRequest,
            "ReasoningResult": ReasoningResult,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
