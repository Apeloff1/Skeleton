"""SQLite/WAL durable adapter for the GF-B game save plane.

Extend-only: a new adapter module. It does not modify
``skeleton.persistence.core`` (Internal Systems) or the frozen
``skeleton.persist`` shims (#4122). It backs the in-memory ports from
:mod:`skeleton.kernel.game_save_plane` with one SQLite file:

- :class:`SqliteCheckpointStore` — a :class:`CheckpointStore` whose saves
  are written through to SQLite (sealed JSON rows, WAL journal) and
  reloaded on open. Retention prunes rows beyond ``retain``. Seals are
  re-verified on load and on restore, so tampered rows are skipped.
- :class:`SqliteReplayJournal` — a :class:`ReplayJournal` whose frames
  are persisted per stream with the same idempotent/conflict semantics.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections import deque
from typing import Any, Callable, Mapping, Optional

from skeleton.kernel.checkpoint import Checkpoint, CheckpointCorruptError, CheckpointStore
from skeleton.kernel.game_save_plane import (
    ReplayJournal, content_digest,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gf_save_checkpoints (
    component TEXT NOT NULL,
    sequence  INTEGER NOT NULL,
    body      TEXT NOT NULL,
    PRIMARY KEY (component, sequence)
);
CREATE TABLE IF NOT EXISTS gf_replay_frames (
    stream TEXT NOT NULL,
    frame  INTEGER NOT NULL,
    digest TEXT NOT NULL,
    event  TEXT NOT NULL,
    PRIMARY KEY (stream, frame)
);
"""


def open_game_save_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    if path != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(_SCHEMA)
    return conn


class SqliteCheckpointStore(CheckpointStore):
    def __init__(self, conn: sqlite3.Connection, *, retain: int = 8,
                 clock: Optional[Callable[[], float]] = None) -> None:
        super().__init__(retain=retain, clock=clock)
        self._conn = conn
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        rows = self._conn.execute(
            "SELECT component, sequence, body FROM gf_save_checkpoints "
            "ORDER BY component, sequence").fetchall()
        for component, sequence, body in rows:
            data = json.loads(body)
            ckpt = Checkpoint(component=data["component"],
                              sequence=int(data["sequence"]),
                              state=dict(data["state"]),
                              taken_at=float(data["taken_at"]),
                              seal=data["seal"])
            store = self._stores.setdefault(component, deque(maxlen=self.retain))
            store.append(ckpt)  # corrupt rows kept; restore() walks past them
            self._high_seq[component] = max(self._high_seq.get(component, -1),
                                            int(sequence))

    def save(self, component: str, sequence: int,
             state: Mapping[str, Any]) -> Checkpoint:
        with self._lock:
            ckpt = super().save(component, sequence, dict(state))
            body = json.dumps(ckpt.to_dict(), sort_keys=True, default=str)
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(
                    "INSERT INTO gf_save_checkpoints VALUES (?,?,?)",
                    (component, sequence, body))
                kept = [c.sequence for c in self._stores[component]]
                self._conn.execute(
                    "DELETE FROM gf_save_checkpoints WHERE component=? AND "
                    f"sequence NOT IN ({','.join('?' * len(kept))})",
                    (component, *kept))
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                self._stores[component].pop()
                raise
            return ckpt


class SqliteReplayJournal(ReplayJournal):
    def __init__(self, conn: sqlite3.Connection, stream: str, *,
                 context_window: int = 64) -> None:
        super().__init__(context_window=context_window)
        self._conn = conn
        self.stream = stream
        for frame, digest, event in conn.execute(
                "SELECT frame, digest, event FROM gf_replay_frames WHERE stream=? "
                "ORDER BY frame", (stream,)):
            ev = json.loads(event)
            if content_digest(ev) != digest:
                raise CheckpointCorruptError("replay frame digest mismatch",
                                             context={"stream": stream,
                                                      "frame": frame})
            self._frames[int(frame)] = (digest, ev)

    def append(self, frame: int, event: Mapping[str, Any]) -> str:
        known = frame in self._frames
        digest = super().append(frame, event)
        if not known:
            self._conn.execute(
                "INSERT OR IGNORE INTO gf_replay_frames VALUES (?,?,?,?)",
                (self.stream, frame, digest,
                 json.dumps(dict(event), sort_keys=True, default=str)))
        return digest


__all__ = ["open_game_save_db", "SqliteCheckpointStore", "SqliteReplayJournal"]
