"""Canonical retrieval boundary for frontier agent/runtime execution.

Storage backends implement ``MemoryContract``. Runtime consumers depend on the
smaller ``RetrieverContract`` defined here, so ranking/provenance policy stays
separate from persistence. Retrieval hits are normalized once, require a
traceable source, and expose a content-free audit shape for execution records.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from skeleton.frontier.contracts import MemoryContract, stable_content_digest
from skeleton.frontier.memory import normalize_memory_metadata


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"retrieval {field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"retrieval {field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"retrieval {field_name} must be normalized")
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


@dataclass(frozen=True, slots=True)
class RetrievedMemory:
    """One validated memory hit crossing into agent execution context."""

    item_id: str
    content: str
    metadata: Mapping[str, Any]
    source_repository: str
    source_revision: str | None = None
    source_path: str | None = None
    relevance: float | None = None

    def as_agent_context(self) -> dict[str, Any]:
        """Return the content-bearing shape supplied to the selected agent."""
        payload: dict[str, Any] = {
            "id": self.item_id,
            "content": self.content,
            "metadata": dict(self.metadata),
            "source": {
                "repository": self.source_repository,
                "revision": self.source_revision,
                "path": self.source_path,
            },
        }
        if self.relevance is not None:
            payload["relevance"] = self.relevance
        return payload

    def audit_summary(self) -> dict[str, Any]:
        """Return a content-free trace suitable for logs/provenance metadata."""
        payload: dict[str, Any] = {
            "id": self.item_id,
            "content_sha256": stable_content_digest(self.content),
            "source_repository": self.source_repository,
            "source_revision": self.source_revision,
            "source_path": self.source_path,
        }
        if self.relevance is not None:
            payload["relevance"] = self.relevance
        return payload


class RetrieverContract(Protocol):
    """Storage-neutral retrieval policy consumed by runtime composition."""

    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        filters: Mapping[str, Any] | None = None,
    ) -> Sequence[RetrievedMemory]: ...


def normalize_retrieval_hit(hit: Mapping[str, Any]) -> RetrievedMemory:
    """Validate one ``MemoryContract.search`` result fail-closed.

    Runtime retrieval is stricter than generic memory storage because content
    injected into an agent must remain attributable to an upstream source.
    ``source_repository`` is therefore mandatory in hit metadata while revision
    and path remain optional for sources that cannot provide finer granularity.
    """
    if not isinstance(hit, Mapping):
        raise TypeError("retrieval hit must be a mapping")

    item_id = _require_text(hit.get("id"), "hit id")
    content = _require_text(hit.get("content"), "hit content")

    raw_metadata = hit.get("metadata")
    if not isinstance(raw_metadata, Mapping):
        raise TypeError("retrieval hit metadata must be a mapping")
    metadata = normalize_memory_metadata(raw_metadata)

    raw_source_repository = metadata.get("source_repository")
    if raw_source_repository is None:
        raise ValueError("retrieval source_repository must not be empty")
    source_repository = _require_text(
        raw_source_repository,
        "source_repository",
    )
    source_revision = _optional_text(
        metadata.get("source_revision"),
        "source_revision",
    )
    source_path = _optional_text(metadata.get("source_path"), "source_path")

    relevance: float | None = None
    raw_relevance = hit.get("relevance")
    if raw_relevance is not None:
        if isinstance(raw_relevance, bool):
            raise TypeError("retrieval relevance must be numeric")
        try:
            relevance = float(raw_relevance)
        except (TypeError, ValueError) as exc:
            raise TypeError("retrieval relevance must be numeric") from exc
        if not math.isfinite(relevance):
            raise ValueError("retrieval relevance must be finite")
        if relevance < 0.0 or relevance > 1.0:
            raise ValueError("retrieval relevance must be between 0 and 1")

    return RetrievedMemory(
        item_id=item_id,
        content=content,
        metadata=metadata,
        source_repository=source_repository,
        source_revision=source_revision,
        source_path=source_path,
        relevance=relevance,
    )


async def retrieve_memory_context(
    memory: MemoryContract,
    query: str,
    *,
    limit: int = 5,
    filters: Mapping[str, Any] | None = None,
) -> tuple[RetrievedMemory, ...]:
    """Search one canonical memory backend and validate every returned hit."""
    normalized_query = _require_text(query, "query")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("retrieval limit must be an integer")
    if limit < 1:
        raise ValueError("retrieval limit must be positive")
    if filters is not None and not isinstance(filters, Mapping):
        raise TypeError("retrieval filters must be a mapping")

    raw_hits = await memory.search(
        normalized_query,
        limit=limit,
        filters=filters,
    )
    if isinstance(raw_hits, (str, bytes)):
        raise TypeError("memory search results must be a sequence of mappings")

    try:
        hits = tuple(raw_hits)
    except TypeError as exc:
        raise TypeError("memory search results must be iterable") from exc
    if len(hits) > limit:
        raise ValueError("memory backend returned more hits than requested")
    return tuple(normalize_retrieval_hit(hit) for hit in hits)


@dataclass(frozen=True, slots=True)
class MemoryRetriever:
    """Canonical retrieval policy over any ``MemoryContract`` backend."""

    memory: MemoryContract

    async def retrieve(
        self,
        query: str,
        *,
        limit: int = 5,
        filters: Mapping[str, Any] | None = None,
    ) -> tuple[RetrievedMemory, ...]:
        return await retrieve_memory_context(
            self.memory,
            query,
            limit=limit,
            filters=filters,
        )


def retrieval_audit_summary(
    hits: Sequence[RetrievedMemory],
) -> list[dict[str, Any]]:
    """Return stable digest/source metadata without retrieved document text."""
    return [hit.audit_summary() for hit in hits]
