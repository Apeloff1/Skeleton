"""SQLite-backed durable conversation state with optimistic concurrency.

No pickle, dynamic SQL identifiers, or implicit trust in persisted state.
Snapshots are revalidated against the currently admitted native model on load.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
import sqlite3
import threading
import time
from typing import Any, Iterator, Mapping

from .native_llm_runtime import NativeConversationSession, NativeLLMRuntime
from .runtime_contracts import RuntimeContractError


@dataclass(frozen=True)
class StoredConversation:
    session_id: str
    revision: int
    created_at: float
    updated_at: float
    pinned: bool
    snapshot: Mapping[str, Any]


class ConversationStore:
    """Transactional persistence for token-native chat sessions."""

    def __init__(self, path: str, runtime: NativeLLMRuntime, *,
                 max_snapshot_bytes: int = 2_000_000) -> None:
        if not isinstance(path, str) or not path:
            raise RuntimeContractError("nonempty database path required")
        if not isinstance(runtime, NativeLLMRuntime):
            raise RuntimeContractError("NativeLLMRuntime required")
        if type(max_snapshot_bytes) is not int or not 1024 <= max_snapshot_bytes <= 64_000_000:
            raise RuntimeContractError("invalid snapshot budget")
        self.runtime = runtime
        self.max_snapshot_bytes = max_snapshot_bytes
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None,
                                   timeout=10.0)
        self._db.execute("PRAGMA busy_timeout=10000")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS conversations (
            session_id TEXT PRIMARY KEY,
            revision INTEGER NOT NULL CHECK(revision >= 0),
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            pinned INTEGER NOT NULL CHECK(pinned IN (0, 1)),
            snapshot_json TEXT NOT NULL
        )""")
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_conversations_updated ON conversations(updated_at)")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            else:
                self._db.execute("COMMIT")

    def _encode(self, session: NativeConversationSession) -> str:
        snapshot = session.snapshot()
        payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if len(payload.encode("utf-8")) > self.max_snapshot_bytes:
            raise RuntimeContractError("conversation snapshot exceeds storage budget")
        return payload

    def _decode(self, payload: str) -> Mapping[str, Any]:
        if len(payload.encode("utf-8")) > self.max_snapshot_bytes:
            raise RuntimeContractError("stored conversation exceeds storage budget")
        try:
            obj = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise RuntimeContractError("corrupted conversation JSON") from exc
        NativeConversationSession.restore(self.runtime, obj)
        return obj

    def create(self, session_id: str, session: NativeConversationSession, *,
               pinned: bool = False) -> int:
        if not isinstance(session_id, str) or not 8 <= len(session_id) <= 256:
            raise RuntimeContractError("invalid session identifier")
        if type(pinned) is not bool:
            raise RuntimeContractError("invalid pinned state")
        payload = self._encode(session)
        now = time.time()
        with self._transaction():
            try:
                self._db.execute(
                    "INSERT INTO conversations VALUES (?, 0, ?, ?, ?, ?)",
                    (session_id, now, now, int(pinned), payload))
            except sqlite3.IntegrityError as exc:
                raise RuntimeContractError("conversation already exists") from exc
        return 0

    def load(self, session_id: str) -> StoredConversation:
        with self._lock:
            row = self._db.execute(
                "SELECT revision, created_at, updated_at, pinned, snapshot_json "
                "FROM conversations WHERE session_id=?", (session_id,)).fetchone()
        if row is None:
            raise RuntimeContractError("unknown stored conversation")
        snapshot = self._decode(row[4])
        return StoredConversation(session_id, row[0], row[1], row[2], bool(row[3]), snapshot)

    def restore_session(self, session_id: str) -> NativeConversationSession:
        return NativeConversationSession.restore(self.runtime, self.load(session_id).snapshot)

    def save(self, session_id: str, expected_revision: int,
             session: NativeConversationSession, *, pinned: bool | None = None) -> int:
        if type(expected_revision) is not int or expected_revision < 0:
            raise RuntimeContractError("invalid expected revision")
        if pinned is not None and type(pinned) is not bool:
            raise RuntimeContractError("invalid pinned state")
        payload = self._encode(session)
        with self._transaction():
            if pinned is None:
                cursor = self._db.execute(
                    "UPDATE conversations SET revision=revision+1, updated_at=?, snapshot_json=? "
                    "WHERE session_id=? AND revision=?",
                    (time.time(), payload, session_id, expected_revision))
            else:
                cursor = self._db.execute(
                    "UPDATE conversations SET revision=revision+1, updated_at=?, "
                    "snapshot_json=?, pinned=? WHERE session_id=? AND revision=?",
                    (time.time(), payload, int(pinned), session_id, expected_revision))
            if cursor.rowcount != 1:
                raise RuntimeContractError("conversation missing or revision conflict")
        return expected_revision + 1

    def delete(self, session_id: str, *, expected_revision: int | None = None) -> None:
        with self._transaction():
            if expected_revision is None:
                cursor = self._db.execute(
                    "DELETE FROM conversations WHERE session_id=?", (session_id,))
            else:
                if type(expected_revision) is not int or expected_revision < 0:
                    raise RuntimeContractError("invalid expected revision")
                cursor = self._db.execute(
                    "DELETE FROM conversations WHERE session_id=? AND revision=?",
                    (session_id, expected_revision))
            if cursor.rowcount != 1:
                raise RuntimeContractError("conversation missing or revision conflict")

    def exists(self, session_id: str) -> bool:
        with self._lock:
            return self._db.execute(
                "SELECT 1 FROM conversations WHERE session_id=?", (session_id,)).fetchone() is not None

    def count(self) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]

    def list_ids(self, *, limit: int = 100, offset: int = 0) -> tuple[str, ...]:
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise RuntimeContractError("invalid page limit")
        if type(offset) is not int or offset < 0:
            raise RuntimeContractError("invalid page offset")
        with self._lock:
            rows = self._db.execute(
                "SELECT session_id FROM conversations ORDER BY created_at, session_id "
                "LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return tuple(row[0] for row in rows)

    def prune_idle(self, older_than: float) -> int:
        if not isinstance(older_than, (int, float)) or not 0 <= older_than <= time.time():
            raise RuntimeContractError("invalid expiration cutoff")
        with self._transaction():
            cursor = self._db.execute(
                "DELETE FROM conversations WHERE pinned=0 AND updated_at < ?",
                (older_than,))
            return cursor.rowcount

    def pin(self, session_id: str, expected_revision: int, pinned: bool) -> int:
        if type(pinned) is not bool or type(expected_revision) is not int or expected_revision < 0:
            raise RuntimeContractError("invalid pin operation")
        with self._transaction():
            cursor = self._db.execute(
                "UPDATE conversations SET pinned=?, revision=revision+1, updated_at=? "
                "WHERE session_id=? AND revision=?",
                (int(pinned), time.time(), session_id, expected_revision))
            if cursor.rowcount != 1:
                raise RuntimeContractError("conversation missing or revision conflict")
        return expected_revision + 1

    def close(self) -> None:
        with self._lock:
            self._db.close()


__all__ = ["ConversationStore", "StoredConversation"]
