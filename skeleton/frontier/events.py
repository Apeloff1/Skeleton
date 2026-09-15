"""Typed frontier event bus with optional journal-before-delivery durability.

The canonical bus remains provider-neutral and in-process. A journal can be
attached to preserve the portable GameForge outbox invariant: record intent
before exposing an event, leave failed or currently undeliverable events
pending, and confirm only after successful fan-out. No MongoDB client or second
event bus is imported.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Mapping, Protocol, Sequence
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class DomainEvent:
    topic: str
    payload: Mapping[str, object]
    occurred_at: datetime

    @classmethod
    def create(cls, topic: str, payload: Mapping[str, object]) -> "DomainEvent":
        if not topic.strip():
            raise ValueError("topic must not be empty")
        return cls(
            topic=topic.strip(),
            payload=dict(payload),
            occurred_at=datetime.now(timezone.utc),
        )


@dataclass(frozen=True, slots=True)
class JournalEntry:
    token: str
    event: DomainEvent


class EventJournal(Protocol):
    """Minimal durability boundary consumed by ``EventBus``."""

    async def journal(self, event: DomainEvent) -> str:
        ...

    async def confirm(self, token: str) -> None:
        ...

    async def pending(self, *, limit: int = 100) -> tuple[JournalEntry, ...]:
        ...


Handler = Callable[[DomainEvent], Awaitable[None]]


class EventBus:
    """Ordered async fan-out bus with optional journal-before-delivery semantics.

    Recovery is explicit rather than backgrounded. ``replay_pending`` processes
    journal entries oldest-first and confirms each only after successful fan-
    out to at least one subscriber. Handler side effects therefore have
    at-least-once semantics if a prior delivery partially completed before
    failing.
    """

    def __init__(self, *, journal: EventJournal | None = None) -> None:
        self._handlers: dict[str, list[Handler]] = {}
        self._lock = asyncio.Lock()
        self._replay_lock = asyncio.Lock()
        self._journal = journal

    async def subscribe(self, topic: str, handler: Handler) -> None:
        if not topic.strip():
            raise ValueError("topic must not be empty")
        async with self._lock:
            self._handlers.setdefault(topic, []).append(handler)

    async def _deliver(self, event: DomainEvent) -> int:
        async with self._lock:
            handlers = tuple(self._handlers.get(event.topic, ()))

        delivered = 0
        for handler in handlers:
            await handler(event)
            delivered += 1
        return delivered

    async def publish(self, event: DomainEvent) -> int:
        token = await self._journal.journal(event) if self._journal else None
        delivered = await self._deliver(event)
        if self._journal is not None and token is not None and delivered > 0:
            await self._journal.confirm(token)
        return delivered

    async def replay_pending(self, *, limit: int = 100) -> int:
        """Replay pending durable events in journal order.

        Replays are serialized per bus instance. A failing handler or an event
        with no current subscribers stops replay at that entry and leaves it,
        plus all later entries, pending. This preserves source order and avoids
        both silent acknowledgement and concurrent double-delivery.
        """

        if limit < 1 or self._journal is None:
            return 0

        async with self._replay_lock:
            entries = await self._journal.pending(limit=limit)
            replayed = 0
            for entry in entries:
                delivered = await self._deliver(entry.event)
                if delivered == 0:
                    break
                await self._journal.confirm(entry.token)
                replayed += 1
            return replayed


class SQLiteEventJournal:
    """Persistent stdlib event journal for recovery evidence and local services.

    Entries are inserted before delivery and retained until confirmed. Capacity
    applies only to unconfirmed entries: when full, the journal backpressures
    publishers instead of dropping pending work.
    """

    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        namespace: str = "frontier_events",
        capacity: int = 4096,
    ) -> None:
        namespace = namespace.strip()
        if not namespace:
            raise ValueError("namespace must not be empty")
        if capacity < 1:
            raise ValueError("capacity must be positive")

        self.namespace = namespace
        self.capacity = capacity
        self._connection = sqlite3.connect(
            str(path),
            check_same_thread=False,
            timeout=5.0,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS frontier_event_journal (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    namespace TEXT NOT NULL,
                    token TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    confirmed INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(namespace, token)
                )
                """
            )
            self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_frontier_event_journal_pending
                ON frontier_event_journal(namespace, confirmed, seq)
                """
            )
            self._connection.commit()

    @staticmethod
    def _serialize_payload(payload: Mapping[str, object]) -> str:
        try:
            return json.dumps(
                dict(payload),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise TypeError("event payload must be JSON serializable") from exc

    def _pending_count_sync(self) -> int:
        with self._lock:
            row = self._connection.execute(
                """
                SELECT COUNT(*)
                FROM frontier_event_journal
                WHERE namespace = ? AND confirmed = 0
                """,
                (self.namespace,),
            ).fetchone()
            return int(row[0])

    def _journal_sync(self, event: DomainEvent) -> str:
        if not event.topic.strip():
            raise ValueError("event topic must not be empty")
        if event.occurred_at.tzinfo is None:
            raise ValueError("event occurred_at must be timezone-aware")

        payload_json = self._serialize_payload(event.payload)
        token = str(uuid4())
        occurred_at = event.occurred_at.astimezone(timezone.utc).isoformat()
        with self._lock:
            pending = self._connection.execute(
                """
                SELECT COUNT(*)
                FROM frontier_event_journal
                WHERE namespace = ? AND confirmed = 0
                """,
                (self.namespace,),
            ).fetchone()
            if int(pending[0]) >= self.capacity:
                raise RuntimeError(
                    "event journal full — unconfirmed events are backpressured, not dropped"
                )
            self._connection.execute(
                """
                INSERT INTO frontier_event_journal(
                    namespace,
                    token,
                    topic,
                    payload_json,
                    occurred_at,
                    confirmed
                ) VALUES (?, ?, ?, ?, ?, 0)
                """,
                (
                    self.namespace,
                    token,
                    event.topic,
                    payload_json,
                    occurred_at,
                ),
            )
            self._connection.commit()
        return token

    async def journal(self, event: DomainEvent) -> str:
        return await asyncio.to_thread(self._journal_sync, event)

    def _confirm_sync(self, token: str) -> None:
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE frontier_event_journal
                SET confirmed = 1
                WHERE namespace = ? AND token = ?
                """,
                (self.namespace, token),
            )
            self._connection.commit()
            if cursor.rowcount == 0:
                raise KeyError(f"unknown event journal token: {token}")

    async def confirm(self, token: str) -> None:
        await asyncio.to_thread(self._confirm_sync, token)

    def _pending_sync(self, limit: int) -> tuple[JournalEntry, ...]:
        if limit < 1:
            return ()
        with self._lock:
            rows: Sequence[sqlite3.Row] = tuple(
                self._connection.execute(
                    """
                    SELECT token, topic, payload_json, occurred_at
                    FROM frontier_event_journal
                    WHERE namespace = ? AND confirmed = 0
                    ORDER BY seq ASC
                    LIMIT ?
                    """,
                    (self.namespace, limit),
                )
            )
        return tuple(
            JournalEntry(
                token=row["token"],
                event=DomainEvent(
                    topic=row["topic"],
                    payload=json.loads(row["payload_json"]),
                    occurred_at=datetime.fromisoformat(row["occurred_at"]),
                ),
            )
            for row in rows
        )

    async def pending(self, *, limit: int = 100) -> tuple[JournalEntry, ...]:
        return await asyncio.to_thread(self._pending_sync, limit)

    async def pending_count(self) -> int:
        return await asyncio.to_thread(self._pending_count_sync)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "SQLiteEventJournal":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
