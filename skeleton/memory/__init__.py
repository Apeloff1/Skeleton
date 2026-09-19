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
- ConsolidationCycle: KREM due-refresh → scheduler → dream wiring
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
from skeleton.memory.jvm_vector_accelerator import (
    JvmVectorAccelerator,
    JvmVectorConfig,
    VectorAcceleratorStatus,
    JvmVectorError,
    JvmVectorProtocolError,
    JvmVectorTimeout,
    JvmVectorUnavailable,
    VectorHit,
    close_default_vector_accelerator,
    get_default_vector_accelerator,
)
from skeleton.memory.consolidation import ConsolidationCycle, wire_from_genesis

__all__ = [
    "InMemoryTFIDFStore",
    "VectorStore",
    "HashEmbedder",
    "VectorEntry",
    "JvmVectorAccelerator",
    "JvmVectorConfig",
    "VectorAcceleratorStatus",
    "JvmVectorError",
    "JvmVectorUnavailable",
    "JvmVectorProtocolError",
    "JvmVectorTimeout",
    "VectorHit",
    "get_default_vector_accelerator",
    "close_default_vector_accelerator",
    "CAGStore",
    "MAGStore",
    "MemoryTrinity",
    "RepetitionScheduler",
    "Chunk",
    "ScoredChunk",
    "TrinityResult",
    "ConsolidationCycle",
    "wire_from_genesis",
]
