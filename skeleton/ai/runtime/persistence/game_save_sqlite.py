"""Transaction-authoritative SQLite/WAL adapter for the GF-B game save plane.

Checkpoint and replay writes are decided by SQLite under BEGIN IMMEDIATE,
not by a stale Python cache. Readers observe committed SQL rows, and a
failed transaction cannot leave an advanced in-memory sequence or journal.
Connections used concurrently by multiple participants must be independent.
This is a local cooperative database, not an authenticated hostile-DB vault.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import threading
from typing import Any, Callable, Mapping, Optional

from skeleton.kernel.checkpoint import (
    Checkpoint, CheckpointCorruptError, CheckpointError,
    CheckpointSequenceError, CheckpointStore,
)
from skeleton.kernel.game_save_plane import ReplayConflictError, ReplayJournal, content_digest

MAX_SEQUENCE = 2**63 - 1
MAX_ID_CHARS = 512
MAX_CHECKPOINT_BYTES = 64 * 1024 * 1024
MAX_EVENT_BYTES = 2 * 1024 * 1024
MAX_RETAIN = 100_000
MAX_JOURNAL_FRAMES = 1_000_000

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


def _identity(value):
    if (type(value) is not str or not 1 <= len(value) <= MAX_ID_CHARS
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in value)):
        raise CheckpointError("invalid storage identity")
    return value


def _integer(value, *, maximum=MAX_SEQUENCE):
    if type(value) is not int or not 0 <= value <= maximum:
        raise CheckpointError("invalid storage counter")
    return value


def _json(value, ceiling):
    try:
        # Normalize to detached JSON data before the kernel seals it. Preserve
        # the legacy string fallback for existing non-JSON scalar callers.
        raw = json.dumps(value, sort_keys=True, default=str, allow_nan=False)
        if len(raw.encode("utf-8")) > ceiling:
            raise CheckpointError("storage document exceeds byte ceiling")
        return raw
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise CheckpointError("invalid storage document") from exc


def _strict_pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError("duplicate storage field")
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError("nonfinite storage value")


def _decode(raw, ceiling):
    if type(raw) is not str:
        raise CheckpointCorruptError("nontext stored document")
    try:
        if len(raw.encode("utf-8")) > ceiling:
            raise ValueError("stored document byte ceiling")
        value = json.loads(raw, object_pairs_hook=_strict_pairs, parse_constant=_reject_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise CheckpointCorruptError("stored document malformed") from exc
    if type(value) is not dict:
        raise CheckpointCorruptError("stored document not an object")
    return value


def _write_transaction(conn, work):
    """Rollback only a transaction successfully begun by this invocation."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        result = work()
        conn.execute("COMMIT")
        return result
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def open_game_save_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None,
                           timeout=10.0)
    try:
        if path != ":memory:":
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.executescript(_SCHEMA)
        return conn
    except BaseException:
        conn.close()
        raise


def _checkpoint(component, sequence, raw):
    _identity(component)
    _integer(sequence)
    data = _decode(raw, MAX_CHECKPOINT_BYTES)
    if (set(data) != {"component", "sequence", "state", "taken_at", "seal"}
            or data["component"] != component or type(data["sequence"]) is not int
            or data["sequence"] != sequence or type(data["state"]) is not dict
            or type(data["taken_at"]) not in (float, int)
            or not math.isfinite(data["taken_at"])
            or type(data["seal"]) is not str):
        raise CheckpointCorruptError("checkpoint row identity or shape mismatch")
    return Checkpoint(component=component, sequence=sequence, state=data["state"],
                      taken_at=float(data["taken_at"]), seal=data["seal"])


