"""Local-only, revisioned transcript workspace for offline app conversations.

This is user-controlled desktop/headless *context persistence*, not the
authoritative production conversation/operation repository. No hosted services
or model tools run here. SQLite transactions provide durable complete-turn
snapshots, model binding and stale-writer rejection.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import os
import re
import sqlite3
import threading
from typing import Any, Protocol

from .offline_history import _history, _canonical, _model_digest, MAX_BACKUP_BYTES


_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SCHEMA = "skeleton.app.offline_workspace.v1"


class OfflineWorkspaceError(RuntimeError):
    """The local workspace cannot accept or restore a safe transcript."""


class OfflineWorkspaceConflict(OfflineWorkspaceError):
    """A stale writer cannot overwrite a committed conversation revision."""


def _session_id(value: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise OfflineWorkspaceError("invalid offline session id")
    return value


def _snapshot(history: tuple[tuple[str, str], ...]) -> tuple[str, str]:
    turns = _history(history)
    data = _canonical([[role, text] for role, text in turns])
    if len(data) > MAX_BACKUP_BYTES:
        raise OfflineWorkspaceError("offline transcript exceeds storage quota")
    return data.decode("utf-8"), hashlib.sha256(data).hexdigest()


def _load_snapshot(text: str, digest: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BACKUP_BYTES:
        raise OfflineWorkspaceError("stored transcript exceeds quota")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise OfflineWorkspaceError("stored transcript checksum is invalid")
    raw = text.encode("utf-8")
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), digest):
        raise OfflineWorkspaceError("stored transcript integrity mismatch")
    try:
        data = json.loads(text)
    except (ValueError, UnicodeError) as exc:
        raise OfflineWorkspaceError("stored transcript JSON is malformed") from exc
    try:
        return _history(data)
    except ValueError as exc:
        raise OfflineWorkspaceError("stored transcript fails turn validation") from exc


class OfflineWorkspace:
    """Bounded local SQLite snapshots with compare-and-swap and model fencing."""

    def __init__(self, path: str | Path) -> None:
        target = Path(path).expanduser()
        if not target.parent.is_dir() or target.is_symlink():
            raise OfflineWorkspaceError("workspace requires a non-symlink local file path")
        if target.exists() and not target.is_file():
            raise OfflineWorkspaceError("workspace path must be a regular file")
        self.path = target
        self._lock = threading.RLock()
        was_present = target.exists()
        try:
            # GUI inference runs in a worker thread; all SQLite connection use is
            # serialized by _lock and busy_timeout guards other processes.
            self._db = sqlite3.connect(
                str(target), timeout=10.0, isolation_level=None,
                check_same_thread=False,
            )
            # Never leave newly created user conversation data world-readable
            # on POSIX. Do not silently modify the permissions of existing DBs.
            if not was_present and os.name == "posix":
                os.chmod(target, 0o600)
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("""CREATE TABLE IF NOT EXISTS offline_conversations (
                session_id TEXT PRIMARY KEY,
                model_digest TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision >= 0),
                history_json TEXT NOT NULL,
                history_sha256 TEXT NOT NULL
            )""")
        except sqlite3.Error as exc:
            raise OfflineWorkspaceError("cannot initialize local SQLite workspace") from exc

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "OfflineWorkspace":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def open(self, session_id: str, model_digest: str) -> tuple[int, tuple[tuple[str, str], ...]]:
        sid, model = _session_id(session_id), _model_digest(model_digest)
        empty, digest = _snapshot(())
        with self._lock:
            try:
                self._db.execute(
                    "INSERT OR IGNORE INTO offline_conversations VALUES (?, ?, 0, ?, ?)",
                    (sid, model, empty, digest),
                )
                row = self._db.execute(
                    "SELECT model_digest, revision, history_json, history_sha256 "
                    "FROM offline_conversations WHERE session_id=?", (sid,),
                ).fetchone()
            except sqlite3.Error as exc:
                raise OfflineWorkspaceError("cannot read local SQLite workspace") from exc
        if row is None or row[0] != model:
            raise OfflineWorkspaceError("workspace session belongs to a different model")
        if type(row[1]) is not int or row[1] < 0:
            raise OfflineWorkspaceError("invalid stored workspace revision")
        return row[1], _load_snapshot(row[2], row[3])

    def save(
        self, session_id: str, model_digest: str, revision: int,
        history: tuple[tuple[str, str], ...],
    ) -> int:
        sid, model = _session_id(session_id), _model_digest(model_digest)
        if type(revision) is not int or revision < 0:
            raise OfflineWorkspaceError("expected revision must be a nonnegative integer")
        raw, checksum = _snapshot(history)
        with self._lock:
            try:
                cursor = self._db.execute(
                    "UPDATE offline_conversations "
                    "SET revision=revision+1, history_json=?, history_sha256=? "
                    "WHERE session_id=? AND model_digest=? AND revision=?",
                    (raw, checksum, sid, model, revision),
                )
            except sqlite3.Error as exc:
                raise OfflineWorkspaceError("cannot commit offline SQLite transcript") from exc
        if cursor.rowcount != 1:
            raise OfflineWorkspaceConflict("offline workspace revision conflict")
        return revision + 1

    def list_sessions(self, *, limit: int = 100) -> tuple[str, ...]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise OfflineWorkspaceError("invalid session list limit")
        with self._lock:
            try:
                rows = self._db.execute(
                    "SELECT session_id FROM offline_conversations ORDER BY session_id LIMIT ?",
                    (limit,),
                ).fetchall()
            except sqlite3.Error as exc:
                raise OfflineWorkspaceError("cannot list offline sessions") from exc
        return tuple(row[0] for row in rows)


class _Session(Protocol):
    history: tuple[tuple[str, str], ...]
    @property
    def model_digest(self) -> str: ...
    @property
    def max_interactive_tokens(self) -> int: ...
    async def ask(
        self, prompt: str, *, max_output_tokens: int = 32,
        inference_prompt: str | None = None,
    ) -> Any: ...
    def save_history_backup(self, path: str | Path) -> str: ...
    def restore_history_backup(self, path: str | Path) -> int: ...


class DurableOfflineSession:
    """Opt-in durable shell around an admitted local inference session.

    Inference is delegated to the existing native/GGUF owner. A result counts
    as successfully delivered only when the full turn reaches durable storage.
    If persistence fails, restore the previous in-memory transcript.
    """

    def __init__(
        self, session: _Session, path: str | Path, *, session_id: str = "default",
    ) -> None:
        self.session = session
        self.store = OfflineWorkspace(path)
        self.session_id = _session_id(session_id)
        try:
            self.revision, restored = self.store.open(self.session_id, session.model_digest)
            if session.history:
                raise OfflineWorkspaceError("durable session requires a fresh local chat")
            session.history = restored
        except BaseException:
            self.store.close()
            raise

    @property
    def history(self) -> tuple[tuple[str, str], ...]:
        return self.session.history

    @property
    def model_digest(self) -> str:
        return self.session.model_digest

    @property
    def max_interactive_tokens(self) -> int:
        return self.session.max_interactive_tokens

    def save_history_backup(self, path: str | Path) -> str:
        return self.session.save_history_backup(path)

    def restore_history_backup(self, path: str | Path) -> int:
        if self.session.history:
            raise OfflineWorkspaceError(
                "start a new conversation before importing a manual backup"
            )
        before = self.session.history
        turns = self.session.restore_history_backup(path)
        try:
            next_revision = self.store.save(
                self.session_id, self.model_digest, self.revision, self.session.history,
            )
        except BaseException:
            self.session.history = before
            raise
        self.revision = next_revision
        return turns

    async def ask(
        self, prompt: str, *, max_output_tokens: int = 32,
        inference_prompt: str | None = None,
    ) -> Any:
        before = self.session.history
        answer = await self.session.ask(
            prompt, max_output_tokens=max_output_tokens,
            inference_prompt=inference_prompt,
        )
        try:
            next_revision = self.store.save(
                self.session_id, self.model_digest, self.revision, self.session.history,
            )
        except BaseException:
            self.session.history = before
            raise
        self.revision = next_revision
        return answer

    def clear(self) -> None:
        prior = self.session.history
        self.session.history = ()
        try:
            self.revision = self.store.save(self.session_id, self.model_digest, self.revision, ())
        except BaseException:
            self.session.history = prior
            raise

    def close(self) -> None:
        self.store.close()


__all__ = [
    "SCHEMA", "OfflineWorkspace", "OfflineWorkspaceError",
    "OfflineWorkspaceConflict", "DurableOfflineSession",
]
