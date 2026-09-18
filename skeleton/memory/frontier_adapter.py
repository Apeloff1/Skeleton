"""Compatibility bridge from legacy synchronous memory stores to Frontier.

This module intentionally lives beside the legacy ``skeleton.memory`` stack:
the canonical Frontier layer does not import old storage implementations. Legacy
RAG/CAG/MAG stores can migrate behind ``MemoryContract`` through this adapter
while callers move to ``skeleton.frontier.retrieval_context``.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from skeleton.frontier.memory import (
    normalize_memory_filters,
    normalize_memory_item,
    normalize_memory_metadata,
)
from skeleton.memory.store import MemoryStore
from skeleton.memory.types import MemoryChunk, MemoryQueryResult


def _normalized_query(query: object) -> str:
    if not isinstance(query, str):
        raise TypeError("memory query must be a string")
    return query.strip()


def _normalized_limit(limit: object) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("memory search limit must be an integer")
    return limit


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"legacy memory {field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"legacy memory {field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"legacy memory {field_name} must be normalized")
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _normalized_relevance(value: object, *, empty_query: bool) -> float:
    if empty_query:
        return 1.0
    if isinstance(value, bool):
        raise TypeError("legacy memory score must be numeric")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError("legacy memory score must be numeric") from exc
    if not math.isfinite(score):
        raise ValueError("legacy memory score must be finite")
    if score < 0.0 or score > 1.0:
        raise ValueError("legacy memory score must be between 0 and 1")
    return score


@dataclass(slots=True)
class LegacyMemoryStoreAdapter:
    """Expose one synchronous ``MemoryStore`` through async ``MemoryContract``.

    ``source_repository`` is required because canonical runtime retrieval is
    fail-closed on unattributed context. Optional revision/path defaults let a
    migration preserve finer lineage while item-specific metadata, when present,
    remains authoritative.
    """

    store: MemoryStore
    source_repository: str
    source_tier: str = "legacy"
    source_revision: str | None = None
    source_path: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.source_repository, "source_repository")
        _required_text(self.source_tier, "source_tier")
        _optional_text(self.source_revision, "source_revision")
        _optional_text(self.source_path, "source_path")

    def _with_source_defaults(self, metadata: Mapping[str, Any]) -> dict[str, Any]:
        normalized = normalize_memory_metadata(metadata)
        normalized.setdefault("source_repository", self.source_repository)
        if self.source_revision is not None:
            normalized.setdefault("source_revision", self.source_revision)
        if self.source_path is not None:
            normalized.setdefault("source_path", self.source_path)
        return normalized

    async def put(self, item: Mapping[str, Any]) -> str:
        item_id, content, metadata = normalize_memory_item(item)
        chunk = MemoryChunk(
            id=item_id,
            text=content,
            metadata=self._with_source_defaults(metadata),
            source_tier=self.source_tier,
        )
        await asyncio.to_thread(self.store.add, chunk)
        return item_id

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        normalized_query = _normalized_query(query)
        normalized_limit = _normalized_limit(limit)
        if normalized_limit < 1:
            return []
        where = normalize_memory_filters(filters)

        results = await asyncio.to_thread(
            self.store.query,
            normalized_query,
            top_k=normalized_limit,
            metadata_filter=where or None,
            min_score=0.0,
        )
        if isinstance(results, (str, bytes)):
            raise TypeError("legacy memory query must return result objects")

        normalized_results: list[dict[str, Any]] = []
        for result in results:
            if not isinstance(result, MemoryQueryResult):
                raise TypeError("legacy memory query returned an unexpected result type")
            chunk = result.chunk
            item_id = str(chunk.id).strip()
            if not item_id:
                raise ValueError("legacy memory result id must not be empty")
            content = str(chunk.text).strip()
            if not content:
                raise ValueError("legacy memory result content must not be empty")
            metadata = self._with_source_defaults(chunk.metadata)
            metadata.setdefault("source_tier", chunk.source_tier or self.source_tier)
            relevance = _normalized_relevance(
                result.score,
                empty_query=not normalized_query,
            )
            if normalized_query and relevance <= 0.0:
                continue
            normalized_results.append(
                {
                    "id": item_id,
                    "content": content,
                    "metadata": metadata,
                    "relevance": relevance,
                }
            )
            if len(normalized_results) >= normalized_limit:
                break
        return normalized_results

    async def delete(self, item_id: str) -> None:
        normalized = str(item_id).strip()
        if not normalized:
            raise ValueError("memory id must not be empty")
        await asyncio.to_thread(self.store.delete, normalized)