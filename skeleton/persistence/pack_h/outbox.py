"""Transactional outbox for domain events, with an at-least-once relay.

Writers call ``Outbox.append(conn, event)`` inside the *same* SQLite
transaction as their domain write, so the event exists iff the write
committed. ``OutboxRelay`` claims ready rows with a lease, hands them to a
publisher, marks them delivered, and retries failures with exponential
backoff until ``max_attempts``, after which the row is dead-lettered.

Delivery is at-least-once: a relay that crashes after publishing but before
marking delivered will re-publish after its lease expires. Consumers dedupe
with ``ConsumerLedger`` (keyed by event_id).
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol

from skeleton.persistence.pack_h.codecs import canonical_json
from skeleton.persistence.pack_h.migrations import OUTBOX_MIGRATIONS, connect, migrate

_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")
MAX_PAYLOAD_BYTES = 256 * 1024


class OutboxError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DomainEvent:
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: Mapping[str, Any]
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _TYPE_RE.fullmatch(self.aggregate_type):
            raise OutboxError("aggregate_type must be dotted lower_snake")
        if not _TYPE_RE.fullmatch(self.event_type):
            raise OutboxError("event_type must be dotted lower_snake")
        if not self.aggregate_id or len(self.aggregate_id) > 256:
            raise OutboxError("aggregate_id must be 1-256 chars")
        if not self.event_id or len(self.event_id) > 128:
            raise OutboxError("event_id must be 1-128 chars")
        if not isinstance(self.payload, Mapping):
            raise OutboxError("payload must be a mapping")
        if len(canonical_json(dict(self.payload)).encode()) > MAX_PAYLOAD_BYTES:
            raise OutboxError("payload too large")


@dataclass(frozen=True, slots=True)
class OutboxRecord:
    seq: int
    event: DomainEvent
    created_at: float
    attempts: int
    last_error: Optional[str]


class Publisher(Protocol):
    def __call__(self, record: OutboxRecord) -> None: ...


class Outbox:
    """Schema owner and append/claim/ack operations over ``pack_h_outbox``."""

    def __init__(self, path: str = ":memory:", *, conn: Optional[sqlite3.Connection] = None,
                 clock: Callable[[], float] = time.time) -> None:
        self._conn = conn if conn is not None else connect(path)
        self._clock = clock
        self._lock = threading.RLock()
        with self._lock:
            migrate(self._conn, "outbox", OUTBOX_MIGRATIONS)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def append(self, event: DomainEvent, *, conn: Optional[sqlite3.Connection] = None,
               delay_s: float = 0.0) -> bool:
        """Insert an event. Call inside the caller's open transaction.

        Returns False if the event_id already exists (idempotent append).
        """
        c = conn if conn is not None else self._conn
        now = self._clock()
        if not math.isfinite(delay_s) or delay_s < 0:
            raise OutboxError("delay_s must be finite and non-negative")
        cur = c.execute(
            "INSERT OR IGNORE INTO pack_h_outbox (event_id, aggregate_type, aggregate_id, event_type, "
            "payload_json, headers_json, created_at, available_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.aggregate_type,
                event.aggregate_id,
                event.event_type,
                canonical_json(dict(event.payload)),
                canonical_json(dict(event.headers)),
                now,
                now + delay_s,
            ),
        )
        return (cur.rowcount or 0) == 1

    def append_now(self, event: DomainEvent) -> bool:
        """Standalone append in its own transaction (no domain write)."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                ok = self.append(event)
                self._conn.execute("COMMIT")
                return ok
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def claim(self, worker: str, *, limit: int = 100, lease_s: float = 30.0) -> List[OutboxRecord]:
        if not worker:
            raise OutboxError("worker id required")
        if limit < 1:
            raise OutboxError("limit must be positive")
        now = self._clock()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                rows = self._conn.execute(
                    "SELECT seq, event_id, aggregate_type, aggregate_id, event_type, payload_json, headers_json, "
                    "created_at, attempts, last_error FROM pack_h_outbox "
                    "WHERE delivered_at IS NULL AND dead_at IS NULL AND available_at <= ? "
                    "AND (claimed_until IS NULL OR claimed_until <= ?) ORDER BY seq LIMIT ?",
                    (now, now, limit),
                ).fetchall()
                if rows:
                    self._conn.executemany(
                        "UPDATE pack_h_outbox SET claimed_by = ?, claimed_until = ? WHERE seq = ?",
                        [(worker, now + lease_s, r[0]) for r in rows],
                    )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return [
            OutboxRecord(
                seq=int(r[0]),
                event=DomainEvent(
                    aggregate_type=r[2], aggregate_id=r[3], event_type=r[4],
                    payload=json.loads(r[5]), event_id=r[1], headers=json.loads(r[6]),
                ),
                created_at=float(r[7]),
                attempts=int(r[8]),
                last_error=r[9],
            )
            for r in rows
        ]

    def mark_delivered(self, worker: str, seq: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE pack_h_outbox SET delivered_at = ?, claimed_by = NULL, claimed_until = NULL "
                "WHERE seq = ? AND claimed_by = ? AND delivered_at IS NULL",
                (self._clock(), seq, worker),
            )
        return (cur.rowcount or 0) == 1

    def mark_failed(self, worker: str, seq: int, error: str, *, max_attempts: int,
                    backoff_s: float, max_backoff_s: float) -> str:
        """Record a failure; returns 'retry' or 'dead'."""
        now = self._clock()
        with self._lock:
            row = self._conn.execute(
                "SELECT attempts FROM pack_h_outbox WHERE seq = ? AND claimed_by = ?", (seq, worker)
            ).fetchone()
            if row is None:
                return "lost"
            attempts = int(row[0]) + 1
            msg = error[:1000]
            if attempts >= max_attempts:
                self._conn.execute(
                    "UPDATE pack_h_outbox SET attempts = ?, last_error = ?, dead_at = ?, claimed_by = NULL, "
                    "claimed_until = NULL WHERE seq = ?",
                    (attempts, msg, now, seq),
                )
                return "dead"
            delay = min(max_backoff_s, backoff_s * (2 ** (attempts - 1)))
            self._conn.execute(
                "UPDATE pack_h_outbox SET attempts = ?, last_error = ?, available_at = ?, claimed_by = NULL, "
                "claimed_until = NULL WHERE seq = ?",
                (attempts, msg, now + delay, seq),
            )
            return "retry"

    def requeue_dead(self, seqs: Optional[Iterable[int]] = None) -> int:
        """Operator action: move dead-lettered events back to ready."""
        now = self._clock()
        with self._lock:
            if seqs is None:
                cur = self._conn.execute(
                    "UPDATE pack_h_outbox SET dead_at = NULL, attempts = 0, available_at = ? WHERE dead_at IS NOT NULL",
                    (now,),
                )
            else:
                ids = [(now, int(s)) for s in seqs]
                cur = self._conn.executemany(
                    "UPDATE pack_h_outbox SET dead_at = NULL, attempts = 0, available_at = ? "
                    "WHERE seq = ? AND dead_at IS NOT NULL",
                    ids,
                )
        return cur.rowcount or 0

    def purge_delivered(self, older_than_s: float) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM pack_h_outbox WHERE delivered_at IS NOT NULL AND delivered_at <= ?",
                (self._clock() - older_than_s,),
            )
        return cur.rowcount or 0

    def counts(self) -> Dict[str, int]:
        now = self._clock()
        with self._lock:
            row = self._conn.execute(
                "SELECT "
                "SUM(CASE WHEN delivered_at IS NULL AND dead_at IS NULL AND available_at <= ? THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN delivered_at IS NULL AND dead_at IS NULL AND available_at > ? THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN delivered_at IS NOT NULL THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN dead_at IS NOT NULL THEN 1 ELSE 0 END) FROM pack_h_outbox",
                (now, now),
            ).fetchone()
        return {
            "ready": int(row[0] or 0),
            "scheduled": int(row[1] or 0),
            "delivered": int(row[2] or 0),
            "dead": int(row[3] or 0),
        }

    def events_for(self, aggregate_type: str, aggregate_id: str) -> List[DomainEvent]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT event_id, event_type, payload_json, headers_json FROM pack_h_outbox "
                "WHERE aggregate_type = ? AND aggregate_id = ? ORDER BY seq",
                (aggregate_type, aggregate_id),
            ).fetchall()
        return [
            DomainEvent(aggregate_type, aggregate_id, r[1], json.loads(r[2]), event_id=r[0], headers=json.loads(r[3]))
            for r in rows
        ]


