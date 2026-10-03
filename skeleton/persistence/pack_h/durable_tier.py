"""SQLite durable tier (L3) for TieredCache, with write-behind.

``DurableTier`` is a versioned key/value store with optional expiry and
tombstones. ``WriteBehindQueue`` coalesces writes per key and flushes them to a
tier in batches on size, interval, explicit ``flush()`` or ``close()``. The
queue keeps the newest pending write per key, so a burst of updates to one key
costs one durable write. Readers that consult ``pending()`` before the tier see
their own writes even before the flush lands (read-your-writes).

Crash model: the write-behind buffer is memory-only by design (it is a cache).
A crash loses at most the unflushed window, bounded by ``max_pending`` and
``flush_interval_s``. Flush failures are retried with backoff and never drop
data silently: after ``max_attempts`` failed flushes the batch is handed to the
``on_failure`` callback and counted in ``stats()['dropped']``.
"""

from __future__ import annotations

import math
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from skeleton.persistence.pack_h import codecs
from skeleton.persistence.pack_h.migrations import DURABLE_TIER_MIGRATIONS, connect, migrate

_MISSING = object()


class DurableTierError(RuntimeError):
    pass


class StaleWrite(DurableTierError):
    """A conditional write lost to a newer version."""


@dataclass(frozen=True, slots=True)
class DurableEntry:
    namespace: str
    key: str
    value: Any
    version: int
    expires_at: Optional[float]
    updated_at: float

    def expired(self, now: float) -> bool:
        return self.expires_at is not None and self.expires_at <= now


