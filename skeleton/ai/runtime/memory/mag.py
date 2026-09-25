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
        if isinstance(dimension, bool) or not isinstance(dimension, int) or dimension < 1:
            raise ValueError("dimension must be a positive integer")
        self.dimension = dimension
        self.vector: List[float] = [0.0] * dimension
        self.update_count: int = 0

    def update(self, interaction_vector: List[float], weight: float = 1.0) -> None:
        """Online moving-average update."""
        if len(interaction_vector) != self.dimension:
            raise ValueError(f"Expected dimension {self.dimension}, got {len(interaction_vector)}")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) for value in interaction_vector):
            raise ValueError("interaction values must be finite")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(float(weight)) or float(weight) <= 0:
            raise ValueError("weight must be positive")
        self.update_count += 1
        alpha = weight / self.update_count
        for i in range(self.dimension):
            self.vector[i] = (1 - alpha) * self.vector[i] + alpha * interaction_vector[i]

    def similarity(self, other: "PreferenceEmbedding") -> float:
        """Cosine similarity between preference vectors."""
        if not isinstance(other, PreferenceEmbedding):
            raise TypeError("other must be a preference embedding")
        if self.update_count == 0 or other.update_count == 0:
            raise ValueError("preference similarity needs an update")
        if self.dimension != other.dimension:
            raise ValueError("preference dimensions differ")
        dot = sum(a * b for a, b in zip(self.vector, other.vector))
        norm1 = math.sqrt(sum(a * a for a in self.vector))
        norm2 = math.sqrt(sum(b * b for b in other.vector))
        if norm1 == 0 or norm2 == 0:
            raise ValueError("preference similarity needs a non-zero vector")
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
        if not isinstance(content, str) or not content:
            raise ValueError("content must be a non-empty string")
        if isinstance(emotional_valence, bool) or not isinstance(
            emotional_valence, (int, float)
        ):
            raise TypeError("emotional_valence must be numeric")
        if not -1.0 <= float(emotional_valence) <= 1.0:
            raise ValueError("emotional_valence must be in [-1, 1]")
        if isinstance(importance, bool) or not isinstance(importance, (int, float)):
            raise TypeError("importance must be numeric")
        if float(importance) < 0.0:
            raise ValueError("importance must be non-negative")
        if tags is not None and not isinstance(tags, set):
            raise TypeError("tags must be a set when provided")
        episode_id = f"mag_{self.user_id}_{hashlib.sha256(content.encode()).hexdigest()[:16]}"

        previous = self._episodes.get(episode_id)
        if previous is not None:
            for tag in previous.tags:
                self._tag_index[tag].discard(episode_id)
                if not self._tag_index[tag]:
                    del self._tag_index[tag]

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

    def clusters(self, *, min_size: int = 2) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """Return tag groups large enough to consolidate, without exposing store internals."""

        if isinstance(min_size, bool) or not isinstance(min_size, int) or min_size < 2:
            raise ValueError("min_size must be an integer >= 2")
        grouped: list[tuple[str, tuple[str, ...]]] = []
        for tag in sorted(self._tag_index):
            episode_ids = tuple(sorted(episode_id for episode_id in self._tag_index[tag] if episode_id in self._episodes))
            if len(episode_ids) >= min_size:
                grouped.append((tag, episode_ids))
        return tuple(grouped)

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
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise TypeError("top_k must be an integer")
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        if isinstance(min_score, bool) or not isinstance(min_score, (int, float)):
            raise TypeError("min_score must be numeric")
        if metadata_filter is not None and not isinstance(metadata_filter, dict):
            raise TypeError("metadata_filter must be a mapping")
        if top_k == 0:
            return []
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

        scored.sort(key=lambda item: (-item[0], item[1].episode_id))

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

    def query_scoped(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        scope: Dict[str, str],
    ) -> List[MemoryQueryResult]:
        """Enforce the store's user identity before scoring episodic memory."""
        if not isinstance(scope, dict) or set(scope) != {"user_id"}:
            raise ValueError("MAG scope must contain exactly user_id")
        if not isinstance(scope["user_id"], str) or not scope["user_id"]:
            raise ValueError("user_id scope must be a non-empty string")
        if scope["user_id"] != str(self.user_id):
            return []
        return self.query(query_text, top_k=top_k)

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
