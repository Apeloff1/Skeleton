"""Memory package — the RAG/CAG/MAG trinity (split from the v16 monolith)."""

from .types import MemoryChunk, MemoryQueryResult, UnifiedContext
from .store import MemoryStore
from .rag import InMemoryTFIDFStore, ChromaDBStore
from .cag import PersonaContext, CAGStore
from .mag import EpisodicMemory, PreferenceEmbedding, MAGStore
from .trinity import MemoryTrinity
from .repetition import Outcome, RepetitionScheduler, ReviewCard
from .prefix_renderer import (
    CAGPrefix,
    PrefixRenderer,
    PrefixRegistry,
    PrefixSegment,
    build_prefix,
    content_hash,
    estimate_tokens,
)
from .warmer import Filler, FillerStore, MemoryWarmer
from .distill import (
    NON_LEXICAL_WORDS,
    DistilledFact,
    DistilledStore,
    distill,
    is_non_lexical,
    worth_remembering,
)
from .eviction import evict_for_capacity, keep_score
from .compaction import CompactionResult, ContextCompactor, Turn
from .rot_guard import ContextRotGuard, RotReport
from .guarded_compaction import GuardedResult, RotGuardedCompactor

__all__ = ['MemoryChunk', 'MemoryQueryResult', 'UnifiedContext', 'MemoryStore', 'InMemoryTFIDFStore', 'ChromaDBStore', 'PersonaContext', 'CAGStore', 'EpisodicMemory', 'PreferenceEmbedding', 'MAGStore', 'MemoryTrinity', 'RepetitionScheduler', 'ReviewCard', 'Outcome', 'CAGPrefix', 'PrefixRenderer', 'PrefixRegistry', 'PrefixSegment', 'build_prefix', 'content_hash', 'estimate_tokens', 'Filler', 'FillerStore', 'MemoryWarmer', 'NON_LEXICAL_WORDS', 'DistilledFact', 'DistilledStore', 'distill', 'is_non_lexical', 'worth_remembering', 'evict_for_capacity', 'keep_score', 'CompactionResult', 'ContextCompactor', 'Turn', 'ContextRotGuard', 'RotReport', 'GuardedResult', 'RotGuardedCompactor']
