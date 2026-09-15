"""Jeeves retrieval-augmented memory.

ChromaDB-backed vector memory with a transparent in-memory fallback so the
tutor works (and tests pass) without a running Chroma server. Documents are
embedded with a deterministic local hashing embedder when no embedding
function is supplied.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any

from skeleton.kernel.events import EventBus
from skeleton.kernel.ids import MemoryId

_DIM = 64


def _local_embed(text: str) -> list[float]:
    """Deterministic bag-of-hashes embedding — no network, stable."""
    vec = [0.0] * _DIM
    for token in text.lower().split():
        h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        vec[h % _DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass
class MemoryItem:
    memory_id: str
    text: str
    metadata: dict[str, Any]
    embedding: list[float] = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {"memory_id": self.memory_id, "text": self.text, "metadata": self.metadata}


class _FallbackStore:
    """In-memory cosine-similarity store used when ChromaDB is unavailable."""

    def __init__(self) -> None:
        self._items: dict[str, MemoryItem] = {}

    def add(self, item: MemoryItem) -> None:
        self._items[item.memory_id] = item

    def query(self, embedding: list[float], k: int) -> list[MemoryItem]:
        scored = sorted(self._items.values(),
                        key=lambda it: _cosine(it.embedding, embedding), reverse=True)
        return scored[:k]

    def __len__(self) -> int:
        return len(self._items)


class RagMemory:
    """Retrieval-augmented memory for Jeeves."""

    def __init__(self, bus: EventBus | None = None,
                 *, chroma_client: Any | None = None,
                 collection: str = "skeleton_memory",
                 embedder: Any | None = None) -> None:
        self._bus = bus or EventBus()
        self._embed = embedder or _local_embed
        self._fallback = _FallbackStore()
        self._collection = None
        if chroma_client is not None:
            try:
                self._collection = chroma_client.get_or_create_collection(collection)
            except Exception:  # noqa: BLE001 - fall through to local store
                self._collection = None

    @property
    def backend(self) -> str:
        return "chromadb" if self._collection is not None else "local"

    def remember(self, text: str, *, metadata: dict[str, Any] | None = None) -> MemoryItem:
        item = MemoryItem(memory_id=str(MemoryId.new()), text=text,
                          metadata=dict(metadata or {}), embedding=self._embed(text))
        if self._collection is not None:
            try:
                self._collection.add(ids=[item.memory_id], documents=[text],
                                     metadatas=[item.metadata], embeddings=[item.embedding])
            except Exception:  # noqa: BLE001
                self._fallback.add(item)
        else:
            self._fallback.add(item)
        self._bus.emit("jeeves.memory.stored",
                       {"memory_id": item.memory_id, "backend": self.backend})
        return item

    def recall(self, query: str, *, k: int = 5) -> list[MemoryItem]:
        embedding = self._embed(query)
        if self._collection is not None:
            try:
                res = self._collection.query(query_embeddings=[embedding], n_results=k)
                ids = res["ids"][0]
                docs = res["documents"][0]
                metas = res.get("metadatas", [[None] * len(ids)])[0]
                items = [
                    MemoryItem(memory_id=i, text=d, metadata=m or {}, embedding=[])
                    for i, d, m in zip(ids, docs, metas)
                ]
                self._bus.emit("jeeves.memory.recalled",
                               {"k": k, "hits": len(items), "backend": "chromadb"})
                return items
            except Exception:  # noqa: BLE001
                pass
        items = self._fallback.query(embedding, k)
        self._bus.emit("jeeves.memory.recalled",
                       {"k": k, "hits": len(items), "backend": "local"})
        return items

    def __len__(self) -> int:
        if self._collection is not None:
            try:
                return int(self._collection.count())
            except Exception:  # noqa: BLE001
                pass
        return len(self._fallback)
