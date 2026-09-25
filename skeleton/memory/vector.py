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


def _unit_norm(vector: List[float]) -> float:
    if not vector:
        raise ValueError("embedding is required")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in vector
    ):
        raise ValueError("embedding values must be finite")
    norm = math.sqrt(sum(float(value) * float(value) for value in vector))
    if norm == 0.0:
        raise ValueError("embedding must be non-zero")
    return norm


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
        if not tokens:
            raise ValueError("text must contain a token")
        norm = _unit_norm(vec)
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
        use_asm_acceleration: bool = False,
        asm_accelerator: Any = None,
    ):
        self._embedder_fn: Callable[[str], List[float]] = embedder or HashEmbedder(dims).embed
        self._entries: Dict[str, VectorEntry] = {}
        self._stats = {"added": 0, "queries": 0}
        self._use_jvm_acceleration = bool(use_jvm_acceleration)
        self._accelerator = accelerator
        self._use_asm_acceleration = bool(use_asm_acceleration)
        self._asm_accelerator = asm_accelerator
        self._asm_revision = 0
        self._asm_prepared_cache: tuple[int, Any] | None = None
        self._acceleration = {
            "attempts": 0,
            "successes": 0,
            "fallbacks": 0,
            "bypassed_small_batch": 0,
            "batch_attempts": 0,
            "batch_successes": 0,
            "range_attempts": 0,
            "range_successes": 0,
        }
        self._asm_acceleration = {
            "attempts": 0,
            "successes": 0,
            "fallbacks": 0,
            "bypassed_small_batch": 0,
            "batch_attempts": 0,
            "batch_successes": 0,
            "range_attempts": 0,
            "range_successes": 0,
            "prepared_builds": 0,
            "prepared_hits": 0,
            "prepared_invalidations": 0,
        }

    def add(self, chunk: Chunk) -> None:
        vector = self._embedder_fn(chunk.text)
        norm = _unit_norm(vector)
        self._entries[chunk.chunk_id] = VectorEntry(chunk=chunk, vector=vector, norm=norm)
        self._stats["added"] += 1
        self._invalidate_asm_prepared_cache()

    def add_texts(self, texts: List[str], metadata: Optional[Dict[str, Any]] = None) -> int:
        for i, text in enumerate(texts):
            self.add(Chunk(text=text, chunk_id=f"vec-{len(self._entries)}-{i}", metadata=dict(metadata or {})))
        return len(texts)

    def query(self, text: str, top_k: int = 5, metadata_filter: Optional[Dict[str, Any]] = None) -> List[ScoredChunk]:
        self._stats["queries"] += 1
        if not self._entries:
            return []

        qv = self._embedder_fn(text)
        qnorm = _unit_norm(qv)
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

        if self._use_asm_acceleration and top_k > 0:
            try:
                asm_accelerator = self._resolve_asm_accelerator()
                minimum = int(getattr(asm_accelerator, "minimum_candidates", 1))
                if len(candidates) >= minimum:
                    self._asm_acceleration["attempts"] += 1
                    hits = self._asm_top_k(
                        asm_accelerator,
                        qv,
                        qnorm,
                        candidates,
                        min(top_k, len(candidates)),
                        metadata_filter=metadata_filter,
                    )
                    self._asm_acceleration["successes"] += 1
                    return [
                        ScoredChunk(
                            chunk=candidates[hit.index].chunk,
                            score=(hit.similarity + 1.0) / 2.0,
                            plane="rag",
                        )
                        for hit in hits
                    ]
                self._asm_acceleration["bypassed_small_batch"] += 1
            except Exception:
                self._asm_acceleration["fallbacks"] += 1

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
            norm = _unit_norm(vector)
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

        if self._use_asm_acceleration and top_k > 0:
            try:
                asm_accelerator = self._resolve_asm_accelerator()
                minimum = int(getattr(asm_accelerator, "minimum_candidates", 1))
                if len(candidates) >= minimum:
                    self._asm_acceleration["attempts"] += 1
                    self._asm_acceleration["batch_attempts"] += 1
                    batches = self._asm_top_k_many(
                        asm_accelerator,
                        embedded,
                        candidates,
                        min(top_k, len(candidates)),
                        metadata_filter=metadata_filter,
                    )
                    if len(batches) != len(embedded):
                        raise RuntimeError(
                            "Assembly accelerator returned wrong batch query count"
                        )
                    self._asm_acceleration["successes"] += 1
                    self._asm_acceleration["batch_successes"] += 1
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
                self._asm_acceleration["bypassed_small_batch"] += 1
            except Exception:
                self._asm_acceleration["fallbacks"] += 1

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

    def query_threshold(
        self,
        text: str,
        minimum_score: float,
        metadata_filter: Optional[Dict[str, Any]] = None,
        *,
        max_results: int = 10_000,
    ) -> List[ScoredChunk]:
        """Return all results meeting the normalized [0, 1] score threshold."""
        if (
            isinstance(minimum_score, bool)
            or not isinstance(minimum_score, (int, float))
            or not math.isfinite(float(minimum_score))
            or not 0.0 <= float(minimum_score) <= 1.0
        ):
            raise ValueError("minimum_score must be finite and within [0, 1]")
        if (
            isinstance(max_results, bool)
            or not isinstance(max_results, int)
            or max_results < 1
        ):
            raise ValueError("max_results must be a positive integer")

        self._stats["queries"] += 1
        if not self._entries:
            return []

        qv = self._embedder_fn(text)
        qnorm = _unit_norm(qv)
        candidates = [
            entry
            for entry in self._entries.values()
            if not metadata_filter or self._matches(entry.chunk.metadata, metadata_filter)
        ]
        if not candidates:
            return []

        cosine_threshold = float(minimum_score) * 2.0 - 1.0
        bounded_results = min(max_results, len(candidates))

        if self._use_jvm_acceleration:
            try:
                accelerator = self._resolve_accelerator()
                minimum = int(getattr(accelerator, "minimum_candidates", 1))
                if len(candidates) >= minimum:
                    self._acceleration["attempts"] += 1
                    self._acceleration["range_attempts"] += 1
                    hits = accelerator.range_search(
                        qv,
                        qnorm,
                        [(entry.vector, entry.norm) for entry in candidates],
                        cosine_threshold,
                        max_hits=bounded_results,
                    )
                    self._acceleration["successes"] += 1
                    self._acceleration["range_successes"] += 1
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

        if self._use_asm_acceleration:
            try:
                asm_accelerator = self._resolve_asm_accelerator()
                minimum = int(getattr(asm_accelerator, "minimum_candidates", 1))
                if len(candidates) >= minimum:
                    self._asm_acceleration["attempts"] += 1
                    self._asm_acceleration["range_attempts"] += 1
                    hits = self._asm_range_search(
                        asm_accelerator,
                        qv,
                        qnorm,
                        candidates,
                        cosine_threshold,
                        max_hits=bounded_results,
                        metadata_filter=metadata_filter,
                    )
                    self._asm_acceleration["successes"] += 1
                    self._asm_acceleration["range_successes"] += 1
                    return [
                        ScoredChunk(
                            chunk=candidates[hit.index].chunk,
                            score=(hit.similarity + 1.0) / 2.0,
                            plane="rag",
                        )
                        for hit in hits
                    ]
                self._asm_acceleration["bypassed_small_batch"] += 1
            except Exception:
                self._asm_acceleration["fallbacks"] += 1

        scored: List[Tuple[float, VectorEntry]] = []
        for entry in candidates:
            dot = sum(q * value for q, value in zip(qv, entry.vector))
            similarity = dot / (qnorm * entry.norm)
            if similarity + 1e-12 < cosine_threshold:
                continue
            scored.append((similarity, entry))
            if len(scored) > max_results:
                raise ValueError("threshold result bound exceeded")
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            ScoredChunk(
                chunk=entry.chunk,
                score=(similarity + 1.0) / 2.0,
                plane="rag",
            )
            for similarity, entry in scored
        ]

    def query_threshold_many(
        self,
        texts: List[str],
        minimum_score: float,
        metadata_filter: Optional[Dict[str, Any]] = None,
        *,
        max_total_results: int = 100_000,
    ) -> List[List[ScoredChunk]]:
        """Threshold-search many queries while reusing one candidate matrix."""
        if (
            isinstance(minimum_score, bool)
            or not isinstance(minimum_score, (int, float))
            or not math.isfinite(float(minimum_score))
            or not 0.0 <= float(minimum_score) <= 1.0
        ):
            raise ValueError("minimum_score must be finite and within [0, 1]")
        if (
            isinstance(max_total_results, bool)
            or not isinstance(max_total_results, int)
            or max_total_results < 1
        ):
            raise ValueError("max_total_results must be a positive integer")

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
            norm = _unit_norm(vector)
            embedded.append((vector, norm))

        cosine_threshold = float(minimum_score) * 2.0 - 1.0
        if self._use_jvm_acceleration:
            try:
                accelerator = self._resolve_accelerator()
                minimum = int(getattr(accelerator, "minimum_candidates", 1))
                if len(candidates) >= minimum:
                    self._acceleration["attempts"] += 1
                    self._acceleration["range_attempts"] += 1
                    batches = accelerator.range_search_many(
                        embedded,
                        [(entry.vector, entry.norm) for entry in candidates],
                        cosine_threshold,
                        max_total_hits=max_total_results,
                    )
                    if len(batches) != len(embedded):
                        raise RuntimeError("accelerator returned wrong range batch count")
                    self._acceleration["successes"] += 1
                    self._acceleration["range_successes"] += 1
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

        if self._use_asm_acceleration:
            try:
                asm_accelerator = self._resolve_asm_accelerator()
                minimum = int(getattr(asm_accelerator, "minimum_candidates", 1))
                if len(candidates) >= minimum:
                    self._asm_acceleration["attempts"] += 1
                    self._asm_acceleration["range_attempts"] += 1
                    batches = self._asm_range_search_many(
                        asm_accelerator,
                        embedded,
                        candidates,
                        cosine_threshold,
                        max_total_hits=max_total_results,
                        metadata_filter=metadata_filter,
                    )
                    if len(batches) != len(embedded):
                        raise RuntimeError(
                            "Assembly accelerator returned wrong range batch count"
                        )
                    self._asm_acceleration["successes"] += 1
                    self._asm_acceleration["range_successes"] += 1
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
                self._asm_acceleration["bypassed_small_batch"] += 1
            except Exception:
                self._asm_acceleration["fallbacks"] += 1

        output: List[List[ScoredChunk]] = []
        total = 0
        for query_vector, query_norm in embedded:
            scored: List[Tuple[float, VectorEntry]] = []
            for entry in candidates:
                dot = sum(q * value for q, value in zip(query_vector, entry.vector))
                similarity = dot / (query_norm * entry.norm)
                if similarity + 1e-12 < cosine_threshold:
                    continue
                total += 1
                if total > max_total_results:
                    raise ValueError("threshold batch result bound exceeded")
                scored.append((similarity, entry))
            scored.sort(key=lambda item: item[0], reverse=True)
            output.append(
                [
                    ScoredChunk(
                        chunk=entry.chunk,
                        score=(similarity + 1.0) / 2.0,
                        plane="rag",
                    )
                    for similarity, entry in scored
                ]
            )
        return output
    def delete(self, chunk_id: str) -> bool:
        removed = self._entries.pop(chunk_id, None) is not None
        if removed:
            self._invalidate_asm_prepared_cache()
        return removed

    @staticmethod
    def _matches(metadata: Dict[str, Any], filt: Dict[str, Any]) -> bool:
        return all(metadata.get(k) == v for k, v in filt.items())

    def acceleration_stats(self) -> Dict[str, int | bool]:
        """Return optional fast-path counters without changing store stats."""
        return {
            "enabled": self._use_jvm_acceleration,
            **self._acceleration,
            "asm_enabled": self._use_asm_acceleration,
            **{
                f"asm_{name}": value
                for name, value in self._asm_acceleration.items()
            },
        }

    def _resolve_accelerator(self) -> Any:
        if self._accelerator is None:
            from skeleton.memory.jvm_vector_accelerator import get_default_vector_accelerator

            self._accelerator = get_default_vector_accelerator()
        return self._accelerator

    def _resolve_asm_accelerator(self) -> Any:
        if self._asm_accelerator is None:
            from skeleton.memory.asm_vector_accelerator import (
                get_default_asm_vector_accelerator,
            )

            self._asm_accelerator = get_default_asm_vector_accelerator()
        return self._asm_accelerator

    def _invalidate_asm_prepared_cache(self) -> None:
        self._asm_revision += 1
        if self._asm_prepared_cache is not None:
            self._asm_acceleration["prepared_invalidations"] += 1
            self._asm_prepared_cache = None

    def _asm_candidate_payload(
        self,
        accelerator: Any,
        candidates: List[VectorEntry],
        *,
        metadata_filter: Optional[Dict[str, Any]],
    ) -> tuple[Any | None, List[Tuple[List[float], float]]]:
        raw = [(entry.vector, entry.norm) for entry in candidates]
        prepare = getattr(accelerator, "prepare_candidates", None)
        if not callable(prepare):
            return None, raw

        if metadata_filter:
            prepared = prepare(raw)
            self._asm_acceleration["prepared_builds"] += 1
            return prepared, raw

        cache = self._asm_prepared_cache
        if cache is not None and cache[0] == self._asm_revision:
            self._asm_acceleration["prepared_hits"] += 1
            return cache[1], raw

        prepared = prepare(raw)
        self._asm_acceleration["prepared_builds"] += 1
        self._asm_prepared_cache = (self._asm_revision, prepared)
        return prepared, raw

    def _asm_top_k(
        self,
        accelerator: Any,
        query: List[float],
        query_norm: float,
        candidates: List[VectorEntry],
        top_k: int,
        *,
        metadata_filter: Optional[Dict[str, Any]],
    ) -> Any:
        prepared, raw = self._asm_candidate_payload(
            accelerator,
            candidates,
            metadata_filter=metadata_filter,
        )
        prepared_method = getattr(accelerator, "top_k_prepared", None)
        if prepared is not None and callable(prepared_method):
            return prepared_method(query, query_norm, prepared, top_k)
        return accelerator.top_k(query, query_norm, raw, top_k)

    def _asm_top_k_many(
        self,
        accelerator: Any,
        queries: List[Tuple[List[float], float]],
        candidates: List[VectorEntry],
        top_k: int,
        *,
        metadata_filter: Optional[Dict[str, Any]],
    ) -> Any:
        prepared, raw = self._asm_candidate_payload(
            accelerator,
            candidates,
            metadata_filter=metadata_filter,
        )
        prepared_method = getattr(accelerator, "top_k_many_prepared", None)
        if prepared is not None and callable(prepared_method):
            return prepared_method(queries, prepared, top_k)
        return accelerator.top_k_many(queries, raw, top_k)

    def _asm_range_search(
        self,
        accelerator: Any,
        query: List[float],
        query_norm: float,
        candidates: List[VectorEntry],
        threshold: float,
        *,
        max_hits: int,
        metadata_filter: Optional[Dict[str, Any]],
    ) -> Any:
        prepared, raw = self._asm_candidate_payload(
            accelerator,
            candidates,
            metadata_filter=metadata_filter,
        )
        prepared_method = getattr(accelerator, "range_search_prepared", None)
        if prepared is not None and callable(prepared_method):
            return prepared_method(
                query,
                query_norm,
                prepared,
                threshold,
                max_hits=max_hits,
            )
        return accelerator.range_search(
            query,
            query_norm,
            raw,
            threshold,
            max_hits=max_hits,
        )

    def _asm_range_search_many(
        self,
        accelerator: Any,
        queries: List[Tuple[List[float], float]],
        candidates: List[VectorEntry],
        threshold: float,
        *,
        max_total_hits: int,
        metadata_filter: Optional[Dict[str, Any]],
    ) -> Any:
        prepared, raw = self._asm_candidate_payload(
            accelerator,
            candidates,
            metadata_filter=metadata_filter,
        )
        prepared_method = getattr(
            accelerator,
            "range_search_many_prepared",
            None,
        )
        if prepared is not None and callable(prepared_method):
            return prepared_method(
                queries,
                prepared,
                threshold,
                max_total_hits=max_total_hits,
            )
        return accelerator.range_search_many(
            queries,
            raw,
            threshold,
            max_total_hits=max_total_hits,
        )

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "documents": len(self._entries),
            "dimensions": len(self._embedder_fn("probe")),
        }
