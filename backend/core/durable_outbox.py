"""Durable, bounded, cross-process coherent outbox for consequential effects.

Intent is journaled before exposure. Capacity exhaustion backpressures callers;
unconfirmed work is never silently evicted. Every state-changing decision occurs
under both an in-process RLock and an OS-backed file lease. A checksum-protected
sequence high-watermark prevents identifier reuse after an empty queue/restart.
The leased journal factory lets callers perform prerequisite staging only after
capacity is secured, closing cross-process preflight/staging races.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import hmac
import inspect
import json
import os
from pathlib import Path
import threading
from typing import Any, Awaitable, Callable, Iterator

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None
try:
    import msvcrt  # type: ignore
except ImportError:  # pragma: no cover
    msvcrt = None


class OutboxFullError(RuntimeError): pass
class OutboxIntegrityError(RuntimeError): pass


@dataclass(slots=True)
class OutboxEntry:
    seq: int
    collection: str
    payload: dict[str, Any]
    journaled_at: str
    confirmed: bool = False


Confirmer = Callable[[OutboxEntry], bool | Awaitable[bool]]
PayloadFactory = Callable[[int], dict[str, Any]]


class DurableOutbox:
    META_VERSION = 1

    def __init__(self, directory: str | os.PathLike[str], cap: int = 4096) -> None:
        if cap <= 0: raise ValueError("cap must be positive")
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "outbox.jsonl"; self.meta_path = self.directory / "outbox.meta.json"; self.lock_path = self.directory / ".outbox.lock"
        self.cap = cap; self._lock = threading.RLock()
        with self._guard(refresh=False):
            self._entries = self._restore(); inferred = max((e.seq for e in self._entries), default=0) + 1
            self._next_seq = max(inferred, self._load_next_seq(default=inferred)); self._persist_next_seq(self._next_seq)

    @staticmethod
    def _canonical(value: Any) -> bytes: return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    @classmethod
    def _digest(cls, value: Any) -> str: return hashlib.sha256(cls._canonical(value)).hexdigest()

    @contextmanager
    def _process_lease(self) -> Iterator[None]:
        with self.lock_path.open("a+b") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try: yield
                finally: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                return
            if msvcrt is not None:  # pragma: no cover
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0: handle.write(b"\0"); handle.flush()
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try: yield
                finally: handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                return
            raise RuntimeError("no supported OS file-locking primitive available")

    @contextmanager
    def _guard(self, *, refresh: bool = True) -> Iterator[None]:
        with self._lock:
            with self._process_lease():
                if refresh and hasattr(self, "_entries"):
                    self._entries = self._restore(); inferred = max((e.seq for e in self._entries), default=0) + 1
                    self._next_seq = max(inferred, self._load_next_seq(default=inferred))
                yield

    def _load_next_seq(self, *, default: int) -> int:
        if not self.meta_path.exists(): return default
        try:
            env = json.loads(self.meta_path.read_text(encoding="utf-8")); payload = env["payload"]; digest = env["sha256"]
            version = int(payload["version"]); next_seq = int(payload["next_seq"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc: raise OutboxIntegrityError("outbox sequence metadata is unreadable") from exc
        if version != self.META_VERSION or next_seq <= 0 or not isinstance(digest, str): raise OutboxIntegrityError("outbox sequence metadata is malformed")
        if not hmac.compare_digest(self._digest(payload), digest): raise OutboxIntegrityError("outbox sequence metadata checksum mismatch")
        return next_seq

    def _persist_next_seq(self, next_seq: int) -> None:
        payload = {"version": self.META_VERSION, "next_seq": next_seq}; env = {"payload": payload, "sha256": self._digest(payload)}
        temp = self.meta_path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with temp.open("x", encoding="utf-8") as handle:
                handle.write(self._canonical(env).decode("utf-8")); handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.meta_path)
        finally: temp.unlink(missing_ok=True)

    def _restore(self) -> list[OutboxEntry]:
        if not self.path.exists(): return []
        entries: list[OutboxEntry] = []; seen: set[int] = set()
        try: lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc: raise OutboxIntegrityError("outbox journal is unreadable") from exc
        for line_no, raw in enumerate(lines, start=1):
            if not raw.strip(): continue
            try: entry = OutboxEntry(**json.loads(raw))
            except (TypeError, ValueError, json.JSONDecodeError) as exc: raise OutboxIntegrityError(f"outbox unreadable at line {line_no}") from exc
            if entry.seq <= 0 or entry.seq in seen: raise OutboxIntegrityError(f"invalid outbox sequence at line {line_no}")
            if not entry.collection.strip() or not isinstance(entry.payload, dict): raise OutboxIntegrityError(f"invalid outbox record at line {line_no}")
            seen.add(entry.seq); entries.append(entry)
        entries.sort(key=lambda e: e.seq); return [e for e in entries if not e.confirmed]

    @property
    def pending_count(self) -> int:
        with self._guard(): return len(self._entries)
    @property
    def capacity_remaining(self) -> int:
        with self._guard(): return max(0, self.cap - len(self._entries))
    def has_capacity(self, count: int = 1) -> bool:
        if count < 0: raise ValueError("count cannot be negative")
        with self._guard(): return len(self._entries) + count <= self.cap
    def pending(self) -> tuple[OutboxEntry, ...]:
        with self._guard(): return tuple(self._entries)

    def journal_factory(self, collection: str, payload_factory: PayloadFactory) -> OutboxEntry:
        if not collection.strip(): raise ValueError("collection is required")
        with self._guard():
            if len(self._entries) >= self.cap: raise OutboxFullError("outbox full — durable persistence is backpressured, not dropped")
            seq = self._next_seq
            payload = payload_factory(seq)
            if not isinstance(payload, dict): raise ValueError("payload factory must return an object")
            json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            entry = OutboxEntry(seq=seq, collection=collection, payload=dict(payload), journaled_at=datetime.now(UTC).isoformat())
            self._append_record(entry); self._entries.append(entry); self._next_seq += 1; self._persist_next_seq(self._next_seq)
            return entry

    def journal(self, collection: str, payload: dict[str, Any]) -> OutboxEntry:
        if not isinstance(payload, dict): raise ValueError("payload must be an object")
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        return self.journal_factory(collection, lambda _seq: payload)

    def _append_record(self, entry: OutboxEntry) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), ensure_ascii=False, separators=(",", ":")) + "\n"); handle.flush(); os.fsync(handle.fileno())

    def _rewrite_pending(self) -> None:
        temp = self.path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            with temp.open("x", encoding="utf-8") as handle:
                for entry in self._entries: handle.write(json.dumps(asdict(entry), ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally: temp.unlink(missing_ok=True)

    async def confirm_one(self, seq: int, confirmer: Confirmer) -> bool:
        with self._guard(): entry = next((x for x in self._entries if x.seq == seq), None)
        if entry is None: return True
        result = confirmer(entry)
        if inspect.isawaitable(result): result = await result
        if not result: return False
        with self._guard():
            if not any(x.seq == seq for x in self._entries): return True
            self._entries = [x for x in self._entries if x.seq != seq]; self._rewrite_pending()
        return True

    async def reconcile(self, confirmer: Confirmer, limit: int | None = None) -> int:
        seqs = [e.seq for e in self.pending()]
        if limit is not None:
            if limit < 0: raise ValueError("limit cannot be negative")
            seqs = seqs[:limit]
        confirmed = 0
        for seq in seqs:
            if await self.confirm_one(seq, confirmer): confirmed += 1
        return confirmed

    def health(self) -> dict[str, Any]:
        with self._guard():
            return {"pending": len(self._entries), "capacity": self.cap, "capacity_remaining": max(0, self.cap - len(self._entries)),
                    "next_sequence": self._next_seq, "sequence_meta_version": self.META_VERSION, "cross_process_locking": True,
                    "leased_intent_factory": True, "lock_backend": "fcntl" if fcntl is not None else "msvcrt"}
