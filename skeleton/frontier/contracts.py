"""Provider-neutral contracts used during frontier consolidation.

These protocols intentionally stay small. Concrete agent, memory, and provider
implementations can evolve without forcing application code to depend on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Traceability metadata for generated or promoted artifacts."""

    source_repository: str
    source_revision: str | None = None
    source_path: str | None = None
    operation: str = "consolidation"
    actor: str = "frontier"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-friendly provenance data."""
        return {
            "source_repository": self.source_repository,
            "source_revision": self.source_revision,
            "source_path": self.source_path,
            "operation": self.operation,
            "actor": self.actor,
            "timestamp": self.timestamp.isoformat(),
            "metadata": dict(self.metadata),
        }
