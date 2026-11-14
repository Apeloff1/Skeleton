"""Bounded tenant-fair, in-process dispatch queue with deterministic cancellation.

No distributed-lease promise: use the authoritative service's process fence
and durable conversation commit for cross-process generation correctness.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import RLock
from typing import Deque

from .contracts import strict_integer
from .errors import deny
from .identities import require_id


@dataclass(frozen=True, slots=True)
class QueueTicket:
    request_id: str
    owner: str

    def __post_init__(self) -> None:
        require_id(self.request_id, "request")
        require_id(self.owner, "owner")


class FairQueue:
    """Round robin across owners; FIFO within owner; finite active+pending."""

    def __init__(self, *, capacity: int = 64, per_owner: int = 8):
        self.capacity = strict_integer(capacity, minimum=1, maximum=4096, field="capacity")
        self.per_owner = strict_integer(per_owner, minimum=1, maximum=4096, field="owner-capacity")
        self._lock = RLock()
        self._pending: dict[str, Deque[QueueTicket]] = {}
        self._owners: Deque[str] = deque()
        self._tickets: dict[str, QueueTicket] = {}
        self._running: set[str] = set()

    def enqueue(self, ticket: QueueTicket) -> None:
        if type(ticket) is not QueueTicket:
            deny("queue-ticket")
        with self._lock:
            if ticket.request_id in self._tickets:
                deny("queue-duplicate")
            if len(self._tickets) >= self.capacity:
                deny("queue-full")
            owner_count = sum(t.owner == ticket.owner for t in self._tickets.values())
            if owner_count >= self.per_owner:
                deny("queue-owner-full")
            pending = self._pending.setdefault(ticket.owner, deque())
            if not pending:
                self._owners.append(ticket.owner)
            pending.append(ticket)
            self._tickets[ticket.request_id] = ticket

    def poll(self) -> QueueTicket | None:
        with self._lock:
            if not self._owners:
                return None
            owner = self._owners.popleft()
            pending = self._pending[owner]
            ticket = pending.popleft()
            if pending:
                self._owners.append(owner)
            else:
                del self._pending[owner]
            self._running.add(ticket.request_id)
            return ticket

    def cancel(self, request_id: str) -> bool:
        require_id(request_id, "request")
        with self._lock:
            ticket = self._tickets.get(request_id)
            if ticket is None:
                return False
            if request_id in self._running:
                deny("queue-already-running")
            pending = self._pending[ticket.owner]
            pending.remove(ticket)
            if not pending:
                del self._pending[ticket.owner]
                self._owners.remove(ticket.owner)
            del self._tickets[request_id]
            return True

    def finish(self, ticket: QueueTicket) -> None:
        with self._lock:
            if ticket.request_id not in self._running or self._tickets.get(ticket.request_id) != ticket:
                deny("queue-finish-conflict")
            self._running.remove(ticket.request_id)
            del self._tickets[ticket.request_id]

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "total": len(self._tickets),
                "inflight": len(self._running),
                "pending": len(self._tickets) - len(self._running),
                "owners_pending": len(self._owners),
            }
