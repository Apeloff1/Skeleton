"""Δ-Memory as a derived memory projection (memory-hex adapter).

Plugs any ``DeltaMemoryPort`` into ``MemoryProjectionCoordinator`` as a
one-way canonical → projection target, alongside the TF-IDF / vector / CAG /
MAG adapters in ``skeleton.memory.projection``. Canonical ``MemoryRecord``
state stays authoritative; this store is disposable and rebuildable.

Semantics:
- ``upsert`` of an ACTIVE record writes a JSON-friendly entry keyed by
  ``memory_id``; non-ACTIVE records are deleted (tombstoned) instead.
- Version guard: an upsert whose ``version`` is not newer than the stored
  entry is skipped, so out-of-order or replayed dispatch cannot regress
  the projection. Equal-version replays are idempotent no-ops.
- ``content_ref`` records are projected as refs (no dereferencing), unlike
  retrieval projections which require inline content.
- Not a retrieval plane: no ``governance_plane`` attribute, so it is not
  lifecycle-bound by the coordinator.

Kept out of ``projection.py`` (extend-only; that module is shared) and only
depends on the canonical record contract plus the Δ-Memory port.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from skeleton.contracts.memory_record import MemoryRecord, MemoryState
from skeleton.memory.delta_memory import DeltaMemoryPort


def delta_entry(record: MemoryRecord) -> Dict[str, Any]:
    """JSON-friendly Δ-Memory value for a canonical record."""
    return {
        "canonical_memory_id": record.memory_id,
        "version": record.version,
        "tenant_id": record.tenant_id,
        "namespace": record.namespace,
        "subject_id": record.subject_id,
        "kind": record.kind.value,
        "content": record.content,
        "content_ref": record.content_ref,
        "payload_digest": record.payload_digest,
        "provenance_refs": list(record.provenance_refs),
        "source_operation_id": record.source_operation_id,
        "data_class": record.data_class,
        "updated_at": record.updated_at.isoformat(),
    }


class DeltaMemoryProjection:
    """``MemoryProjection`` adapter writing canonical records into Δ-Memory."""

    def __init__(self, name: str, memory: DeltaMemoryPort) -> None:
        normalized = str(name).strip()
        if not normalized:
            raise ValueError("projection name is required")
        if not isinstance(memory, DeltaMemoryPort):
            raise TypeError("memory must implement DeltaMemoryPort")
        self.name = normalized
        self.memory = memory
        self.upserts = 0
        self.deletes = 0
        self.stale_skips = 0
        # Serializes the read-compare-write version guard across threads.
        self._lock = threading.Lock()

    def upsert(self, record: MemoryRecord) -> None:
        if record.state is not MemoryState.ACTIVE:
            self.delete(record.memory_id)
            return
        with self._lock:
            current = self._stored_version(record.memory_id)
            if current is not None and current >= record.version:
                self.stale_skips += 1
                return
            self.memory.write(record.memory_id, delta_entry(record))
            self.upserts += 1

    def delete(self, memory_id: str) -> None:
        with self._lock:
            self.memory.delete(str(memory_id))
            self.deletes += 1

    def entry(self, memory_id: str) -> Optional[Dict[str, Any]]:
        found, value = self.memory.lookup(str(memory_id))
        return value if found and isinstance(value, dict) else None

    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "upserts": self.upserts,
            "deletes": self.deletes,
            "stale_skips": self.stale_skips,
            "memory": self.memory.stats(),
        }

    def _stored_version(self, memory_id: str) -> Optional[int]:
        found, value = self.memory.lookup(memory_id)
        if not found or not isinstance(value, dict):
            return None
        version = value.get("version")
        return version if isinstance(version, int) else None


__all__ = ["DeltaMemoryProjection", "delta_entry"]
