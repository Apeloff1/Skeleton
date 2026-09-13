"""In-process memory adapter for the frontier contract.

This is deliberately dependency-free and deterministic. Production stores can
implement the same MemoryContract without leaking storage concerns into the
runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class MemoryItem:
    id: str
    payload: Mapping[str, Any]


class InMemoryStore:
    """Small reference implementation suitable for tests and local runs."""

    def __init__(self) -> None:
        self._items: dict[str, MemoryItem] = {}

    async def put(self, item: Mapping[str, Any]) -> str:
        item_id = str(item.get("id") or uuid4())
        self._items[item_id] = MemoryItem(item_id, dict(item))
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
        needle = query.casefold().strip()
        filters = filters or {}
        hits: list[Mapping[str, Any]] = []
        for item in self._items.values():
            if any(item.payload.get(k) != v for k, v in filters.items()):
                continue
            haystack = repr(dict(item.payload)).casefold()
            if not needle or needle in haystack:
                hits.append(dict(item.payload))
            if len(hits) >= limit:
                break
        return hits

    async def delete(self, item_id: str) -> None:
        self._items.pop(item_id, None)
