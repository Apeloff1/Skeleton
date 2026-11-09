"""Shared memory types — split from the memory monolith (v16.2)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass(frozen=True)
class MemoryChunk:
    """A single chunk of retrievable memory."""
    id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    timestamp: float = field(default_factory=time.time)
    source_tier: str = "unknown"  # "rag", "cag", "mag"
    confidence: float = 1.0

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass
class MemoryQueryResult:
    """Result of a memory query with provenance."""
    chunk: MemoryChunk
    score: float
    rank: int
    fusion_contribution: float = 0.0  # Weight in cross-tier fusion


@dataclass
class UnifiedContext:
    """Combined context from all three memory tiers."""
    facts: List[MemoryQueryResult] = field(default_factory=list)      # RAG
    persona_frame: List[MemoryQueryResult] = field(default_factory=list)  # CAG
    personal_history: List[MemoryQueryResult] = field(default_factory=list)  # MAG
    combined_score: float = 0.0
    token_estimate: int = 0
    provenance_chain: List[str] = field(default_factory=list)
