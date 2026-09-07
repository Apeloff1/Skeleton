"""
Skeleton Memory Package

Exports:
- InMemoryTFIDFStore: Sparse RAG retrieval (fallback)
- VectorStore: Dense embedding retrieval (default RAG plane)
- HashEmbedder: Deterministic local embedder
- CAGStore: Contextual associative memory
- MAGStore: Multi-agent episodic memory
- MemoryTrinity: Unified fusion across planes
- RepetitionScheduler: Spaced repetition consolidation
"""

from skeleton.memory.core import (
    CAGStore,
    Chunk,
    InMemoryTFIDFStore,
    MAGStore,
    MemoryTrinity,
    RepetitionScheduler,
    ScoredChunk,
    TrinityResult,
)
from skeleton.memory.vector import HashEmbedder, VectorEntry, VectorStore

__all__ = [
    "InMemoryTFIDFStore",
    "VectorStore",
    "HashEmbedder",
    "VectorEntry",
    "CAGStore",
    "MAGStore",
    "MemoryTrinity",
    "RepetitionScheduler",
    "Chunk",
    "ScoredChunk",
    "TrinityResult",
]