class SqliteCheckpointStore(CheckpointStore):
    """Read through committed rows, preserving the kernel's checkpoint contract."""

    def __init__(self, conn: sqlite3.Connection, *, retain: int = 8,
                 clock: Optional[Callable[[], float]] = None) -> None:
        if type(retain) is not int or not 1 <= retain <= MAX_RETAIN:
            raise CheckpointError("invalid checkpoint retention")
        super().__init__(retain=retain, clock=clock)
        self._conn = conn
        self._lock = threading.RLock()

    def _rows(self, component, *, limit=None, minimum=0):
        _identity(component)
        _integer(minimum)
        return self._conn.execute(
            "SELECT component, sequence, body FROM gf_save_checkpoints "
            "WHERE component=? AND sequence>=? ORDER BY sequence DESC LIMIT ?",
            (component, minimum, self.retain if limit is None else limit),
        )

    def save(self, component: str, sequence: int,
             state: Mapping[str, Any]) -> Checkpoint:
        _identity(component)
        _integer(sequence)
        normalized = _decode(_json(dict(state), MAX_CHECKPOINT_BYTES), MAX_CHECKPOINT_BYTES)
        with self._lock:
            def write():
                high = self._conn.execute(
                    "SELECT MAX(sequence) FROM gf_save_checkpoints WHERE component=?",
                    (component,),
                ).fetchone()[0]
                if high is not None and sequence <= high:
                    raise CheckpointSequenceError(
                        "checkpoint sequence must increase monotonically",
                        context={"component": component, "attempted": sequence,
                                 "latest": high},
                    )
                now = self._now()
                if type(now) not in (float, int) or not math.isfinite(now):
                    raise CheckpointError("invalid checkpoint clock")
                checkpoint = Checkpoint.create(component, sequence, normalized, now=now)
                body = _json(checkpoint.to_dict(), MAX_CHECKPOINT_BYTES)
                self._conn.execute(
                    "INSERT INTO gf_save_checkpoints(component,sequence,body) VALUES(?,?,?)",
                    (component, sequence, body),
                )
                # Compute retention from the durable authority, not from
                # the opening process's possibly stale in-memory window.
                self._conn.execute(
                    "DELETE FROM gf_save_checkpoints WHERE component=? AND sequence NOT IN "
                    "(SELECT sequence FROM gf_save_checkpoints WHERE component=? "
                    "ORDER BY sequence DESC LIMIT ?)",
                    (component, component, self.retain),
                )
                return checkpoint
            return _write_transaction(self._conn, write)

    def latest(self, component: str) -> Optional[Checkpoint]:
        with self._lock:
            row = self._rows(component, limit=1).fetchone()
            return None if row is None else _checkpoint(*row)

    def restore(self, component: str, *, min_sequence: int = 0) -> Optional[Checkpoint]:
        with self._lock:
            # Deliberately bound the fallback to retained rows, not all deleted
            # history. Malformed or invalid seals never qualify as recovery.
            for row in self._rows(component, minimum=min_sequence):
                try:
                    ckpt = _checkpoint(*row)
                    ckpt.verify()
                except CheckpointCorruptError:
                    continue
                return ckpt
            return None

    def history(self, component: str) -> tuple[Checkpoint, ...]:
        with self._lock:
            return tuple(reversed([_checkpoint(*row) for row in self._rows(component)]))

    def components(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(row[0] for row in self._conn.execute(
                "SELECT DISTINCT component FROM gf_save_checkpoints ORDER BY component"
            ))

    def report(self) -> dict:
        with self._lock:
            result = {}
            for component in self.components():
                stored = self.history(component)
                result[component] = {"retained": len(stored),
                    "latest_sequence": stored[-1].sequence if stored else None,
                    "latest_seal": stored[-1].seal[:12] if stored else None}
            return result


def _journal_event(stream, frame, expected_digest, raw):
    _integer(frame)
    event = _decode(raw, MAX_EVENT_BYTES)
    if type(expected_digest) is not str or content_digest(event) != expected_digest:
        raise CheckpointCorruptError("replay frame digest mismatch",
                                     context={"stream": stream, "frame": frame})
    return event


class SqliteReplayJournal(ReplayJournal):
    """Committed, idempotent per-stream events with cross-connection conflict fencing."""

    def __init__(self, conn: sqlite3.Connection, stream: str, *,
                 context_window: int = 64) -> None:
        if type(context_window) is not int or not 1 <= context_window <= 4096:
            raise CheckpointError("invalid journal context window")
        super().__init__(context_window=context_window)
        self._conn = conn
        self.stream = _identity(stream)
        self._lock = threading.RLock()
        # Preserve eager corruption detection without retaining an unbounded
        # process-local copy of all journal events.
        self.head_digest()

    def append(self, frame: int, event: Mapping[str, Any]) -> str:
        _integer(frame)
        raw = _json(dict(event), MAX_EVENT_BYTES)
        normalized = _decode(raw, MAX_EVENT_BYTES)
        observed_digest = content_digest(normalized)
        with self._lock:
            def write():
                row = self._conn.execute(
                    "SELECT digest,event FROM gf_replay_frames WHERE stream=? AND frame=?",
                    (self.stream, frame),
                ).fetchone()
                if row is not None:
                    other = _journal_event(self.stream, frame, row[0], row[1])
                    if row[0] != observed_digest or content_digest(other) != observed_digest:
                        raise ReplayConflictError("frame already recorded with different event",
                                                  context={"frame": frame})
                    return observed_digest
                total = self._conn.execute(
                    "SELECT COUNT(*) FROM gf_replay_frames WHERE stream=?", (self.stream,)
                ).fetchone()[0]
                if total >= MAX_JOURNAL_FRAMES:
                    raise CheckpointError("journal stream entry ceiling")
                self._conn.execute(
                    "INSERT INTO gf_replay_frames(stream,frame,digest,event) VALUES(?,?,?,?)",
                    (self.stream, frame, observed_digest, raw),
                )
                return observed_digest
            return _write_transaction(self._conn, write)

    def _rows(self, after=-1):
        if type(after) is not int or not -1 <= after <= MAX_SEQUENCE:
            raise CheckpointError("invalid journal cursor")
        return self._conn.execute(
            "SELECT frame,digest,event FROM gf_replay_frames WHERE stream=? AND frame>? "
            "ORDER BY frame LIMIT ?", (self.stream, after, MAX_JOURNAL_FRAMES + 1),
        )

    def frames(self, *, after: int = -1):
        with self._lock:
            result = []
            for index, (frame, expected, raw) in enumerate(self._rows(after)):
                if index >= MAX_JOURNAL_FRAMES:
                    raise CheckpointError("journal stream entry ceiling")
                result.append((frame, _journal_event(self.stream, frame, expected, raw)))
            return result

    def ai_context(self, *, upto: Optional[int] = None):
        upper = MAX_SEQUENCE if upto is None else _integer(upto)
        with self._lock:
            rows = self._conn.execute(
                "SELECT frame,digest,event FROM gf_replay_frames WHERE stream=? AND frame<=? "
                "ORDER BY frame DESC LIMIT ?", (self.stream, upper, self.context_window)
            )
            return list(reversed([_journal_event(self.stream, frame, expected, raw)
                                  for frame, expected, raw in rows]))

    def head_digest(self) -> str:
        """Stream the exact canonical JSON digest list without retaining events."""
        with self._lock:
            digest = hashlib.sha256()
            digest.update(b"[")
            for index, (frame, expected, raw) in enumerate(self._rows()):
                if index >= MAX_JOURNAL_FRAMES:
                    raise CheckpointError("journal stream entry ceiling")
                _journal_event(self.stream, frame, expected, raw)
                if index:
                    digest.update(b",")
                digest.update(json.dumps(expected, separators=(",", ":")).encode("utf-8"))
            digest.update(b"]")
            return digest.hexdigest()


__all__ = ["open_game_save_db", "SqliteCheckpointStore", "SqliteReplayJournal"]
