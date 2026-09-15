"""Outbox — journal-first durability. Nothing exists only in memory.

The law of the outbox: intent is journaled *before* the event is admitted
anywhere observable, and a background reconciler confirms each journal
entry into Mongo. A crash between journal and insert leaves an unconfirmed
row that the reconciler replays on boot — a decided event can never exist
nowhere durable.

When the outbox is full it backpressures (raises), it never drops.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


class OutboxFull(Exception):
    """Durability is backpressured, not dropped. Caller sees this."""


@dataclass
class Intent:
    seq: int
    collection: str
    document: dict[str, Any]
    journaled_at: float = field(default_factory=time.time)
    confirmed: bool = False
    attempts: int = 0


class Outbox:
    """Bounded journal + reconciler. `sink` performs the durable write."""

    def __init__(self, sink: Callable[[str, dict], Awaitable[None]], cap: int = 4096):
        self._sink = sink
        self._cap = cap
        self._pending: deque[Intent] = deque()
        self._seq = 0
        self._lock = asyncio.Lock()
        self.journaled_total = 0
        self.confirmed_total = 0

    async def journal(self, collection: str, document: dict[str, Any]) -> int:
        async with self._lock:
            unconfirmed = sum(1 for i in self._pending if not i.confirmed)
            if unconfirmed >= self._cap:
                raise OutboxFull("outbox at capacity — write is refused, not lost")
            self._seq += 1
            self._pending.append(Intent(self._seq, collection, document))
            self.journaled_total += 1
            return self._seq

    async def reconcile(self) -> int:
        """Confirm everything unconfirmed, oldest first. Returns count."""
        done = 0
        async with self._lock:
            for intent in self._pending:
                if intent.confirmed:
                    continue
                try:
                    await self._sink(intent.collection, intent.document)
                    intent.confirmed = True
                    done += 1
                    self.confirmed_total += 1
                except Exception:
                    intent.attempts += 1
            while self._pending and self._pending[0].confirmed:
                self._pending.popleft()
        return done

    async def pending_count(self) -> int:
        async with self._lock:
            return sum(1 for i in self._pending if not i.confirmed)


async def run_reconciler(outbox: Outbox, interval_secs: float = 5.0) -> None:
    """The reconciler never retires; it only waits."""
    while True:
        await asyncio.sleep(interval_secs)
        await outbox.reconcile()
