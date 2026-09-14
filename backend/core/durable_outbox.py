"""Durable, bounded, cross-process coherent outbox for consequential effects.

Intent is journaled before exposure. Capacity exhaustion backpressures callers;
unconfirmed work is never silently evicted. Every state-changing decision occurs
under both an in-process RLock and an OS-backed file lease so separate workers
cannot race sequence allocation or confirmation rewrites.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import inspect
import json
import os
from pathlib import Path
import threading
from typing import Any, Awaitable, Callable, Iterator

try:  # POSIX
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows path
    fcntl = None
try:  # Windows
    import msvcrt  # type: ignore
except ImportError:  # pragma: no cover - POSIX path
    msvcrt = None


class OutboxFullError(RuntimeError):
    pass


class OutboxIntegrityError(RuntimeError):
    pass


@dataclass(slots=True)
class OutboxEntry:
    seq: int
    collection: str
    payload: dict[str, Any]
    journaled_at: str
    confirmed: bool = False


Confirmer = Callable[[OutboxEntry], bool | Awaitable[bool]]


class DurableOutbox:
    def __init__(self, directory: str | os.PathLike[str], cap: int = 4096) -> None:
        if cap <= 0:
            raise ValueError("cap must be positive")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "outbox.jsonl"
        self.lock_path = self.directory / ".outbox.lock"
        self.cap = cap
        self._lock = threading.RLock()
        with self._guard(refresh=False):
            self._entries = self._restore()
            self._next_seq = max((entry.seq for entry in self._entries), default=0) + 1

    @contextmanager
    def _process_lease(self) -> Iterator[None]:
        """Exclusive OS advisory lock shared by all processes using this directory."""
        with self.lock_path.open("a+b") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                return
            if msvcrt is not None:  # pragma: no cover - exercised on Windows
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                return
            raise RuntimeError("no supported OS file-locking primitive available")

    @contextmanager
    def _guard(self, *, refresh: bool = True) -> Iterator[None]:
        with self._lock:
            with self._process_lease():
                if refresh and hasattr(self, "_entries"):
                    self._entries = self._restore()
                    self._next_seq = max((entry.seq for entry in self._entries), default=0) + 1
                yield

    def _restore(self) -> list[OutboxEntry]:
        if not self.path.exists():
            return []
        entries: list[OutboxEntry] = []
        seen: set[int] = set()
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise OutboxIntegrityError("outbox journal is unreadable") from exc
        for line_no, raw in enumerate(lines, start=1):
            if not raw.strip():
                continue
            try:
                entry = OutboxEntry(**json.loads(raw))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise OutboxIntegrityError(f"outbox unreadable at line {line_no}") from exc
            if entry.seq <= 0 or entry.seq in seen:
                raise OutboxIntegrityError(f"invalid outbox sequence at line {line_no}")
            if not entry.collection.strip() or not isinstance(entry.payload, dict):
                raise OutboxIntegrityError(f"invalid outbox record at line {line_no}")
            seen.add(entry.seq)
            entries.append(entry)
        entries.sort(key=lambda entry: entry.seq)
        return [entry for entry in entries if not entry.confirmed]

    @property
    def pending_count(self) -> int:
        with self._guard():
            return len(self._entries)

    @property
    def capacity_remaining(self) -> int:
        with self._guard():
            return max(0, self.cap - len(self._entries))

    def has_capacity(self, count: int = 1) -> bool:
        if count < 0:
            raise ValueError("count cannot be negative")
        with self._guard():
            return len(self._entries) + count <= self.cap

    def pending(self) -> tuple[OutboxEntry, ...]:
        with self._guard():
            return tuple(self._entries)

    def journal(self, collection: str, payload: dict[str, Any]) -> OutboxEntry:
        if not collection.strip():
            raise ValueError("collection is required")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        with self._guard():
            if len(self._entries) >= self.cap:
                raise OutboxFullError("outbox full — durable persistence is backpressured, not dropped")
            entry = OutboxEntry(
                seq=self._next_seq,
                collection=collection,
                payload=dict(payload),
                journaled_at=datetime.now(UTC).isoformat(),
            )
            self._append_record(entry)
            self._entries.append(entry)
            self._next_seq += 1
            return entry

    def _append_record(self, entry: OutboxEntry) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _rewrite_pending(self) -> None:
        temp = self.path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with temp.open("x", encoding="utf-8") as handle:
                for entry in self._entries:
                    handle.write(json.dumps(asdict(entry), ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally:
            temp.unlink(missing_ok=True)

    async def confirm_one(self, seq: int, confirmer: Confirmer) -> bool:
        # Snapshot under lease; run external confirmer outside the lease so a slow
        # side effect never blocks other writers from journaling durable intent.
        with self._guard():
            entry = next((item for item in self._entries if item.seq == seq), None)
        if entry is None:
            return True
        result = confirmer(entry)
        if inspect.isawaitable(result):
            result = await result
        if not result:
            return False
        # Re-read under the process lease: another worker may have confirmed it.
        with self._guard():
            if not any(item.seq == seq for item in self._entries):
                return True
            self._entries = [item for item in self._entries if item.seq != seq]
            self._rewrite_pending()
        return True

    async def reconcile(self, confirmer: Confirmer, limit: int | None = None) -> int:
        seqs = [entry.seq for entry in self.pending()]
        if limit is not None:
            if limit < 0:
                raise ValueError("limit cannot be negative")
            seqs = seqs[:limit]
        confirmed = 0
        for seq in seqs:
            if await self.confirm_one(seq, confirmer):
                confirmed += 1
        return confirmed

    def health(self) -> dict[str, Any]:
        with self._guard():
            return {
                "pending": len(self._entries),
                "capacity": self.cap,
                "capacity_remaining": max(0, self.cap - len(self._entries)),
                "next_sequence": self._next_seq,
                "cross_process_locking": True,
                "lock_backend": "fcntl" if fcntl is not None else "msvcrt",
            }
