"""Durable, bounded outbox for consequential side effects.

Mined from gameforge-rs gf-core and redesigned for the Python application spine.
Intent is journaled before exposure. Capacity exhaustion backpressures callers;
unconfirmed work is never silently evicted. Confirmation is storage-agnostic.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import inspect
import json
import os
from pathlib import Path
import threading
from typing import Any, Awaitable, Callable


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
        self.cap = cap
        self._lock = threading.RLock()
        self._entries = self._restore()
        self._next_seq = max((entry.seq for entry in self._entries), default=0) + 1

    def _restore(self) -> list[OutboxEntry]:
        if not self.path.exists():
            return []
        entries: list[OutboxEntry] = []
        seen: set[int] = set()
        for line_no, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), start=1):
            if not raw.strip():
                continue
            try:
                entry = OutboxEntry(**json.loads(raw))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise OutboxIntegrityError(f"outbox unreadable at line {line_no}") from exc
            if entry.seq <= 0 or entry.seq in seen:
                raise OutboxIntegrityError(f"invalid outbox sequence at line {line_no}")
            seen.add(entry.seq)
            entries.append(entry)
        entries.sort(key=lambda entry: entry.seq)
        return [entry for entry in entries if not entry.confirmed]

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def pending(self) -> tuple[OutboxEntry, ...]:
        with self._lock:
            return tuple(self._entries)

    def journal(self, collection: str, payload: dict[str, Any]) -> OutboxEntry:
        if not collection.strip():
            raise ValueError("collection is required")
        # Validate serializability before mutating sequence state.
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        with self._lock:
            if len(self._entries) >= self.cap:
                raise OutboxFullError("outbox full — durable persistence is backpressured, not dropped")
            entry = OutboxEntry(
                seq=self._next_seq,
                collection=collection,
                payload=payload,
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
        temp = self.path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            for entry in self._entries:
                handle.write(json.dumps(asdict(entry), ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.path)

    async def confirm_one(self, seq: int, confirmer: Confirmer) -> bool:
        with self._lock:
            entry = next((item for item in self._entries if item.seq == seq), None)
        if entry is None:
            return True
        result = confirmer(entry)
        if inspect.isawaitable(result):
            result = await result
        if not result:
            return False
        with self._lock:
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
