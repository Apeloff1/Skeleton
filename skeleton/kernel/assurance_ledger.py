"""Assurance transition ledger.

Small bounded audit surface for assurance state changes.
Keeps transition history separate from durable memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time
from typing import Dict, List


@dataclass(frozen=True)
class LedgerEntry:
    event_id: str
    state: str
    task_id: str
    evidence_digest: str
    created_at: float


class AssuranceLedger:
    def __init__(self, limit: int = 4096) -> None:
        self.limit = max(32, int(limit))
        self._entries: List[LedgerEntry] = []

    def record(self, event_id: str, state: str, task_id: str, evidence_digest: str) -> LedgerEntry:
        entry = LedgerEntry(
            event_id=event_id,
            state=state,
            task_id=task_id,
            evidence_digest=evidence_digest,
            created_at=time(),
        )
        self._entries.append(entry)
        if len(self._entries) > self.limit:
            self._entries.pop(0)
        return entry

    def contains(self, event_id: str) -> bool:
        return any(item.event_id == event_id for item in self._entries)

    def snapshot(self) -> List[Dict[str, object]]:
        return [item.__dict__.copy() for item in self._entries]
