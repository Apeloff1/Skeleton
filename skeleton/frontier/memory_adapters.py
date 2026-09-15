"""Boundary adapters for promoted memory implementations.

The Prood/Tutolage RAG implementation uses a Chroma-style synchronous
collection API. This module preserves those useful collection/query semantics
without importing ChromaDB or its application service into the frontier kernel.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4


class CollectionLike(Protocol):
    """Small structural contract matching the promoted RAG collection surface."""

    def add(
        self,
        *,
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, Any]],
        ids: Sequence[str],
    ) -> Any:
        ...

    def query(
        self,
        *,
        query_texts: Sequence[str],
        n_results: int,
        where: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        ...

    def delete(
        self,
        *,
        ids: Sequence[str] | None = None,
        where: Mapping[str, Any] | None = None,
    ) -> Any:
        ...


def _first_row(value: Any) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    if not value:
        return []
    first = value[0]
    if isinstance(first, Sequence) and not isinstance(first, (str, bytes)):
        return list(first)
    return list(value)


@dataclass(slots=True)
class CollectionMemoryAdapter:
    """Adapt a Chroma-like collection to ``MemoryContract``.

    Input items intentionally use a tiny portable shape: ``id`` is optional,
    content may be supplied as ``content``, ``text`` or ``document``, and
    source-specific filtering data lives under ``metadata``. Search results
    preserve source ids, metadata and relevance when available.
    """

    collection: CollectionLike

    @staticmethod
    def _content(item: Mapping[str, Any]) -> str:
        for key in ("content", "text", "document"):
            value = item.get(key)
            if value is not None:
                text = str(value).strip()
                if text:
                    return text
        raise ValueError("memory item requires non-empty content/text/document")

    async def put(self, item: Mapping[str, Any]) -> str:
        item_id = str(item.get("id") or uuid4())
        metadata = item.get("metadata") or {}
        if not isinstance(metadata, Mapping):
            raise TypeError("memory item metadata must be a mapping")
        content = self._content(item)
        await asyncio.to_thread(
            self.collection.add,
            documents=[content],
            metadatas=[dict(metadata)],
            ids=[item_id],
        )
        return item_id

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        if limit < 1:
            return []
        raw = await asyncio.to_thread(
            self.collection.query,
            query_texts=[query],
            n_results=limit,
            where=dict(filters) if filters else None,
        )
        documents = _first_row(raw.get("documents", []))
        metadatas = _first_row(raw.get("metadatas", []))
        ids = _first_row(raw.get("ids", []))
        distances = _first_row(raw.get("distances", []))

        hits: list[Mapping[str, Any]] = []
        for index, document in enumerate(documents[:limit]):
            hit: dict[str, Any] = {"content": document}
            if index < len(ids):
                hit["id"] = ids[index]
            if index < len(metadatas):
                hit["metadata"] = metadatas[index] or {}
            if index < len(distances):
                try:
                    hit["relevance"] = 1.0 - float(distances[index])
                except (TypeError, ValueError):
                    pass
            hits.append(hit)
        return hits

    async def delete(self, item_id: str) -> None:
        await asyncio.to_thread(self.collection.delete, ids=[item_id])
