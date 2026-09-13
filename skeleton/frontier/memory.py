"""In-process memory adapter for the frontier contract.

This is deliberately dependency-free and deterministic. Production stores can
implement the same MemoryContract without leaking storage concerns into the
runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from uuid import uuid4

from skeleton.frontier.execution import positive_int
from skeleton.frontier.payloads import json_snapshot, memory_payload


@dataclass(frozen=True, slots=True)
class MemoryItem:
    id: str
    payload: Mapping[str, Any]


class InMemoryStore:
    """Small reference implementation suitable for tests and local runs."""

    def __init__(self, *, capacity: int = 10_000, max_payload_bytes: int = 1_048_576) -> None:
        self.capacity = positive_int("capacity", capacity)
        self.max_payload_bytes = positive_int("max_payload_bytes", max_payload_bytes)
        self._items: dict[str, MemoryItem] = {}

    async def put(self, item: Mapping[str, Any]) -> str:
        item_id = item.get("id", str(uuid4()))
        payload = memory_payload(item, item_id, self.max_payload_bytes)
        if item_id not in self._items and len(self._items) >= self.capacity:
            raise OverflowError("memory store capacity reached")
        self._items[item_id] = MemoryItem(item_id, payload)
        return item_id

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        positive_int("limit", limit, minimum=0)
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        if limit == 0:
            return []
        needle = query.casefold().strip()
        filters = json_snapshot(dict(filters or {}), max_bytes=self.max_payload_bytes)
        hits: list[Mapping[str, Any]] = []
        for item in sorted(self._items.values(), key=lambda value: value.id):
            if any(item.payload.get(k) != v for k, v in filters.items()):
                continue
            haystack = repr(dict(item.payload)).casefold()
            if not needle or needle in haystack:
                hits.append(json_snapshot(item.payload, max_bytes=self.max_payload_bytes))
            if len(hits) >= limit:
                break
        return hits

    async def delete(self, item_id: str) -> None:
        self._items.pop(item_id, None)
