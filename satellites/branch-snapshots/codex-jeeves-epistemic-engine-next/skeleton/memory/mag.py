"""MAG — episodic & preference memory — split from the memory monolith (v16.2)."""

from __future__ import annotations

import hashlib
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from skeleton.kernel.ids import UserId

from .types import MemoryChunk, MemoryQueryResult
from .store import MemoryStore

# =============================================================================
# MAG — MEMORY-AUGMENTED GENERATION
# =============================================================================

@dataclass
class EpisodicMemory:
    """A single episodic memory entry with emotional valence and decay."""
    episode_id: str
    timestamp: float
    content: str
    emotional_valence: float = 0.0  # -1.0 to 1.0
    importance: float = 1.0
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    tags: Set[str] = field(default_factory=set)

    def compute_retrieval_probability(
        self, query_time: float, decay_rate: float = 0.001
    ) -> float:
        """
        Compute probability of recall using exponential decay + rehearsal bonus.
        R = importance * exp(-decay * Δt) * (1 + log(access_count + 1))
        """
        time_delta = query_time - self.timestamp
        decay = math.exp(-decay_rate * time_delta)
        rehearsal = 1.0 + math.log(self.access_count + 1)
        return self.importance * decay * rehearsal


class PreferenceEmbedding:
    """User preference vector with incremental updates."""

    def __init__(self, dimension: int = 128) -> None:
        self.dimension = dimension
        self.vector: List[float] = [0.0] * dimension
        self.update_count: int = 0

    def update(self, interaction_vector: List[float], weight: float = 1.0) -> None:
        """Online moving-average update."""
        if len(interaction_vector) != self.dimension:
            raise ValueError(f"Expected dimension {self.dimension}, got {len(interaction_vector)}")
        self.update_count += 1
        alpha = weight / self.update_count
        for i in range(self.dimension):
            self.vector[i] = (1 - alpha) * self.vector[i] + alpha * interaction_vector[i]

    def similarity(self, other: "PreferenceEmbedding") -> float:
        """Cosine similarity between preference vectors."""
        dot = sum(a * b for a, b in zip(self.vector, other.vector))
        norm1 = math.sqrt(sum(a * a for a in self.vector))
        norm2 = math.sqrt(sum(b * b for b in other.vector))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)


class MAGStore(MemoryStore):
    """
    Memory-Augmented Generation store.
    Episodic memory, preference embeddings, and personalised recall.
    """

    def __init__(self, user_id: UserId) -> None:
        self.user_id = user_id
        self._episodes: Dict[str, EpisodicMemory] = {}
        self._preference = PreferenceEmbedding()
        self._tag_index: Dict[str, Set[str]] = defaultdict(set)
        self._decay_rate: float = 0.001

    def add_episode(
        self,
        content: str,
        *,
        emotional_valence: float = 0.0,
        importance: float = 1.0,
        tags: Optional[Set[str]] = None,
    ) -> str:
        episode_id = f"mag_{self.user_id}_{hashlib.sha256(content.encode()).hexdigest()[:16]}"
        episode = EpisodicMemory(
            episode_id=episode_id,
            timestamp=time.time(),
            content=content,
            emotional_valence=emotional_valence,
            importance=importance,
            tags=tags or set(),
        )
        self._episodes[episode_id] = episode
        for tag in episode.tags:
            self._tag_index[tag].add(episode_id)
        return episode_id

    def update_preference(self, interaction_vector: List[float], weight: float = 1.0) -> None:
        self._preference.update(interaction_vector, weight)

    def add(self, chunk: MemoryChunk) -> None:
        """Add a memory chunk as an episodic memory."""
        tags = set(chunk.metadata.get("tags", []))
        self.add_episode(
            chunk.text,
            emotional_valence=chunk.metadata.get("valence", 0.0),
            importance=chunk.metadata.get("importance", 1.0),
            tags=tags,
        )

    def query(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[MemoryQueryResult]:
        query_time = time.time()
        query_words = set(query_text.lower().split())

        # Score episodes by retrieval probability + keyword overlap
        scored: List[Tuple[float, EpisodicMemory]] = []
        for episode in self._episodes.values():
            # Filter by metadata if specified
            if metadata_filter:
                skip = False
                for k, v in metadata_filter.items():
                    if k == "tags":
                        if not isinstance(v, list) or not any(t in episode.tags for t in v):
                            skip = True
                            break
                    elif k == "min_importance" and episode.importance < v:
                        skip = True
                        break
                if skip:
                    continue

            retrieval_prob = episode.compute_retrieval_probability(query_time, self._decay_rate)

            # Keyword overlap bonus
            content_words = set(episode.content.lower().split())
            overlap = len(query_words & content_words) / max(len(query_words), 1)

            # Emotional resonance (boost if query sentiment matches)
            # Simplified: assume neutral query, use absolute valence as distinctiveness
            emotional_boost = abs(episode.emotional_valence) * 0.1

            score = retrieval_prob * 0.6 + overlap * 0.3 + emotional_boost * 0.1

            if score >= min_score:
                scored.append((score, episode))

        scored.sort(key=lambda x: x[0], reverse=True)

        results: List[MemoryQueryResult] = []
        for i, (score, episode) in enumerate(scored[:top_k]):
            # Update access stats
            episode.last_accessed = query_time
            episode.access_count += 1

            chunk = MemoryChunk(
                id=episode.episode_id,
                text=episode.content,
                metadata={
                    "valence": episode.emotional_valence,
                    "importance": episode.importance,
                    "tags": list(episode.tags),
                    "access_count": episode.access_count,
                },
                source_tier="mag",
                confidence=score,
            )
            results.append(MemoryQueryResult(chunk=chunk, score=score, rank=i + 1))

        return results

    def delete(self, chunk_id: str) -> bool:
        if chunk_id not in self._episodes:
            return False
        episode = self._episodes.pop(chunk_id)
        for tag in episode.tags:
            self._tag_index[tag].discard(chunk_id)
        return True

    def get_preference_vector(self) -> List[float]:
        return self._preference.vector.copy()

    def health(self) -> Dict[str, Any]:
        return {
            "tier": "mag",
            "episodes": len(self._episodes),
            "tags": len(self._tag_index),
            "preference_updates": self._preference.update_count,
            "status": "healthy",
        }
