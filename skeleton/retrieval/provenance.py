"""Provenance ledger — every answer carries its evidence chain, signed.

RAG returns chunks; the ledger records *which* chunks fed *which* answer,
hash-chained so the record itself is tamper-evident. When Jeeves cites a
fact, the ledger can prove which memory tier, which chunk id, at which
fusion weight it entered the context window — and a later auditor can
recompute the chain hashes to verify nobody edited the record.

Design
------
- Each entry links to the previous entry's hash (a hash chain, same
  trick as the merkle log, specialised for answer attribution).
- Attribution is per-source: chunk id, tier, and fusion contribution,
  so "why did the tutor say that?" decomposes into ranked evidence.
- Verification is local and cheap: walk the chain, recompute, compare.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass(frozen=True)
class Attribution:
    """One chunk's contribution to one answer."""
    chunk_id: str
    tier: str                     # "rag" | "cag" | "mag"
    fusion_contribution: float


@dataclass
class LedgerEntry:
    answer_id: str
    query: str
    attributions: List[Attribution]
    prev_hash: str
    entry_hash: str = ""
    recorded_at: float = field(default_factory=time.time)

    def compute_hash(self) -> str:
        body = json.dumps({
            "answer_id": self.answer_id,
            "query": self.query,
            "attributions": [a.__dict__ for a in self.attributions],
            "prev_hash": self.prev_hash,
            "recorded_at": self.recorded_at,
        }, sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()


class ProvenanceLedger:
    """Append-only, hash-chained record of answer attributions."""

    GENESIS = "0" * 64

    def __init__(self, *, bus: Optional[EventBus] = None) -> None:
        self._entries: List[LedgerEntry] = []
        self._bus = bus

    def record(self, answer_id: str, query: str,
               attributions: List[Attribution]) -> LedgerEntry:
        prev_hash = self._entries[-1].entry_hash if self._entries else self.GENESIS
        entry = LedgerEntry(answer_id=answer_id, query=query,
                            attributions=list(attributions), prev_hash=prev_hash)
        entry.entry_hash = entry.compute_hash()
        self._entries.append(entry)
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="retrieval.provenance.recorded",
                    payload={
                        "answer_id": answer_id,
                        "sources": len(attributions),
                        "tiers": sorted({a.tier for a in attributions}),
                        "chain_length": len(self._entries),
                    },
                    correlation_id=f"prov_{answer_id}",
                )
            )
        return entry

    def verify(self) -> bool:
        """Recompute the whole chain; False at the first broken link."""
        prev = self.GENESIS
        for entry in self._entries:
            if entry.prev_hash != prev:
                return False
            if entry.compute_hash() != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True

    def explain(self, answer_id: str) -> Optional[Dict[str, Any]]:
        """The ranked evidence for one answer, best contribution first."""
        for entry in reversed(self._entries):
            if entry.answer_id == answer_id:
                ranked = sorted(entry.attributions,
                                key=lambda a: a.fusion_contribution, reverse=True)
                return {
                    "answer_id": answer_id,
                    "query": entry.query,
                    "evidence": [a.__dict__ for a in ranked],
                    "recorded_at": entry.recorded_at,
                }
        return None

    def stats(self) -> Dict[str, Any]:
        return {
            "entries": len(self._entries),
            "chain_valid": self.verify(),
            "head_hash": self._entries[-1].entry_hash[:16] if self._entries else None,
        }
