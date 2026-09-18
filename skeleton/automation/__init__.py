"""Safe repository-backlog automation primitives."""

from .backlog_engine import (
    BacklogCapacityError,
    BacklogFinding,
    BacklogState,
    BacklogStateError,
    RootCauseRecord,
    SourceHealth,
    workflow_failure_finding,
)
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
    "workflow_failure_finding",
    "SourceHealth",
    "RootCauseRecord",
    "BacklogStateError",
    "BacklogState",
    "BacklogFinding",
    "BacklogCapacityError",
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
