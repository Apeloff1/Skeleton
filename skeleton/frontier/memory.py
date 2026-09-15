"""In-process memory adapter and canonical MemoryContract normalization.

The reference implementation is deliberately dependency-free and deterministic.
Production stores consume the same normalized input and retrieval semantics so
storage concerns do not leak into the runtime contract.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from uuid import uuid4


_CONTENT_FIELDS = ("content", "text", "document")
_RESERVED_FIELDS = frozenset({"id", *_CONTENT_FIELDS, "metadata"})


@dataclass(frozen=True, slots=True)
class MemoryItem:
    id: str
    payload: Mapping[str, Any]


def normalize_memory_id(item: Mapping[str, Any]) -> str:
    """Return a canonical non-empty id, generating one only when absent."""

    raw_id = item.get("id")
    if raw_id is None:
        return str(uuid4())
    item_id = str(raw_id).strip()
    if not item_id:
        raise ValueError("memory id must not be empty")
    return item_id


def memory_content(item: Mapping[str, Any]) -> str:
    """Extract the canonical document text accepted by all memory backends."""

    for key in _CONTENT_FIELDS:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    raise ValueError("memory item requires non-empty content/text/document")


def _portable_json_value(
    value: Any,
    *,
    path: str,
    active_containers: set[int],
) -> Any:
    """Return a strict JSON-domain copy of one memory metadata value.

    Both the reference and persistent backends consume this normalized shape so
    values cannot change type merely because they crossed a JSON persistence
    boundary. Lists and objects are copied recursively, object keys must already
    be strings, numeric values must be finite, and cycles fail closed.
    """

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"memory metadata value at {path} must be finite")
        return value

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active_containers:
            raise ValueError(f"memory metadata at {path} must not contain cycles")
        active_containers.add(identity)
        try:
            normalized: dict[str, Any] = {}
            for key, child in value.items():
                if not isinstance(key, str):
                    raise TypeError(
                        f"memory metadata object key at {path} must be a string"
                    )
                normalized[key] = _portable_json_value(
                    child,
                    path=f"{path}.{key}",
                    active_containers=active_containers,
                )
            return normalized
        finally:
            active_containers.remove(identity)

    if isinstance(value, list):
        identity = id(value)
        if identity in active_containers:
            raise ValueError(f"memory metadata at {path} must not contain cycles")
        active_containers.add(identity)
        try:
            return [
                _portable_json_value(
                    child,
                    path=f"{path}[{index}]",
                    active_containers=active_containers,
                )
                for index, child in enumerate(value)
            ]
        finally:
            active_containers.remove(identity)

    raise TypeError(
        f"memory metadata value at {path} must be JSON-compatible, got {type(value).__name__}"
    )


def _portable_json_metadata(metadata: Mapping[Any, Any]) -> dict[str, Any]:
    normalized = _portable_json_value(
        metadata,
        path="metadata",
        active_containers=set(),
    )
    if not isinstance(normalized, dict):
        raise TypeError("memory metadata must normalize to an object")
    return normalized


def normalize_memory_metadata(metadata: Mapping[Any, Any]) -> dict[str, Any]:
    """Normalize one metadata object to the finite strict-JSON data model."""

    if not isinstance(metadata, Mapping):
        raise TypeError("memory metadata must be a mapping")
    return _portable_json_metadata(metadata)


def normalize_memory_filters(
    filters: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Normalize query filters using the same boundary as stored metadata.

    This prevents reference/persistent backend drift such as a tuple matching in
    memory while becoming a list after JSON persistence, and rejects non-finite
    numeric filters consistently before any backend query is executed.
    """

    if filters is None:
        return {}
    if not isinstance(filters, Mapping):
        raise TypeError("memory filters must be a mapping")
    return normalize_memory_metadata(filters)


def portable_memory_metadata(item: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten portable filter fields into one strict JSON metadata mapping.

    The promoted Prood/Tutolage RAG surface stores filter state as collection
    metadata while historical callers may put filterable fields at the top
    level. Conflicting representations fail closed rather than selecting one.
    Values are normalized to the JSON data model before either the reference or
    persistent backend sees them, preventing backend-specific type drift.
    """

    raw_metadata = item.get("metadata")
    if raw_metadata is None:
        metadata: dict[Any, Any] = {}
    elif isinstance(raw_metadata, Mapping):
        metadata = dict(raw_metadata)
    else:
        raise TypeError("memory item metadata must be a mapping")

    for key, value in item.items():
        if key in _RESERVED_FIELDS:
            continue
        if key in metadata and metadata[key] != value:
            raise ValueError(f"conflicting memory metadata field: {key}")
        metadata[key] = value
    return normalize_memory_metadata(metadata)


def normalize_memory_item(
    item: Mapping[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    """Normalize one MemoryContract input for any concrete backend."""

    if not isinstance(item, Mapping):
        raise TypeError("memory item must be a mapping")
    return (
        normalize_memory_id(item),
        memory_content(item),
        portable_memory_metadata(item),
    )


def lexical_relevance(document: str, query: str) -> float:
    """Return deterministic lexical relevance shared by reference/SQLite stores."""

    needle = query.casefold().strip()
    if not needle:
        return 1.0

    haystack = document.casefold()
    if needle in haystack:
        return 1.0

    terms = tuple(dict.fromkeys(re.findall(r"\w+", needle)))
    if not terms:
        return 1.0
    return sum(1 for term in terms if term in haystack) / len(terms)


def _matches_filters(
    metadata: Mapping[str, Any],
    filters: Mapping[str, Any],
) -> bool:
    return all(metadata.get(key) == expected for key, expected in filters.items())


class InMemoryStore:
    """Canonical dependency-free MemoryContract reference implementation."""

    def __init__(self) -> None:
        self._items: dict[str, MemoryItem] = {}
        self._sequence: dict[str, int] = {}
        self._next_sequence = 0

    async def put(self, item: Mapping[str, Any]) -> str:
        item_id, content, metadata = normalize_memory_item(item)
        self._next_sequence += 1
        self._items[item_id] = MemoryItem(
            item_id,
            {
                "id": item_id,
                "content": content,
                "metadata": metadata,
            },
        )
        self._sequence[item_id] = self._next_sequence
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

        where = normalize_memory_filters(filters)
        ranked: list[tuple[float, int, Mapping[str, Any]]] = []
        for item_id, item in self._items.items():
            payload = item.payload
            metadata = payload.get("metadata")
            if not isinstance(metadata, Mapping):
                continue
            if not _matches_filters(metadata, where):
                continue

            content = str(payload.get("content") or "")
            relevance = lexical_relevance(content, query)
            if query.strip() and relevance <= 0.0:
                continue
            ranked.append(
                (
                    relevance,
                    self._sequence[item_id],
                    {
                        "id": item_id,
                        "content": content,
                        "metadata": dict(metadata),
                        "relevance": relevance,
                    },
                )
            )

        ranked.sort(key=lambda candidate: (candidate[0], candidate[1]), reverse=True)
        return [candidate[2] for candidate in ranked[:limit]]

    async def delete(self, item_id: str) -> None:
        normalized = str(item_id).strip()
        if not normalized:
            raise ValueError("memory id must not be empty")
        self._items.pop(normalized, None)
        self._sequence.pop(normalized, None)
