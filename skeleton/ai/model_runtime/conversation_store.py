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
        if path != ":memory:":
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
        if not isinstance(session, NativeConversationSession) or session.runtime is not self.runtime:
            raise RuntimeContractError("session belongs to another native runtime")
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
        if not isinstance(session_id, str) or not 8 <= len(session_id) <= 256 or any(ord(ch) < 33 or ord(ch) > 126 for ch in session_id):
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
        if isinstance(older_than, bool) or not isinstance(older_than, (int, float)) or not 0 <= older_than <= time.time():
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

    def revisions(self, session_ids: tuple[str, ...]) -> Mapping[str, int]:
        with self._lock:
            ids = tuple(session_ids)
            if len(set(ids)) != len(ids):
                raise RuntimeContractError("duplicate session identifiers")
            result = {}
            for sid in ids:
                row = self._db.execute(
                    "SELECT revision FROM conversations WHERE session_id=?", (sid,)).fetchone()
                if row is None:
                    raise RuntimeContractError("unknown stored conversation")
                result[sid] = row[0]
            return result

    def save_many(self, updates: tuple[tuple[str, int, NativeConversationSession], ...],
                  *, pinned: Mapping[str, bool] | None = None) -> Mapping[str, int]:
        """Atomic multi-session compare-and-swap; no partial commits."""
        items = tuple(updates)
        ids = [item[0] for item in items]
        if len(set(ids)) != len(ids):
            raise RuntimeContractError("duplicate session identifiers")
        encoded = []
        for sid, revision, session in items:
            if type(revision) is not int or revision < 0:
                raise RuntimeContractError("invalid expected revision")
            encoded.append((sid, revision, self._encode(session)))
        if pinned is not None:
            if set(pinned) != set(ids) or any(type(value) is not bool for value in pinned.values()):
                raise RuntimeContractError("invalid batch pin policy")
        now = time.time()
        with self._transaction():
            for sid, revision, payload in encoded:
                if pinned is None:
                    cursor = self._db.execute(
                        "UPDATE conversations SET revision=revision+1, updated_at=?, snapshot_json=? "
                        "WHERE session_id=? AND revision=?",
                        (now, payload, sid, revision))
                else:
                    cursor = self._db.execute(
                        "UPDATE conversations SET revision=revision+1, updated_at=?, snapshot_json=?, pinned=? "
                        "WHERE session_id=? AND revision=?",
                        (now, payload, int(pinned[sid]), sid, revision))
                if cursor.rowcount != 1:
                    raise RuntimeContractError("conversation batch revision conflict")
        return {sid: revision + 1 for sid, revision, _ in encoded}

    def delete_many(self, expected: Mapping[str, int]) -> int:
        """Atomic conditional cohort deletion."""
        with self._transaction():
            for sid, revision in expected.items():
                if type(revision) is not int or revision < 0:
                    raise RuntimeContractError("invalid expected revision")
                cursor = self._db.execute(
                    "DELETE FROM conversations WHERE session_id=? AND revision=?",
                    (sid, revision))
                if cursor.rowcount != 1:
                    raise RuntimeContractError("conversation batch revision conflict")
        return len(expected)

    def list_pinned(self, *, limit: int = 100) -> tuple[str, ...]:
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise RuntimeContractError("invalid page limit")
        with self._lock:
            rows = self._db.execute(
                "SELECT session_id FROM conversations WHERE pinned=1 "
                "ORDER BY updated_at, session_id LIMIT ?", (limit,)).fetchall()
        return tuple(row[0] for row in rows)

    def list_stale(self, older_than: float, *, limit: int = 100) -> tuple[str, ...]:
        if not isinstance(older_than, (int, float)) or not 0 <= older_than <= time.time():
            raise RuntimeContractError("invalid expiration cutoff")
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise RuntimeContractError("invalid page limit")
        with self._lock:
            rows = self._db.execute(
                "SELECT session_id FROM conversations WHERE pinned=0 AND updated_at < ? "
                "ORDER BY updated_at, session_id LIMIT ?", (older_than, limit)).fetchall()
        return tuple(row[0] for row in rows)

    def integrity_check(self) -> bool:
        with self._lock:
            rows = self._db.execute("PRAGMA integrity_check").fetchall()
            if rows != [("ok",)]:
                raise RuntimeContractError("conversation database integrity failure")
            return True

    def verify_all(self, *, batch_size: int = 100) -> int:
        """Validate every stored snapshot against the active native model."""
        if type(batch_size) is not int or not 1 <= batch_size <= 10000:
            raise RuntimeContractError("invalid verification batch size")
        with self._lock:
            cursor = self._db.execute(
                "SELECT snapshot_json FROM conversations ORDER BY session_id")
            count = 0
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                for (payload,) in rows:
                    self._decode(payload)
                    count += 1
            return count

    def database_size_bytes(self) -> int:
        with self._lock:
            pages = self._db.execute("PRAGMA page_count").fetchone()[0]
            size = self._db.execute("PRAGMA page_size").fetchone()[0]
            return pages * size

    def checkpoint_wal(self) -> tuple[int, int, int]:
        with self._lock:
            return tuple(self._db.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone())

    def vacuum(self) -> None:
        with self._lock:
            self._db.execute("VACUUM")

    def backup_to(self, destination_path: str) -> None:
        """Consistent SQLite online backup, including committed WAL pages."""
        if not isinstance(destination_path, str) or not destination_path or destination_path == ":memory:":
            raise RuntimeContractError("valid backup destination required")
        with self._lock:
            destination = sqlite3.connect(destination_path)
            try:
                self._db.backup(destination)
            finally:
                destination.close()

    def read_page(self, *, limit: int = 100, offset: int = 0) -> tuple[StoredConversation, ...]:
        """Return a bounded, identity-validated page of durable sessions."""
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise RuntimeContractError("invalid page limit")
        if type(offset) is not int or offset < 0:
            raise RuntimeContractError("invalid page offset")
        with self._lock:
            rows = self._db.execute(
                "SELECT session_id, revision, created_at, updated_at, pinned, snapshot_json "
                "FROM conversations ORDER BY created_at, session_id LIMIT ? OFFSET ?",
                (limit, offset)).fetchall()
            return tuple(StoredConversation(sid, rev, created, updated, bool(pinned),
                                            self._decode(payload))
                         for sid, rev, created, updated, pinned, payload in rows)

    def close(self) -> None:
        with self._lock:
            self._db.close()


__all__ = ["ConversationStore", "StoredConversation"]
