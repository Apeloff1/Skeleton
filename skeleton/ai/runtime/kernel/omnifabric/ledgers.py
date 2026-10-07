"""Multi-ledger catalog and indexes over OmniFabric events.

The RS fabric tags every event with a ``ledger`` string. This module
keeps a registry of known ledgers, per-ledger sequence views, and
kind histograms so callers can navigate the fabric without scanning
the entire hot tail on every query.
"""
from __future__ import annotations

import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from skeleton.kernel.omnifabric.errors import CapacityError, LedgerUnknown
from skeleton.kernel.omnifabric.events import FabricEvent


@dataclass
class LedgerInfo:
    name: str
    description: str = ""
    created_seq: int = 0
    event_count: int = 0
    last_seq: int = 0
    last_hash: str = ""
    kinds: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "created_seq": self.created_seq,
            "event_count": self.event_count,
            "last_seq": self.last_seq,
            "last_hash": self.last_hash,
            "kinds": dict(self.kinds),
            "metadata": dict(self.metadata),
        }


class LedgerCatalog:
    """Registry of named ledgers with live indexes fed by fabric appends."""

    def __init__(self, *, max_ledgers: int = 4096, require_registered: bool = False) -> None:
        if max_ledgers < 1:
            raise ValueError("max_ledgers must be >= 1")
        self._max = int(max_ledgers)
        self._require = bool(require_registered)
        self._lock = threading.RLock()
        self._ledgers: dict[str, LedgerInfo] = {}
        self._by_ledger_seqs: dict[str, list[int]] = defaultdict(list)
        self._kind_global: Counter[str] = Counter()

    def register(self, name: str, description: str = "", **metadata: Any) -> LedgerInfo:
        name = str(name)
        with self._lock:
            if name in self._ledgers:
                info = self._ledgers[name]
                if description:
                    info.description = description
                info.metadata.update(metadata)
                return info
            if len(self._ledgers) >= self._max:
                raise CapacityError(f"ledger catalog full ({self._max})")
            info = LedgerInfo(name=name, description=description, metadata=dict(metadata))
            self._ledgers[name] = info
            return info

    def ensure(self, name: str) -> LedgerInfo:
        with self._lock:
            if name in self._ledgers:
                return self._ledgers[name]
            if self._require:
                raise LedgerUnknown(f"ledger not registered: {name}")
            return self.register(name)

    def get(self, name: str) -> LedgerInfo:
        with self._lock:
            if name not in self._ledgers:
                raise LedgerUnknown(f"ledger not registered: {name}")
            return self._ledgers[name]

    def list_ledgers(self) -> list[LedgerInfo]:
        with self._lock:
            return [LedgerInfo(**i.to_dict()) for i in sorted(self._ledgers.values(), key=lambda x: x.name)]

    def observe(self, ev: FabricEvent) -> LedgerInfo:
        """Update indexes from a newly appended event."""
        with self._lock:
            info = self.ensure(ev.ledger)
            if info.event_count == 0:
                info.created_seq = ev.seq
            info.event_count += 1
            info.last_seq = ev.seq
            info.last_hash = ev.hash
            info.kinds[ev.kind] = info.kinds.get(ev.kind, 0) + 1
            self._by_ledger_seqs[ev.ledger].append(ev.seq)
            self._kind_global[ev.kind] += 1
            return info

    def seqs_for(self, ledger: str) -> list[int]:
        with self._lock:
            return list(self._by_ledger_seqs.get(ledger, ()))

    def kind_histogram(self) -> dict[str, int]:
        with self._lock:
            return dict(self._kind_global)

    def rebuild_from(self, events: Iterable[FabricEvent]) -> int:
        """Reset indexes and rebuild from an event stream."""
        with self._lock:
            # preserve registrations/descriptions
            preserved = {n: (i.description, dict(i.metadata)) for n, i in self._ledgers.items()}
            self._ledgers.clear()
            self._by_ledger_seqs.clear()
            self._kind_global.clear()
            for name, (desc, meta) in preserved.items():
                self.register(name, desc, **meta)
            n = 0
            for ev in events:
                self.observe(ev)
                n += 1
            return n

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ledger_count": len(self._ledgers),
                "max_ledgers": self._max,
                "require_registered": self._require,
                "kind_histogram": dict(self._kind_global),
                "total_indexed_events": sum(i.event_count for i in self._ledgers.values()),
            }
