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

    def __init__(self, embedder: Optional[Callable[[str], List[float]]] = None, dims: int = 256):
        self._embedder_fn: Callable[[str], List[float]] = embedder or HashEmbedder(dims).embed
        self._entries: Dict[str, VectorEntry] = {}
        self._stats = {"added": 0, "queries": 0}

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

        scored: List[Tuple[float, VectorEntry]] = []
        for entry in self._entries.values():
            if metadata_filter and not self._matches(entry.chunk.metadata, metadata_filter):
                continue
            dot = sum(q * v for q, v in zip(qv, entry.vector))
            sim = dot / (qnorm * entry.norm)
            scored.append((sim, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            ScoredChunk(chunk=e.chunk, score=(sim + 1.0) / 2.0, plane="rag")  # map [-1,1] -> [0,1]
            for sim, e in scored[:top_k]
        ]

    def delete(self, chunk_id: str) -> bool:
        return self._entries.pop(chunk_id, None) is not None

    @staticmethod
    def _matches(metadata: Dict[str, Any], filt: Dict[str, Any]) -> bool:
        return all(metadata.get(k) == v for k, v in filt.items())

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "documents": len(self._entries),
            "dimensions": len(self._embedder_fn("probe")),
        }
