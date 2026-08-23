"""
================================================================================
skeleton.memory — RAG / CAG / MAG Memory Trinity
================================================================================
Three-tier memory architecture for the Jeeves AI tutor brain.

RAG (Retrieval-Augmented Generation)
  ChromaDB primary + in-memory TF-IDF fallback. Semantic search over
  chunked documents with metadata filtering and hybrid ranking.

CAG (Context-Augmented Generation)
  Hot-swappable persona contexts, knowledge-graph pre-loading, and
  dynamic context window management with importance scoring.

MAG (Memory-Augmented Generation)
  Episodic memory (user interactions), preference embeddings, long-term
  retention curves with forgetting models, and personalised recall.

Design invariants:
  1. All three tiers share a common MemoryStore interface.
  2. Fallbacks are fully implemented, not stubs.
  3. Every query returns a confidence score and provenance chain.
  4. Memory operations are auditable via the kernel event bus.
  5. Cross-tier fusion: RAG provides facts, CAG provides persona framing,
     MAG provides personal history — combined into a unified context window.
================================================================================
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from skeleton.kernel.errors import RagUnavailableError, RagQueryError
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.ids import UserId


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


# =============================================================================
# RAG — RETRIEVAL-AUGMENTED GENERATION
# =============================================================================

class InMemoryTFIDFStore(MemoryStore):
    """
    Fully implemented in-memory TF-IDF vector store.
    No external dependencies. Deterministic. Testable.
    """

    def __init__(self) -> None:
        self._chunks: Dict[str, MemoryChunk] = {}
        self._doc_freq: Dict[str, int] = defaultdict(int)
        self._total_docs: int = 0

    def _tokenize(self, text: str) -> List[str]:
        """Simple but effective tokenisation."""
        return re.findall(r"\b[a-zA-Z]{2,}\b", text.lower())

    def _compute_tf(self, tokens: List[str]) -> Dict[str, float]:
        """Term frequency with log normalisation."""
        freq: Dict[str, int] = defaultdict(int)
        for t in tokens:
            freq[t] += 1
        max_freq = max(freq.values()) if freq else 1
        return {t: 0.5 + 0.5 * (f / max_freq) for t, f in freq.items()}

    def _compute_idf(self) -> Dict[str, float]:
        """Inverse document frequency."""
        return {
            t: math.log((self._total_docs + 1) / (df + 1)) + 1
            for t, df in self._doc_freq.items()
        }

    def _vectorise(self, text: str, idf: Dict[str, float]) -> Dict[str, float]:
        """TF-IDF vector as sparse dict."""
        tokens = self._tokenize(text)
        tf = self._compute_tf(tokens)
        return {t: tf.get(t, 0) * idf.get(t, 0) for t in set(tokens)}

    def _cosine_similarity(
        self, v1: Dict[str, float], v2: Dict[str, float]
    ) -> float:
        """Cosine similarity between two sparse vectors."""
        dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in set(v1) & set(v2))
        norm1 = math.sqrt(sum(v * v for v in v1.values()))
        norm2 = math.sqrt(sum(v * v for v in v2.values()))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def add(self, chunk: MemoryChunk) -> None:
        self._chunks[chunk.id] = chunk
        tokens = set(self._tokenize(chunk.text))
        for t in tokens:
            self._doc_freq[t] += 1
        self._total_docs += 1

    def query(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[MemoryQueryResult]:
        if not self._chunks:
            return []

        idf = self._compute_idf()
        query_vec = self._vectorise(query_text, idf)

        results: List[Tuple[float, MemoryChunk]] = []
        for chunk in self._chunks.values():
            # Metadata filtering
            if metadata_filter:
                skip = False
                for k, v in metadata_filter.items():
                    if chunk.metadata.get(k) != v:
                        skip = True
                        break
                if skip:
                    continue

            chunk_vec = self._vectorise(chunk.text, idf)
            score = self._cosine_similarity(query_vec, chunk_vec)
            if score >= min_score:
                results.append((score, chunk))

        results.sort(key=lambda x: x[0], reverse=True)
        return [
            MemoryQueryResult(chunk=chunk, score=score, rank=i + 1)
            for i, (score, chunk) in enumerate(results[:top_k])
        ]

    def delete(self, chunk_id: str) -> bool:
        if chunk_id not in self._chunks:
            return False
        chunk = self._chunks.pop(chunk_id)
        tokens = set(self._tokenize(chunk.text))
        for t in tokens:
            self._doc_freq[t] -= 1
            if self._doc_freq[t] <= 0:
                del self._doc_freq[t]
        self._total_docs -= 1
        return True

    def health(self) -> Dict[str, Any]:
        return {
            "tier": "rag",
            "backend": "in_memory_tfidf",
            "chunks": len(self._chunks),
            "vocabulary": len(self._doc_freq),
            "status": "healthy",
        }


class ChromaDBStore(MemoryStore):
    """
    ChromaDB-backed store with graceful fallback to in-memory.
    Attempts import; if unavailable, raises RagUnavailableError.
    """

    def __init__(self, collection_name: str = "skeleton_memory") -> None:
        self._collection_name = collection_name
        self._fallback = InMemoryTFIDFStore()
        self._client: Any = None
        self._collection: Any = None
        self._available = False
        self._init_chroma()

    def _init_chroma(self) -> None:
        try:
            import chromadb
            self._client = chromadb.Client()
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
        except ImportError:
            self._available = False
        except Exception as exc:
            raise RagUnavailableError(
                "ChromaDB initialisation failed",
                context={"exception": str(exc)},
            ) from exc

    def add(self, chunk: MemoryChunk) -> None:
        if self._available and self._collection:
            self._collection.add(
                ids=[chunk.id],
                documents=[chunk.text],
                metadatas=[chunk.metadata],
                embeddings=[chunk.embedding] if chunk.embedding else None,
            )
        else:
            self._fallback.add(chunk)

    def query(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[MemoryQueryResult]:
        if self._available and self._collection:
            try:
                results = self._collection.query(
                    query_texts=[query_text],
                    n_results=top_k,
                    where=metadata_filter,
                )
                memory_results: List[MemoryQueryResult] = []
                for i in range(len(results["ids"][0])):
                    score = results["distances"][0][i] if results["distances"] else 0.0
                    # Convert distance to similarity (cosine distance → similarity)
                    similarity = 1.0 - score
                    if similarity >= min_score:
                        chunk = MemoryChunk(
                            id=results["ids"][0][i],
                            text=results["documents"][0][i],
                            metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                            source_tier="rag",
                            confidence=similarity,
                        )
                        memory_results.append(
                            MemoryQueryResult(chunk=chunk, score=similarity, rank=i + 1)
                        )
                return memory_results
            except Exception as exc:
                raise RagQueryError(
                    f"ChromaDB query failed: {exc}",
                    context={"query": query_text, "top_k": top_k},
                ) from exc
        else:
            return self._fallback.query(
                query_text, top_k=top_k, metadata_filter=metadata_filter, min_score=min_score
            )

    def delete(self, chunk_id: str) -> bool:
        if self._available and self._collection:
            try:
                self._collection.delete(ids=[chunk_id])
                return True
            except Exception:
                return False
        else:
            return self._fallback.delete(chunk_id)

    def health(self) -> Dict[str, Any]:
        return {
            "tier": "rag",
            "backend": "chromadb" if self._available else "in_memory_tfidf_fallback",
            "available": self._available,
            "fallback_health": self._fallback.health(),
            "status": "healthy" if self._available else "degraded",
        }


# =============================================================================
# CAG — CONTEXT-AUGMENTED GENERATION
# =============================================================================

@dataclass
class PersonaContext:
    """A hot-swappable persona context with importance scoring."""
    persona_id: str
    name: str
    system_prompt: str
    knowledge_graph: Dict[str, List[str]] = field(default_factory=dict)
    importance_scores: Dict[str, float] = field(default_factory=dict)
    max_tokens: int = 4000
    current_tokens: int = 0

    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate (4 chars ≈ 1 token)."""
        return len(text) // 4

    def add_knowledge(self, key: str, facts: List[str], importance: float = 1.0) -> None:
        """Add facts to the knowledge graph with importance weighting."""
        self.knowledge_graph[key] = facts
        self.importance_scores[key] = importance
        self.current_tokens += sum(self.estimate_tokens(f) for f in facts)
        self._evict_if_needed()

    def _evict_if_needed(self) -> None:
        """Evict lowest-importance knowledge if over token budget."""
        while self.current_tokens > self.max_tokens and self.knowledge_graph:
            # Find lowest importance
            lowest_key = min(self.importance_scores, key=self.importance_scores.get)
            facts = self.knowledge_graph.pop(lowest_key)
            self.current_tokens -= sum(self.estimate_tokens(f) for f in facts)
            del self.importance_scores[lowest_key]

    def get_context_window(self, query: str) -> str:
        """Build context window prioritised by relevance to query + importance."""
        # Score each knowledge node by keyword overlap + importance
        query_words = set(query.lower().split())
        scored: List[Tuple[float, str, List[str]]] = []
        for key, facts in self.knowledge_graph.items():
            overlap = len(set(key.lower().split()) & query_words)
            importance = self.importance_scores.get(key, 1.0)
            score = overlap * 0.3 + importance * 0.7
            scored.append((score, key, facts))

        scored.sort(reverse=True)

        tokens_used = self.estimate_tokens(self.system_prompt)
        parts: List[str] = [self.system_prompt]

        for score, key, facts in scored:
            fact_text = f"[{key}]: " + "; ".join(facts)
            fact_tokens = self.estimate_tokens(fact_text)
            if tokens_used + fact_tokens > self.max_tokens:
                break
            parts.append(fact_text)
            tokens_used += fact_tokens

        return "\n\n".join(parts)


