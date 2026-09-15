"""Provider-neutral contracts used during frontier consolidation.

These protocols intentionally stay small. Concrete agent, memory, and provider
implementations can evolve without forcing application code to depend on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Mapping, Protocol, Sequence


class AgentContract(Protocol):
    """Minimal contract every promoted agent implementation must satisfy."""

    name: str
    capabilities: set[str]

    async def run(self, task: str, context: Mapping[str, Any] | None = None) -> Any:
        ...


class MemoryContract(Protocol):
    """Minimal asynchronous memory contract for RAG/CAG/MAG adapters."""

    async def put(self, item: Mapping[str, Any]) -> str:
        ...

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> Sequence[Mapping[str, Any]]:
        ...

    async def delete(self, item_id: str) -> None:
        ...


def stable_content_digest(payload: Any) -> str:
    """Return the frontier SHA-256 digest for an artifact-like payload.

    Mappings and JSON-compatible sequences are canonicalized so semantically
    identical payloads hash the same regardless of mapping insertion order.
    Bytes and strings are hashed directly. Non-JSON objects fall back to repr
    as a best-effort boundary rather than making provenance collection fatal.
    """

    if isinstance(payload, bytes):
        encoded = payload
    elif isinstance(payload, str):
        encoded = payload.encode("utf-8")
    else:
        try:
            encoded = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        except (TypeError, ValueError):
            encoded = repr(payload).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Traceability metadata for generated or promoted artifacts."""

    source_repository: str
    source_revision: str | None = None
    source_path: str | None = None
    operation: str = "consolidation"
    actor: str = "frontier"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    content_sha256: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def for_artifact(
        cls,
        *,
        source_repository: str,
        payload: Any,
        source_revision: str | None = None,
        source_path: str | None = None,
        operation: str = "consolidation",
        actor: str = "frontier",
        metadata: Mapping[str, Any] | None = None,
    ) -> "ProvenanceRecord":
        """Build provenance with the canonical frontier content digest."""

        return cls(
            source_repository=source_repository,
            source_revision=source_revision,
            source_path=source_path,
            operation=operation,
            actor=actor,
            content_sha256=stable_content_digest(payload),
            metadata=dict(metadata or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-friendly provenance data."""
        return {
            "source_repository": self.source_repository,
            "source_revision": self.source_revision,
            "source_path": self.source_path,
            "operation": self.operation,
            "actor": self.actor,
            "timestamp": self.timestamp.isoformat(),
            "content_sha256": self.content_sha256,
            "metadata": dict(self.metadata),
        }
