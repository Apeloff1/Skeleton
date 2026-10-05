"""
Skeleton Foundation — Event Journal + Deterministic Replay

The bedrock of reproducibility: every event the bus publishes is
appended to an immutable journal. Any system state reachable by
replaying events is therefore reconstructible — exactly — from the
journal plus the boot seed. Time becomes a function of the log.

Semantics:
- Journal: append-only, hash-chained (each entry commits to the
  previous entry's hash — a tamper-evident event blockchain at the
  kernel level, beneath everything else).
- Replay: a fresh set of subsystems is built, then events are
  re-fed IN ORDER through the same handlers. Deterministic handlers
  (seeded entropy, no wall-clock reads inside logic) yield
  bit-identical state.
- Snapshots: periodic state captures (rooted in the Merkle DAG) let
  replay start mid-stream: load snapshot at entry N, replay N+1…M.
- Time-travel queries: "what did the system believe at entry K?" —
  replay from genesis to K on a shadow copy.
- Proof: journal_integrity() verifies the hash chain end-to-end;
  one flipped byte anywhere breaks every link downstream.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class JournalEntry:
    """One immutable journal entry, hash-chained to its predecessor."""
    index: int
    topic: str
    payload: Dict[str, Any]
    correlation_id: str
    timestamp: float
    prev_hash: str
    entry_hash: str = ""

    def compute_hash(self) -> str:
        body = f"{self.index}|{self.topic}|{sorted(self.payload.items())}|{self.correlation_id}|{self.timestamp}|{self.prev_hash}"
        return hashlib.sha256(body.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {"index": self.index, "topic": self.topic,
                "payload": self.payload, "correlation_id": self.correlation_id,
                "timestamp": self.timestamp, "entry_hash": self.entry_hash[:16]}


class EventJournal:
    """Append-only, hash-chained record of every bus event."""

    GENESIS_HASH = "0" * 64

    def __init__(self, dag: Optional[Any] = None):
        self._entries: List[JournalEntry] = []
        self._dag = dag  # optional Merkle DAG for snapshot rooting
        self._snapshots: Dict[int, str] = {}  # index -> dag hash
        self._stats = {"appended": 0, "snapshots": 0}

    def append(self, topic: str, payload: Dict[str, Any],
               correlation_id: str = "", timestamp: Optional[float] = None) -> JournalEntry:
        prev = self._entries[-1].entry_hash if self._entries else self.GENESIS_HASH
        entry = JournalEntry(
            index=len(self._entries),
            topic=topic,
            payload=dict(payload),
            correlation_id=correlation_id,
            timestamp=timestamp if timestamp is not None else time.time(),
            prev_hash=prev,
        )
        entry.entry_hash = entry.compute_hash()
        self._entries.append(entry)
        self._stats["appended"] += 1
        return entry

    def entry(self, index: int) -> Optional[JournalEntry]:
        return self._entries[index] if 0 <= index < len(self._entries) else None

    def __len__(self) -> int:
        return len(self._entries)

    def integrity(self) -> bool:
        """Verify the full hash chain."""
        prev = self.GENESIS_HASH
        for entry in self._entries:
            if entry.prev_hash != prev:
                return False
            if entry.compute_hash() != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True

    def snapshot(self, name: str, state: Dict[str, Any]) -> Optional[str]:
        """Root a state snapshot in the Merkle DAG at the current index."""
        if self._dag is None:
            return None
        parent = self._snapshots.get(len(self._entries) - 1)
        h = self._dag.put({"name": name, "state": state,
                           "journal_index": len(self._entries) - 1},
                          kind="journal.snapshot",
                          links=[parent] if parent else [])
        self._snapshots[len(self._entries) - 1] = h
        self._stats["snapshots"] += 1
        return h

    def slice(self, start: int = 0, end: Optional[int] = None) -> List[JournalEntry]:
        return self._entries[start:end]

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "entries": len(self._entries),
                "tip_hash": self._entries[-1].entry_hash[:16] if self._entries else None}


class ReplayEngine:
    """Deterministic state reconstruction from the journal.

    Handlers are registered per topic (same shape as bus subscribers).
    Replay builds fresh state by feeding recorded events through them
    in journal order. Determinism contract: handlers must use seeded
    entropy only — wall-clock inside logic breaks bit-identity.
    """

    def __init__(self, journal: EventJournal):
        self._journal = journal
        self._handlers: Dict[str, List[Callable[[JournalEntry, Dict[str, Any]], None]]] = {}
        self._stats = {"replays": 0, "events_replayed": 0}

    def on(self, topic: str,
           handler: Callable[[JournalEntry, Dict[str, Any]], None]) -> None:
        self._handlers.setdefault(topic, []).append(handler)

    def replay(self, start: int = 0, end: Optional[int] = None,
               state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Rebuild state by replaying [start, end) through handlers."""
        self._stats["replays"] += 1
        state = state if state is not None else {}
        for entry in self._journal.slice(start, end):
            for topic_pattern, handlers in self._handlers.items():
                if self._matches(topic_pattern, entry.topic):
                    for handler in handlers:
                        handler(entry, state)
            self._stats["events_replayed"] += 1
        return state

    def time_travel(self, index: int) -> Dict[str, Any]:
        """System state as of journal entry `index` (inclusive)."""
        return self.replay(0, index + 1, state={})

    def verify_determinism(self, twice: bool = True) -> bool:
        """Replay twice from genesis; states must be identical."""
        a = self.replay(0, None, state={})
        if not twice:
            return True
        b = self.replay(0, None, state={})
        return a == b

    @staticmethod
    def _matches(pattern: str, topic: str) -> bool:
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            return topic.startswith(pattern[:-1])
        return pattern == topic

    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)


class JournaledBus:
    """EventBus wrapper: publishes through to the wrapped bus while
    appending every event to the journal. Drop-in replacement."""

    def __init__(self, bus: Any, journal: EventJournal):
        self._bus = bus
        self.journal = journal

    def publish(self, event: Any) -> None:
        self.journal.append(event.topic, event.payload, event.correlation_id)
        self._bus.publish(event)

    def emit(self, topic: str, payload: Dict[str, Any]) -> None:
        self.journal.append(topic, payload, "")
        self._bus.emit(topic, payload)

    def subscribe(self, topic: str, handler: Any) -> None:
        self._bus.subscribe(topic, handler)

    def stats(self) -> Dict[str, Any]:
        return {"bus": self._bus.stats(), "journal": self.journal.stats()}