class OutboxRelay:
    """Claims ready events and publishes them, at least once, in seq order."""

    def __init__(
        self,
        outbox: Outbox,
        publisher: Publisher,
        *,
        worker_id: Optional[str] = None,
        batch_size: int = 100,
        lease_s: float = 30.0,
        max_attempts: int = 8,
        backoff_s: float = 0.5,
        max_backoff_s: float = 300.0,
        poll_interval_s: float = 0.25,
    ) -> None:
        self.outbox = outbox
        self.publisher = publisher
        self.worker_id = worker_id or f"relay-{uuid.uuid4().hex[:12]}"
        self.batch_size = batch_size
        self.lease_s = lease_s
        self.max_attempts = max_attempts
        self.backoff_s = backoff_s
        self.max_backoff_s = max_backoff_s
        self.poll_interval_s = poll_interval_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.published = 0
        self.retried = 0
        self.dead = 0

    def run_once(self) -> int:
        """Process one batch; returns events delivered."""
        delivered = 0
        for record in self.outbox.claim(self.worker_id, limit=self.batch_size, lease_s=self.lease_s):
            try:
                self.publisher(record)
            except Exception as exc:
                verdict = self.outbox.mark_failed(
                    self.worker_id, record.seq, f"{type(exc).__name__}: {exc}",
                    max_attempts=self.max_attempts, backoff_s=self.backoff_s, max_backoff_s=self.max_backoff_s,
                )
                if verdict == "dead":
                    self.dead += 1
                elif verdict == "retry":
                    self.retried += 1
                continue
            if self.outbox.mark_delivered(self.worker_id, record.seq):
                delivered += 1
                self.published += 1
        return delivered

    def drain(self, *, max_batches: int = 1000) -> int:
        total = 0
        for _ in range(max_batches):
            n = self.run_once()
            total += n
            if n == 0:
                break
        return total

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()

        def loop() -> None:
            while not self._stop.is_set():
                try:
                    if self.run_once() == 0:
                        self._stop.wait(self.poll_interval_s)
                except Exception:
                    self._stop.wait(self.poll_interval_s)

        self._thread = threading.Thread(target=loop, name=f"pack-h-outbox-{self.worker_id}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def stats(self) -> Dict[str, Any]:
        return {"worker_id": self.worker_id, "published": self.published, "retried": self.retried,
                "dead": self.dead, **self.outbox.counts()}


class ConsumerLedger:
    """Consumer-side dedupe so at-least-once becomes effectively-once."""

    def __init__(self, outbox: Outbox, consumer: str) -> None:
        if not consumer:
            raise OutboxError("consumer name required")
        self.outbox = outbox
        self.consumer = consumer

    def first_time(self, event_id: str) -> bool:
        with self.outbox.lock:
            cur = self.outbox.connection.execute(
                "INSERT OR IGNORE INTO pack_h_outbox_consumed (consumer, event_id, consumed_at) VALUES (?, ?, ?)",
                (self.consumer, event_id, time.time()),
            )
        return (cur.rowcount or 0) == 1

    def handler(self, fn: Callable[[OutboxRecord], None]) -> Publisher:
        """Wrap a handler so duplicates are skipped after a successful run."""

        def wrapped(record: OutboxRecord) -> None:
            with self.outbox.lock:
                seen = self.outbox.connection.execute(
                    "SELECT 1 FROM pack_h_outbox_consumed WHERE consumer = ? AND event_id = ?",
                    (self.consumer, record.event.event_id),
                ).fetchone()
            if seen:
                return
            fn(record)
            self.first_time(record.event.event_id)

        return wrapped
