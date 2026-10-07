"""Fabric outbox — journal-first durability for OmniFabric appends.

Port of ``gf_core::outbox::Outbox`` doctrine into the hex surface:
intent is journaled BEFORE the hot tail admits the event. Full outbox
backpressures (raises ``OutboxFull``); it never drops. A crash between
journal and confirm leaves an unconfirmed row that ``reconcile()``
replays.

This is distinct from ``skeleton.forge.outbox.MaterialiseOutbox`` (forge
materialisations). Fabric durability rides this module only.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from skeleton.kernel.omnifabric.errors import OutboxFull, OutboxJournalError

COLLECTION_DEFAULT = "omega_fabric"


@dataclass
class OutboxEntry:
    seq: int
    collection: str
    document: dict[str, Any]
    journaled_at: float = field(default_factory=time.time)
    confirmed: bool = False
    attempts: int = 0


Sink = Callable[[str, dict[str, Any]], None]


class MemorySink:
    """In-process durable sink for tests and single-process callers."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, collection: str, document: dict[str, Any]) -> None:
        self.rows.append((collection, dict(document)))


class FabricOutbox:
    """Bounded journal + reconciler for Ω-fabric events.

    Capacity is counted in *unconfirmed* entries. Confirmed rows are
    drained after each reconcile. ``journaled_total`` / ``confirmed_total``
    match RS atomic counters.
    """

    def __init__(self, sink: Sink | None = None, *, cap: int = 4096) -> None:
        if cap < 1:
            raise ValueError("outbox cap must be >= 1")
        self._sink: Sink = sink if sink is not None else MemorySink()
        self._cap = int(cap)
        self._pending: deque[OutboxEntry] = deque()
        self._lock = threading.RLock()
        self.journaled_total = 0
        self.confirmed_total = 0

    @property
    def cap(self) -> int:
        return self._cap

    def pending_count(self) -> int:
        with self._lock:
            return sum(1 for e in self._pending if not e.confirmed)

    def journal(self, collection: str, document: Mapping[str, Any]) -> int:
        """Step 1: journal the intent. Only after this returns may callers expose the event."""
        with self._lock:
            unconfirmed = sum(1 for e in self._pending if not e.confirmed)
            if unconfirmed >= self._cap:
                raise OutboxFull(
                    f"outbox full ({self._cap}) — durable persistence is "
                    "backpressured, not dropped"
                )
            self.journaled_total += 1
            seq = self.journaled_total
            entry = OutboxEntry(
                seq=seq,
                collection=str(collection),
                document=dict(document),
            )
            self._pending.append(entry)
            return seq

    def confirm_one(self, seq: int) -> bool:
        """Step 2: confirm into the sink. Retries live with the reconciler."""
        with self._lock:
            target = next((e for e in self._pending if e.seq == seq and not e.confirmed), None)
            if target is None:
                return True
            target.attempts += 1
            try:
                self._sink(target.collection, dict(target.document))
            except Exception as exc:  # noqa: BLE001 — surface as journal error
                raise OutboxJournalError(f"confirm seq={seq} failed: {exc}") from exc
            target.confirmed = True
            self.confirmed_total += 1
            # drain confirmed from the left
            while self._pending and self._pending[0].confirmed:
                self._pending.popleft()
            return True

    def reconcile(self) -> int:
        """Replay everything unconfirmed — boot-time and periodic sweep."""
        with self._lock:
            seqs = [e.seq for e in self._pending if not e.confirmed]
        done = 0
        for seq in seqs:
            if self.confirm_one(seq):
                done += 1
        return done

    def unconfirmed_documents(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(e.document) for e in self._pending if not e.confirmed]

    def snapshot_pending(self) -> list[OutboxEntry]:
        with self._lock:
            return [
                OutboxEntry(
                    seq=e.seq,
                    collection=e.collection,
                    document=dict(e.document),
                    journaled_at=e.journaled_at,
                    confirmed=e.confirmed,
                    attempts=e.attempts,
                )
                for e in self._pending
            ]
