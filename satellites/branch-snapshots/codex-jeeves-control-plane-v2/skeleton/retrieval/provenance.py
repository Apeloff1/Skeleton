"""
Skeleton Retrieval — Provenance tracking for audit trails

Provides:
- ProvenanceLedger: Track data lineage and transformations
- ProvenanceEntry: Single provenance record
"""

from __future__ import annotations

import hashlib
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

    def __init__(self, bus: Optional[EventBus] = None):
        self._entries: Dict[str, ProvenanceEntry] = {}
        self._chains: Dict[str, List[str]] = {}  # root_id -> [entry_ids]
        self._bus = bus
        self._stats = {"recorded": 0, "queries": 0}

    def record(self, source: str, operation: str, input_data: Any, output_data: Any, parent_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> ProvenanceEntry:
        """Record a data transformation in the ledger."""
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
        
        # Track chain
        root = parent_id or entry.entry_id
        if root not in self._chains:
            self._chains[root] = []
        self._chains[root].append(entry.entry_id)
        
        self._stats["recorded"] += 1
        
        if self._bus:
            self._bus.emit("retrieval.provenance.recorded", {
                "entry_id": entry.entry_id,
                "source": source,
                "operation": operation,
            })
        
        return entry

    def trace(self, entry_id: str) -> List[ProvenanceEntry]:
        """Trace the full lineage chain for an entry."""
        self._stats["queries"] += 1
        
        # Find which chain contains this entry
        chain_entries = []
        for root, entries in self._chains.items():
            if entry_id in entries:
                chain_entries = entries
                break
        
        if not chain_entries:
            return []
        
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
        if not entry:
            return False
        
        current_hash = ProvenanceEntry.hash_data(current_data)
        return current_hash == entry.output_hash

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "entries": len(self._entries),
            "chains": len(self._chains),
        }