class CAGStore(MemoryStore):
    """
    Context-Augmented Generation store.
    Manages persona contexts with hot-swapping and knowledge-graph pre-loading.
    """

    def __init__(self) -> None:
        self._personas: Dict[str, PersonaContext] = {}
        self._active_persona_id: Optional[str] = None

    def create_persona(
        self,
        persona_id: str,
        name: str,
        system_prompt: str,
        max_tokens: int = 4000,
    ) -> PersonaContext:
        persona = PersonaContext(
            persona_id=persona_id,
            name=name,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )
        self._personas[persona_id] = persona
        if self._active_persona_id is None:
            self._active_persona_id = persona_id
        return persona

    def switch_persona(self, persona_id: str) -> None:
        if persona_id not in self._personas:
            raise RagQueryError(f"Persona {persona_id} not found")
        self._active_persona_id = persona_id

    def add(self, chunk: MemoryChunk) -> None:
        """Add knowledge to the active persona's knowledge graph."""
        if not self._active_persona_id:
            raise RagQueryError("No active persona")
        persona = self._personas[self._active_persona_id]
        # Extract key from metadata or use chunk id
        key = chunk.metadata.get("topic", chunk.id)
        facts = chunk.text.split("\n") if "\n" in chunk.text else [chunk.text]
        importance = chunk.metadata.get("importance", 1.0)
        persona.add_knowledge(key, facts, importance)

    def query(
        self,
        query_text: str,
        *,
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[MemoryQueryResult]:
        if not self._active_persona_id:
            return []
        persona = self._personas[self._active_persona_id]
        context = persona.get_context_window(query_text)

        # Return the context as a single synthetic chunk
        chunk = MemoryChunk(
            id=f"cag_{self._active_persona_id}",
            text=context,
            metadata={"persona": persona.name, "tier": "cag"},
            source_tier="cag",
            confidence=1.0,
        )
        return [MemoryQueryResult(chunk=chunk, score=1.0, rank=1)]

    def delete(self, chunk_id: str) -> bool:
        # In CAG, deletion means removing a knowledge node from active persona
        if not self._active_persona_id:
            return False
        persona = self._personas[self._active_persona_id]
        for key in list(persona.knowledge_graph.keys()):
            if key == chunk_id or f"cag_{key}" == chunk_id:
                del persona.knowledge_graph[key]
                del persona.importance_scores[key]
                return True
        return False

    def health(self) -> Dict[str, Any]:
        return {
            "tier": "cag",
            "personas": len(self._personas),
            "active_persona": self._active_persona_id,
            "status": "healthy" if self._active_persona_id else "idle",
        }


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


# =============================================================================
# MEMORY TRINITY — CROSS-TIER FUSION
# =============================================================================

class MemoryTrinity:
    """
    Orchestrates RAG, CAG, and MAG into a unified context window.

    Fusion strategy:
      1. Query all three tiers in parallel (conceptually; here sequential for simplicity).
      2. Deduplicate by semantic similarity.
      3. Re-rank by tier-specific weights: RAG=0.4, CAG=0.3, MAG=0.3.
      4. Build unified context with token budget enforcement.
      5. Emit provenance chain for audit.
    """

    def __init__(
        self,
        rag: MemoryStore,
        cag: CAGStore,
        mag: MAGStore,
        *,
        bus: Optional[EventBus] = None,
        max_context_tokens: int = 8000,
    ) -> None:
        self.rag = rag
        self.cag = cag
        self.mag = mag
        self.bus = bus
        self.max_context_tokens = max_context_tokens
        self._tier_weights = {"rag": 0.4, "cag": 0.3, "mag": 0.3}

    def query_unified(
        self,
        query_text: str,
        *,
        top_k_per_tier: int = 3,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> UnifiedContext:
        """Query all tiers and fuse into unified context."""
        # Query each tier
        rag_results = self.rag.query(
            query_text, top_k=top_k_per_tier, metadata_filter=metadata_filter
        )
        cag_results = self.cag.query(
            query_text, top_k=top_k_per_tier, metadata_filter=metadata_filter
        )
        mag_results = self.mag.query(
            query_text, top_k=top_k_per_tier, metadata_filter=metadata_filter
        )

        # Apply tier weights
        for r in rag_results:
            r.fusion_contribution = r.score * self._tier_weights["rag"]
        for r in cag_results:
            r.fusion_contribution = r.score * self._tier_weights["cag"]
        for r in mag_results:
            r.fusion_contribution = r.score * self._tier_weights["mag"]

        # Deduplicate: if same text appears in multiple tiers, merge scores
        seen_texts: Dict[str, MemoryQueryResult] = {}
        for r in rag_results + cag_results + mag_results:
            text_hash = hashlib.sha256(r.chunk.text.encode()).hexdigest()[:16]
            if text_hash in seen_texts:
                seen_texts[text_hash].fusion_contribution += r.fusion_contribution
                seen_texts[text_hash].score = max(seen_texts[text_hash].score, r.score)
            else:
                seen_texts[text_hash] = r

        # Re-rank by fusion contribution
        all_results = sorted(seen_texts.values(), key=lambda x: x.fusion_contribution, reverse=True)

        # Build context within token budget
        tokens_used = 0
        context_parts: List[str] = []
        provenance: List[str] = []

        for r in all_results:
            text = f"[{r.chunk.source_tier.upper()}] {r.chunk.text}"
            tokens = len(text) // 4
            if tokens_used + tokens > self.max_context_tokens:
                break
            context_parts.append(text)
            tokens_used += tokens
            provenance.append(f"{r.chunk.source_tier}:{r.chunk.id}(score={r.score:.3f})")

        # Emit event
        if self.bus:
            self.bus.publish(
                DomainEvent(
                    topic="memory.trinity.query",
                    payload={
                        "query": query_text,
                        "tiers_queried": ["rag", "cag", "mag"],
                        "results_count": len(all_results),
                        "tokens_used": tokens_used,
                        "provenance": provenance,
                    },
                    correlation_id=f"mem_{hashlib.sha256(query_text.encode()).hexdigest()[:12]}",
                )
            )

        return UnifiedContext(
            facts=rag_results,
            persona_frame=cag_results,
            personal_history=mag_results,
            combined_score=sum(r.fusion_contribution for r in all_results),
            token_estimate=tokens_used,
            provenance_chain=provenance,
        )

    def health(self) -> Dict[str, Any]:
        return {
            "trinity": {
                "rag": self.rag.health(),
                "cag": self.cag.health(),
                "mag": self.mag.health(),
            },
            "max_context_tokens": self.max_context_tokens,
            "tier_weights": self._tier_weights,
            "status": "healthy",
        }