def _check_ident(value: str, field: str, *, max_len: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise DurableTierError(f"{field} must be a non-empty str of at most {max_len} chars")
    if "\x00" in value:
        raise DurableTierError(f"{field} must not contain NUL")
    return value


def _ttl(ttl_s: Optional[float], now: float) -> Optional[float]:
    if ttl_s is None:
        return None
    t = float(ttl_s)
    if not math.isfinite(t) or t <= 0:
        raise DurableTierError("ttl_s must be finite and positive")
    return now + t


class DurableTier:
    """Versioned SQLite key/value tier. Thread-safe; one connection per tier."""

    def __init__(
        self,
        path: str = ":memory:",
        *,
        namespace: str = "default",
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = path
        self.namespace = _check_ident(namespace, "namespace", max_len=128)
        self._clock = clock
        self._conn = connect(path)
        self._lock = threading.RLock()
        with self._lock:
            migrate(self._conn, "durable_tier", DURABLE_TIER_MIGRATIONS)
        self.reads = 0
        self.read_hits = 0
        self.writes = 0

    # -- reads -------------------------------------------------------------
    def get_entry(self, key: str) -> Optional[DurableEntry]:
        _check_ident(key, "key")
        now = self._clock()
        with self._lock:
            self.reads += 1
            row = self._conn.execute(
                "SELECT value, codec, version, expires_at, updated_at FROM pack_h_cache_entries "
                "WHERE namespace = ? AND key = ?",
                (self.namespace, key),
            ).fetchone()
        if row is None:
            return None
        entry = DurableEntry(
            namespace=self.namespace,
            key=key,
            value=codecs.get_codec(row[1]).decode(row[0]),
            version=int(row[2]),
            expires_at=None if row[3] is None else float(row[3]),
            updated_at=float(row[4]),
        )
        if entry.expired(now):
            return None
        with self._lock:
            self.read_hits += 1
        return entry

    def get(self, key: str, default: Any = None) -> Any:
        entry = self.get_entry(key)
        return default if entry is None else entry.value

    def get_many(self, keys: Iterable[str]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key in keys:
            entry = self.get_entry(key)
            if entry is not None:
                out[key] = entry.value
        return out

    def version_of(self, key: str) -> int:
        """Latest version for key, counting tombstones; 0 if never written."""
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(v) FROM (SELECT version AS v FROM pack_h_cache_entries WHERE namespace = ? AND key = ? "
                "UNION ALL SELECT version FROM pack_h_cache_tombstones WHERE namespace = ? AND key = ?)",
                (self.namespace, key, self.namespace, key),
            ).fetchone()
        return int(row[0] or 0)

    # -- writes ------------------------------------------------------------
    def _next_version(self, key: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(v) FROM (SELECT version AS v FROM pack_h_cache_entries WHERE namespace = ? AND key = ? "
            "UNION ALL SELECT version FROM pack_h_cache_tombstones WHERE namespace = ? AND key = ?)",
            (self.namespace, key, self.namespace, key),
        ).fetchone()
        return int(row[0] or 0) + 1

    def put(
        self,
        key: str,
        value: Any,
        *,
        ttl_s: Optional[float] = None,
        expected_version: Optional[int] = None,
    ) -> int:
        """Write a value; returns its new version.

        ``expected_version`` makes the write conditional (compare-and-set);
        pass 0 to require that the key has never been written.
        """
        _check_ident(key, "key")
        if value is None:
            raise DurableTierError("None is not storable; use delete()")
        codec_name, blob = codecs.auto_encode(value)
        now = self._clock()
        expires = _ttl(ttl_s, now)
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                version = self._next_version(key)
                if expected_version is not None and version - 1 != int(expected_version):
                    raise StaleWrite(f"expected version {expected_version}, found {version - 1}")
                self._conn.execute(
                    "INSERT INTO pack_h_cache_entries (namespace, key, value, codec, version, expires_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(namespace, key) DO UPDATE SET "
                    "value = excluded.value, codec = excluded.codec, version = excluded.version, "
                    "expires_at = excluded.expires_at, updated_at = excluded.updated_at",
                    (self.namespace, key, blob, codec_name, version, expires, now),
                )
                self._conn.execute(
                    "DELETE FROM pack_h_cache_tombstones WHERE namespace = ? AND key = ?",
                    (self.namespace, key),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            self.writes += 1
        return version

    def put_many(self, items: Iterable[Tuple[str, Any, Optional[float]]]) -> int:
        """Write a batch atomically. Items are ``(key, value, ttl_s)``; a value of
        ``_MISSING``-like ``None`` means delete. Returns rows touched."""
        batch = list(items)
        if not batch:
            return 0
        now = self._clock()
        prepared = []
        for key, value, ttl_s in batch:
            _check_ident(key, "key")
            if value is None:
                prepared.append((key, None, None, None))
            else:
                codec_name, blob = codecs.auto_encode(value)
                prepared.append((key, codec_name, blob, _ttl(ttl_s, now)))
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                for key, codec_name, blob, expires in prepared:
                    version = self._next_version(key)
                    if codec_name is None:
                        self._tombstone_unlocked(key, version, now)
                    else:
                        self._conn.execute(
                            "INSERT INTO pack_h_cache_entries (namespace, key, value, codec, version, expires_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(namespace, key) DO UPDATE SET "
                            "value = excluded.value, codec = excluded.codec, version = excluded.version, "
                            "expires_at = excluded.expires_at, updated_at = excluded.updated_at",
                            (self.namespace, key, blob, codec_name, version, expires, now),
                        )
                        self._conn.execute(
                            "DELETE FROM pack_h_cache_tombstones WHERE namespace = ? AND key = ?",
                            (self.namespace, key),
                        )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            self.writes += len(prepared)
        return len(prepared)

    def _tombstone_unlocked(self, key: str, version: int, now: float) -> None:
        self._conn.execute(
            "DELETE FROM pack_h_cache_entries WHERE namespace = ? AND key = ?", (self.namespace, key)
        )
        self._conn.execute(
            "INSERT INTO pack_h_cache_tombstones (namespace, key, version, deleted_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(namespace, key) DO UPDATE SET version = excluded.version, deleted_at = excluded.deleted_at",
            (self.namespace, key, version, now),
        )

    def delete(self, key: str) -> bool:
        _check_ident(key, "key")
        now = self._clock()
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                existed = self._conn.execute(
                    "SELECT 1 FROM pack_h_cache_entries WHERE namespace = ? AND key = ?",
                    (self.namespace, key),
                ).fetchone() is not None
                self._tombstone_unlocked(key, self._next_version(key), now)
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
        return existed

    # -- maintenance -------------------------------------------------------
    def purge_expired(self, *, tombstone_ttl_s: float = 86_400.0) -> int:
        now = self._clock()
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM pack_h_cache_entries WHERE namespace = ? AND expires_at IS NOT NULL AND expires_at <= ?",
                (self.namespace, now),
            )
            removed = cur.rowcount or 0
            cur = self._conn.execute(
                "DELETE FROM pack_h_cache_tombstones WHERE namespace = ? AND deleted_at <= ?",
                (self.namespace, now - tombstone_ttl_s),
            )
            removed += cur.rowcount or 0
        return removed

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM pack_h_cache_entries WHERE namespace = ?", (self.namespace,)
            ).fetchone()
        return int(row[0])

    def keys(self, prefix: str = "", *, limit: int = 1000) -> List[str]:
        if limit < 1 or limit > 100_000:
            raise DurableTierError("limit must be within [1, 100000]")
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._lock:
            rows = self._conn.execute(
                "SELECT key FROM pack_h_cache_entries WHERE namespace = ? AND key LIKE ? ESCAPE '\\' "
                "ORDER BY key LIMIT ?",
                (self.namespace, escaped + "%", limit),
            ).fetchall()
        return [r[0] for r in rows]

    def stats(self) -> Dict[str, Any]:
        return {
            "namespace": self.namespace,
            "entries": self.count(),
            "reads": self.reads,
            "read_hits": self.read_hits,
            "writes": self.writes,
        }

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.ProgrammingError:
                pass


@dataclass(slots=True)
class _Pending:
    value: Any  # None = delete
    ttl_s: Optional[float]
    enqueued_at: float


class WriteBehindQueue:
    """Coalescing write-behind buffer in front of a ``DurableTier``."""

    def __init__(
        self,
        tier: DurableTier,
        *,
        max_pending: int = 1024,
        batch_size: int = 256,
        flush_interval_s: float = 0.5,
        max_attempts: int = 5,
        backoff_s: float = 0.05,
        on_failure: Optional[Callable[[List[Tuple[str, Any, Optional[float]]], BaseException], None]] = None,
        autostart: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_pending < 1 or batch_size < 1:
            raise ValueError("max_pending and batch_size must be positive")
        if not math.isfinite(flush_interval_s) or flush_interval_s <= 0:
            raise ValueError("flush_interval_s must be finite and positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.tier = tier
        self.max_pending = max_pending
        self.batch_size = batch_size
        self.flush_interval_s = flush_interval_s
        self.max_attempts = max_attempts
        self.backoff_s = backoff_s
        self.on_failure = on_failure
        self._clock = clock
        self._pending: Dict[str, _Pending] = {}
        self._cond = threading.Condition()
        self._flush_lock = threading.Lock()
        self._closed = False
        self._thread: Optional[threading.Thread] = None
        self.enqueued = 0
        self.coalesced = 0
        self.flushed = 0
        self.flushes = 0
        self.failures = 0
        self.dropped = 0
        if autostart:
            self.start()

    def start(self) -> None:
        with self._cond:
            if self._thread is not None or self._closed:
                return
            self._thread = threading.Thread(target=self._run, name="pack-h-write-behind", daemon=True)
            self._thread.start()

    def _run(self) -> None:
        while True:
            with self._cond:
                if self._closed:
                    return
                self._cond.wait(timeout=self.flush_interval_s)
                if self._closed:
                    return
            try:
                self.flush()
            except Exception:  # flush() already accounts failures
                pass

    def put(self, key: str, value: Any, ttl_s: Optional[float] = None) -> None:
        self._enqueue(key, value, ttl_s)

    def delete(self, key: str) -> None:
        self._enqueue(key, None, None)

    def _enqueue(self, key: str, value: Any, ttl_s: Optional[float]) -> None:
        _check_ident(key, "key")
        must_flush = False
        with self._cond:
            if self._closed:
                raise DurableTierError("write-behind queue is closed")
            if key in self._pending:
                self.coalesced += 1
            self._pending[key] = _Pending(value, ttl_s, self._clock())
            self.enqueued += 1
            if len(self._pending) >= self.max_pending:
                must_flush = True
            elif len(self._pending) >= self.batch_size:
                self._cond.notify()
        if must_flush:
            # Backpressure: the writer pays for the flush instead of growing memory.
            self.flush()

    def pending(self, key: str) -> Any:
        """Pending value for key: ``_MISSING`` if none, ``None`` if a delete."""
        with self._cond:
            p = self._pending.get(key)
        return _MISSING if p is None else p.value

    def has_pending(self, key: str) -> bool:
        return self.pending(key) is not _MISSING

    def depth(self) -> int:
        with self._cond:
            return len(self._pending)

    def flush(self) -> int:
        """Flush everything pending; returns the number of keys written."""
        written = 0
        with self._flush_lock:
            while True:
                with self._cond:
                    if not self._pending:
                        break
                    keys = list(self._pending)[: self.batch_size]
                    batch = {k: self._pending[k] for k in keys}
                items = [(k, p.value, p.ttl_s) for k, p in batch.items()]
                error: Optional[BaseException] = None
                for attempt in range(self.max_attempts):
                    try:
                        self.tier.put_many(items)
                        error = None
                        break
                    except Exception as exc:  # pragma: no branch - retried below
                        error = exc
                        self.failures += 1
                        if attempt + 1 < self.max_attempts:
                            time.sleep(self.backoff_s * (2 ** attempt))
                with self._cond:
                    for k, p in batch.items():
                        # Only remove if not overwritten during the flush.
                        if self._pending.get(k) is p:
                            del self._pending[k]
                if error is not None:
                    self.dropped += len(items)
                    if self.on_failure is not None:
                        self.on_failure(items, error)
                    continue
                written += len(items)
                self.flushed += len(items)
                self.flushes += 1
        return written

    def close(self, *, flush: bool = True) -> None:
        with self._cond:
            if self._closed:
                return
            self._closed = True
            self._cond.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=5.0)
        if flush:
            self.flush()

    def stats(self) -> Dict[str, Any]:
        return {
            "pending": self.depth(),
            "enqueued": self.enqueued,
            "coalesced": self.coalesced,
            "flushed": self.flushed,
            "flushes": self.flushes,
            "failures": self.failures,
            "dropped": self.dropped,
        }

    def __enter__(self) -> "WriteBehindQueue":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
