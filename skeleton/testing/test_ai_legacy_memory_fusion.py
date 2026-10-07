from __future__ import annotations

from skeleton.memory.core import Chunk as CanonicalChunk
from skeleton.memory.core import MemoryTrinity as CanonicalTrinity
from skeleton.memory.core import ScoredChunk as CanonicalScored
from skeleton.ai.runtime.memory.core import Chunk as AIChunk
from skeleton.ai.runtime.memory.core import MemoryTrinity as AITrinity
from skeleton.ai.runtime.memory.core import ScoredChunk as AIScored


def test_anonymous_memory_content_identity_fuses_deterministically() -> None:
    for trinity_type, chunk_type, scored_type in (
        (CanonicalTrinity, CanonicalChunk, CanonicalScored),
        (AITrinity, AIChunk, AIScored),
    ):
        first = scored_type(chunk=chunk_type(text="same anonymous memory"), score=0.9, plane="rag")
        second = scored_type(chunk=chunk_type(text="same anonymous memory"), score=0.7, plane="mag")
        results = trinity_type._reciprocal_rank_fusion([first, second])
        assert len(results) == 1
        assert results[0].chunk.text == "same anonymous memory"


def test_legacy_rrf_equal_scores_use_stable_identity_tie_break() -> None:
    for trinity_type, chunk_type, scored_type in (
        (CanonicalTrinity, CanonicalChunk, CanonicalScored),
        (AITrinity, AIChunk, AIScored),
    ):
        items = []
        for rank in range(1, 46):
            if rank in {3, 45}:
                chunk_id = "z"
            elif rank in {10, 30}:
                chunk_id = "a"
            else:
                chunk_id = f"filler-{rank:02d}"
            items.append(scored_type(chunk=chunk_type(text=chunk_id, chunk_id=chunk_id), score=1.0, plane="rag"))
        results = trinity_type._reciprocal_rank_fusion(items)
        ordered = [item.chunk.chunk_id for item in results]
        assert ordered.index("a") < ordered.index("z")
