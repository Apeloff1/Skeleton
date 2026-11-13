"""SQLite hash-chained event journal and idempotent durable receipts.

The journal is an integrity-checked audit *companion*; the existing
OfflineChatStore remains the sole conversation authority. SQLite uses one
BEGIN IMMEDIATE writer, no in-memory success cache and no auto replay of
unknown external effects. A missing middle event invalidates the chain.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import threading
from typing import Any, Iterator
from contextlib import contextmanager

from ..authority.canonical import ContractViolation, canonical_bytes, load_json, sha256
from ..authority.identity import require_id

GENESIS = "0" * 64


class JournalError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Event:
    seq: int
    stream: str
    event_id: str
    kind: str
    payload: dict[str, Any]
    previous_digest: str
    digest: str
    replayed: bool = False


def _event_digest(seq: int, stream: str, event_id: str, kind: str,
                  payload: bytes, previous: str) -> str:
    head = canonical_bytes({"seq": seq, "stream": stream, "event_id": event_id,
                            "kind": kind, "previous": previous}, ceiling=64_000)
    return hashlib.sha256(len(head).to_bytes(4, "big") + head + payload).hexdigest()


def _secure_path(path: str | Path) -> str:
    if str(path) == ":memory:":
        return ":memory:"
    root = Path(path).absolute()
    if root.is_symlink() or root.parent.is_symlink() or not root.parent.is_dir():
        raise JournalError("journal requires an existing trusted directory and no symlink")
    for part in [root, root.with_name(root.name + "-wal"), root.with_name(root.name + "-shm")]:
        if part.is_symlink():
            raise JournalError("journal file or SQLite sidecar is a symlink")
        if part.exists():
            mode = part.stat().st_mode
            if not stat.S_ISREG(mode) or mode & 0o077:
                raise JournalError("journal file is not private and regular")
    if root.parent.stat().st_mode & 0o022:
        raise JournalError("journal directory is writable by other users")
    return str(root)


class EventJournal:
    def __init__(self, path: str | Path = ":memory:") -> None:
        name = _secure_path(path)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(name, isolation_level=None, timeout=10,
                                   check_same_thread=False)
        self._db.execute("PRAGMA busy_timeout=10000")
        self._db.execute("PRAGMA foreign_keys=ON")
        if name != ":memory:":
            os.chmod(name, 0o600)
            self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS ai_events (
            stream TEXT NOT NULL, seq INTEGER NOT NULL, event_id TEXT NOT NULL,
            kind TEXT NOT NULL, payload BLOB NOT NULL, previous TEXT NOT NULL,
            digest TEXT NOT NULL, PRIMARY KEY(stream,seq), UNIQUE(stream,event_id)
        )""")
        self._db.execute("CREATE INDEX IF NOT EXISTS ix_ai_events_kind ON ai_events(kind)")
        if self._db.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise JournalError("SQLite integrity check failed")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise

    def append(self, *, stream: str, event_id: str, kind: str,
               payload: dict[str, Any]) -> Event:
        require_id(stream, field="stream")
        require_id(event_id, field="event id")
        require_id(kind, field="event kind")
        raw = canonical_bytes(payload, ceiling=65_536)
        with self.transaction() as db:
            existing = db.execute("SELECT seq,kind,payload,previous,digest FROM ai_events "
                                  "WHERE stream=? AND event_id=?", (stream,event_id)).fetchone()
            if existing is not None:
                seq, old_kind, old_payload, previous, record_hash = existing
                if old_kind != kind or old_payload != raw:
                    raise JournalError("event ID reused with different data")
                # Verify the entire stream even on idempotent replay.
                self._read_locked(stream, db)
                return Event(seq,stream,event_id,kind,payload,previous,record_hash,True)
            tail = self._read_locked(stream, db)
            seq = tail[-1].seq + 1 if tail else 1
            previous = tail[-1].digest if tail else GENESIS
            record_hash = _event_digest(seq,stream,event_id,kind,raw,previous)
            db.execute("INSERT INTO ai_events VALUES (?,?,?,?,?,?,?)",
                       (stream,seq,event_id,kind,raw,previous,record_hash))
            return Event(seq,stream,event_id,kind,payload,previous,record_hash)

    def _read_locked(self, stream: str, db: sqlite3.Connection) -> list[Event]:
        rows = db.execute("SELECT seq,event_id,kind,payload,previous,digest FROM ai_events "
                          "WHERE stream=? ORDER BY seq", (stream,)).fetchall()
        prev = GENESIS
        seen: set[str] = set()
        events: list[Event] = []
        for seq,event_id,kind,raw,previous,record_hash in rows:
            if type(seq) is not int or seq != len(events)+1 or event_id in seen or previous != prev:
                raise JournalError("journal sequence, uniqueness, or previous hash mismatch")
            if not isinstance(raw, bytes) or not isinstance(record_hash, str):
                raise JournalError("corrupted event payload")
            if _event_digest(seq,stream,event_id,kind,raw,previous) != record_hash:
                raise JournalError("journal content hash mismatch")
            payload = load_json(raw, ceiling=65_536)
            if not isinstance(payload, dict):
                raise JournalError("journal event must be an object")
            events.append(Event(seq,stream,event_id,kind,payload,previous,record_hash))
            seen.add(event_id)
            prev = record_hash
        return events

    def replay(self, stream: str) -> tuple[Event, ...]:
        require_id(stream, field="stream")
        with self._lock:
            self._db.execute("BEGIN")
            try:
                return tuple(self._read_locked(stream, self._db))
            finally:
                self._db.execute("ROLLBACK")

    def head(self, stream: str) -> tuple[int, str]:
        events = self.replay(stream)
        return (events[-1].seq, events[-1].digest) if events else (0, GENESIS)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "EventJournal":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
