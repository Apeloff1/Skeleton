"""
Skeleton Retrieval — Provenance tracking for audit trails

Provides:
- ProvenanceLedger: Track data lineage and transformations
- ProvenanceEntry: Single provenance record
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class ProvenanceEntry:
    """A single provenance record in the data lineage chain."""
    entry_id: str
    source: str
    operation: str
    input_hash: str
    output_hash: str
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None

    @staticmethod
    def hash_data(data: Any) -> str:
        """Create a stable hash of data for provenance tracking."""
        content = str(data).encode('utf-8')
        return hashlib.blake2b(content, digest_size=16).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "source": self.source,
            "operation": self.operation,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "parent_id": self.parent_id,
        }


class ProvenanceLedger:
    """Track data lineage and transformations for auditability.

    Every data transformation is recorded as a ProvenanceEntry,
    creating an immutable chain of custody.
    """

    def __init__(self, bus: Optional[EventBus] = None, persist=None):
        self._entries: Dict[str, ProvenanceEntry] = {}
        self._chains: Dict[str, List[str]] = {}  # root_id -> [entry_ids]
        self._bus = bus
        self._stats = {"recorded": 0, "queries": 0}
        self._idempotency: Dict[str, str] = {}
        self._persist = persist

    def record(self, source: str, operation: str, input_data: Any, output_data: Any, parent_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, idempotency_key: Optional[str] = None) -> ProvenanceEntry:
        """Record a data transformation in the ledger."""
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source is required")
        if not isinstance(operation, str) or not operation.strip():
            raise ValueError("operation is required")
        if parent_id is not None and parent_id not in self._entries:
            raise ValueError("parent is not recorded")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        if idempotency_key is not None:
            if not isinstance(idempotency_key, str) or not idempotency_key.strip():
                raise ValueError("idempotency_key must be a non-empty string")
            prior_id = self._idempotency.get(idempotency_key)
            if prior_id is not None:
                prior = self._entries[prior_id]
                if (prior.source != source or prior.operation != operation or
                    prior.input_hash != ProvenanceEntry.hash_data(input_data) or
                    prior.output_hash != ProvenanceEntry.hash_data(output_data) or
                    prior.parent_id != parent_id or prior.metadata != (metadata or {})):
                    raise ValueError("idempotency_key reused with different provenance payload")
                return prior
        import uuid
        entry = ProvenanceEntry(
            entry_id=str(uuid.uuid4())[:12],
            source=source,
            operation=operation,
            input_hash=ProvenanceEntry.hash_data(input_data),
            output_hash=ProvenanceEntry.hash_data(output_data),
            timestamp=time.time(),
            metadata=metadata or {},
            parent_id=parent_id,
        )

        self._entries[entry.entry_id] = entry
        if idempotency_key is not None:
            self._idempotency[idempotency_key] = entry.entry_id

        # A child of a non-root parent still belongs to the original chain.
        root = self._chain_root(entry.entry_id)
        chain = self._chains.setdefault(root, [])
        if entry.entry_id not in chain:
            chain.append(entry.entry_id)

        self._stats["recorded"] += 1

        if self._persist:
            try:
                self._persist(self)
            except Exception:
                self._stats["recorded"] -= 1
                if idempotency_key is not None:
                    self._idempotency.pop(idempotency_key, None)
                chain.remove(entry.entry_id)
                if not chain:
                    self._chains.pop(root, None)
                self._entries.pop(entry.entry_id, None)
                raise

        if self._bus:
            self._bus.emit("retrieval.provenance.recorded", {
                "entry_id": entry.entry_id,
                "source": source,
                "operation": operation,
            })

        return entry


    def _chain_root(self, entry_id: str) -> str:
        seen = set()
        current = entry_id
        while current and current not in seen:
            seen.add(current)
            entry = self._entries.get(current)
            if entry is None or not entry.parent_id:
                return current
            if entry.parent_id not in self._entries:
                return entry.parent_id
            current = entry.parent_id
        return entry_id

    def trace(self, entry_id: str) -> List[ProvenanceEntry]:
        """Trace the full lineage chain for an entry."""
        if entry_id not in self._entries:
            raise KeyError(entry_id)
        self._stats["queries"] += 1

        # Find which chain contains this entry
        chain_entries = []
        for root, entries in self._chains.items():
            if entry_id in entries:
                chain_entries = entries
                break

        if not chain_entries:
            raise KeyError(entry_id)

        # Build ordered lineage
        lineage = []
        for eid in chain_entries:
            if eid in self._entries:
                lineage.append(self._entries[eid])
            if eid == entry_id:
                break

        return lineage

    def verify(self, entry_id: str, current_data: Any) -> bool:
        """Verify that current data matches the recorded provenance hash."""
        entry = self._entries.get(entry_id)
        if entry is None:
            raise KeyError(entry_id)

        current_hash = ProvenanceEntry.hash_data(current_data)
        return current_hash == entry.output_hash

    def snapshot(self) -> Dict[str, Any]:
        """Return deterministic restart state including idempotency bindings."""
        entries = [self._entries[key].to_dict() for key in sorted(self._entries)]
        payload = {
            "version": 1,
            "entries": entries,
            "idempotency": dict(sorted(self._idempotency.items())),
            "stats": {"recorded": self._stats["recorded"], "queries": self._stats["queries"]},
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload["digest"] = hashlib.blake2b(encoded, digest_size=16).hexdigest()
        return payload

    @classmethod
    def from_snapshot(cls, payload: Dict[str, Any], bus: Optional[EventBus] = None, persist=None) -> "ProvenanceLedger":
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("unsupported provenance snapshot")
        digest = payload.get("digest")
        body = {k: v for k, v in payload.items() if k != "digest"}
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if not isinstance(digest, str) or digest != hashlib.blake2b(encoded, digest_size=16).hexdigest():
            raise ValueError("provenance snapshot digest mismatch")
        ledger = cls(bus, persist=persist)
        entries = payload.get("entries")
        idem = payload.get("idempotency")
        stats = payload.get("stats")
        if not isinstance(entries, list) or not isinstance(idem, dict) or not isinstance(stats, dict):
            raise ValueError("invalid provenance snapshot shape")
        for raw in entries:
            entry = ProvenanceEntry(**raw)
            if not entry.entry_id or entry.entry_id in ledger._entries:
                raise ValueError("duplicate or empty provenance entry id")
            ledger._entries[entry.entry_id] = entry
        for entry in ledger._entries.values():
            if entry.parent_id is not None and entry.parent_id not in ledger._entries:
                raise ValueError("provenance snapshot has missing parent")
            root = ledger._chain_root(entry.entry_id)
            ledger._chains.setdefault(root, []).append(entry.entry_id)
        for key, entry_id in idem.items():
            if not isinstance(key, str) or not key or entry_id not in ledger._entries:
                raise ValueError("invalid provenance idempotency binding")
            ledger._idempotency[key] = entry_id
        recorded = stats.get("recorded")
        queries = stats.get("queries")
        if not isinstance(recorded, int) or recorded < len(entries) or not isinstance(queries, int) or queries < 0:
            raise ValueError("invalid provenance statistics")
        ledger._stats = {"recorded": recorded, "queries": queries}
        return ledger

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "entries": len(self._entries),
            "chains": len(self._chains),
        }
