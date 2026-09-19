"""
Skeleton Memory — Vector embedding store (dense RAG plane)

Provides:
- HashEmbedder: Deterministic local embedding (no external model needed)
- VectorStore: Cosine-similarity dense retrieval with metadata filters

The embedder is intentionally dependency-free: a hashing trick maps
tokens into a fixed-dimension space, giving stable vectors that work
out of the box. Swap in a real model (sentence-transformers, OpenAI)
by implementing the same `embed(text) -> list[float]` interface.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.memory.core import Chunk, ScoredChunk


class HashEmbedder:
    """Deterministic local embedder via feature hashing.

    Each token hashes into `dims` buckets with sign; the bag-of-hashes
    vector is L2-normalized. Deterministic, offline, zero-dependency.
    """

    def __init__(self, dims: int = 256):
        self.dims = dims

    def embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dims
        tokens = self._tokenize(text)
        for token in tokens:
            h = int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big")
            idx = h % self.dims
            sign = 1.0 if (h >> 63) & 1 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        words = [t.lower().strip(".,!?;:()[]{}\"'") for t in text.split()]
        words = [w for w in words if len(w) > 1]
        # Unigrams + bigrams for phrase sensitivity
        bigrams = [f"{words[i]}_{words[i+1]}" for i in range(len(words) - 1)]
        return words + bigrams


@dataclass
class VectorEntry:
    chunk: Chunk
    vector: List[float]
    norm: float


class VectorStore:
    """Dense retrieval store with cosine similarity.

    Compatible with the RAG plane interface (`add`, `query`, `stats`),
    so MemoryTrinity and QuadRetriever can use it as a drop-in upgrade
    over InMemoryTFIDFStore.
    """

    def __init__(
        self,
        embedder: Optional[Callable[[str], List[float]]] = None,
        dims: int = 256,
        *,
        use_jvm_acceleration: bool = False,
        accelerator: Any = None,
    ):
        self._embedder_fn: Callable[[str], List[float]] = embedder or HashEmbedder(dims).embed
        self._entries: Dict[str, VectorEntry] = {}
        self._stats = {"added": 0, "queries": 0}
        self._use_jvm_acceleration = bool(use_jvm_acceleration)
        self._accelerator = accelerator
        self._acceleration = {
            "attempts": 0,
            "successes": 0,
            "fallbacks": 0,
            "bypassed_small_batch": 0,
            "batch_attempts": 0,
            "batch_successes": 0,
        }

    def add(self, chunk: Chunk) -> None:
        vector = self._embedder_fn(chunk.text)
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        self._entries[chunk.chunk_id] = VectorEntry(chunk=chunk, vector=vector, norm=norm)
        self._stats["added"] += 1

    def add_texts(self, texts: List[str], metadata: Optional[Dict[str, Any]] = None) -> int:
        for i, text in enumerate(texts):
            self.add(Chunk(text=text, chunk_id=f"vec-{len(self._entries)}-{i}", metadata=dict(metadata or {})))
        return len(texts)

    def query(self, text: str, top_k: int = 5, metadata_filter: Optional[Dict[str, Any]] = None) -> List[ScoredChunk]:
        self._stats["queries"] += 1
        if not self._entries:
            return []

        qv = self._embedder_fn(text)
        qnorm = math.sqrt(sum(v * v for v in qv)) or 1.0
        candidates = [
            entry
            for entry in self._entries.values()
            if not metadata_filter or self._matches(entry.chunk.metadata, metadata_filter)
        ]
        if not candidates:
            return []

        if self._use_jvm_acceleration and top_k > 0:
            try:
                accelerator = self._resolve_accelerator()
                minimum = int(getattr(accelerator, "minimum_candidates", 1))
                if len(candidates) >= minimum:
                    self._acceleration["attempts"] += 1
                    hits = accelerator.top_k(
                        qv,
                        qnorm,
                        [(entry.vector, entry.norm) for entry in candidates],
                        min(top_k, len(candidates)),
                    )
                    self._acceleration["successes"] += 1
                    return [
                        ScoredChunk(
                            chunk=candidates[hit.index].chunk,
                            score=(hit.similarity + 1.0) / 2.0,
                            plane="rag",
                        )
                        for hit in hits
                    ]
                self._acceleration["bypassed_small_batch"] += 1
            except Exception:
                self._acceleration["fallbacks"] += 1

        scored: List[Tuple[float, VectorEntry]] = []
        for entry in candidates:
            dot = sum(q * v for q, v in zip(qv, entry.vector))
            sim = dot / (qnorm * entry.norm)
            scored.append((sim, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            ScoredChunk(chunk=e.chunk, score=(sim + 1.0) / 2.0, plane="rag")  # map [-1,1] -> [0,1]
            for sim, e in scored[:top_k]
        ]

    def query_many(
        self,
        texts: List[str],
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[List[ScoredChunk]]:
        """Query many texts against one candidate snapshot.

        When JVM acceleration is enabled and the candidate set is large enough,
        all query embeddings share one candidate-matrix transfer. Python still
        owns embedding, metadata filtering, stable result construction, stats,
        and the complete fallback path.
        """
        queries = list(texts)
        if not queries:
            return []

        self._stats["queries"] += len(queries)
        if not self._entries:
            return [[] for _ in queries]

        candidates = [
            entry
            for entry in self._entries.values()
            if not metadata_filter or self._matches(entry.chunk.metadata, metadata_filter)
        ]
        if not candidates:
            return [[] for _ in queries]

        embedded: List[Tuple[List[float], float]] = []
        for text in queries:
            vector = self._embedder_fn(text)
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            embedded.append((vector, norm))

        if self._use_jvm_acceleration and top_k > 0:
            try:
                accelerator = self._resolve_accelerator()
                minimum = int(getattr(accelerator, "minimum_candidates", 1))
                if len(candidates) >= minimum:
                    self._acceleration["attempts"] += 1
                    self._acceleration["batch_attempts"] += 1
                    batches = accelerator.top_k_many(
                        embedded,
                        [(entry.vector, entry.norm) for entry in candidates],
                        min(top_k, len(candidates)),
                    )
                    if len(batches) != len(embedded):
                        raise RuntimeError("accelerator returned wrong batch query count")
                    self._acceleration["successes"] += 1
                    self._acceleration["batch_successes"] += 1
                    return [
                        [
                            ScoredChunk(
                                chunk=candidates[hit.index].chunk,
                                score=(hit.similarity + 1.0) / 2.0,
                                plane="rag",
                            )
                            for hit in hits
                        ]
                        for hits in batches
                    ]
                self._acceleration["bypassed_small_batch"] += 1
            except Exception:
                self._acceleration["fallbacks"] += 1

        output: List[List[ScoredChunk]] = []
        for query_vector, query_norm in embedded:
            scored: List[Tuple[float, VectorEntry]] = []
            for entry in candidates:
                dot = sum(q * value for q, value in zip(query_vector, entry.vector))
                similarity = dot / (query_norm * entry.norm)
                scored.append((similarity, entry))
            scored.sort(key=lambda item: item[0], reverse=True)
            output.append(
                [
                    ScoredChunk(
                        chunk=entry.chunk,
                        score=(similarity + 1.0) / 2.0,
                        plane="rag",
                    )
                    for similarity, entry in scored[:top_k]
                ]
            )
        return output

    def delete(self, chunk_id: str) -> bool:
        return self._entries.pop(chunk_id, None) is not None

    @staticmethod
    def _matches(metadata: Dict[str, Any], filt: Dict[str, Any]) -> bool:
        return all(metadata.get(k) == v for k, v in filt.items())

    def acceleration_stats(self) -> Dict[str, int | bool]:
        """Return optional JVM fast-path counters without changing store stats."""
        return {
            "enabled": self._use_jvm_acceleration,
            **self._acceleration,
        }

    def _resolve_accelerator(self) -> Any:
        if self._accelerator is None:
            from skeleton.memory.jvm_vector_accelerator import get_default_vector_accelerator

            self._accelerator = get_default_vector_accelerator()
        return self._accelerator

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "documents": len(self._entries),
            "dimensions": len(self._embedder_fn("probe")),
        }
