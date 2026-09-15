"""MemoryStore interface — split from the memory monolith (v16.2)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .types import MemoryChunk, MemoryQueryResult

# =============================================================================
# MEMORY STORE INTERFACE
# =============================================================================

class MemoryStore(ABC):
    """Common interface for all memory tiers."""

    @abstractmethod
    def add(self, chunk: MemoryChunk) -> None:
        """Store a memory chunk."""
        ...

    @abstractmethod
    def query(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[MemoryQueryResult]:
        """Query memory and return ranked results."""
        ...

    @abstractmethod
    def delete(self, chunk_id: str) -> bool:
        """Delete a chunk by id. Returns True if found."""
        ...

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Return health metrics for this store."""
        ...
