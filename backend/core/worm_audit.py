"""Durable cross-process write-once hash-chained audit ledger.

Every append acquires an OS-backed FileLease, re-verifies the complete on-disk
chain, derives the next sequence/predecessor from that verified head, appends and
fsyncs before returning. Separate workers therefore cannot fork audit ancestry or
allocate duplicate sequence numbers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import threading
from typing import Iterable

from core.file_lease import FileLease

GENESIS_HASH = "GENESIS"


class AuditIntegrityError(RuntimeError):
    """Raised when an existing audit ledger cannot be verified."""


@dataclass(frozen=True, slots=True)
class AuditEntry:
    seq: int
    ts: str
    kind: str
    seal: str
    principal: str
    route: str
    detail: str
    prev_hash: str
    hash: str = ""

    def payload(self) -> dict[str, object]:
        data = asdict(self); data.pop("hash"); return data


def compute_hash(entry: AuditEntry) -> str:
    payload = json.dumps(entry.payload(), ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _decode_entry(raw: str, line_number: int) -> AuditEntry:
    try: return AuditEntry(**json.loads(raw))
    except (TypeError, ValueError, json.JSONDecodeError) as exc: raise AuditIntegrityError(f"audit ledger unreadable at line {line_number}") from exc


def verify_entries(entries: Iterable[AuditEntry]) -> AuditEntry | None:
    previous = GENESIS_HASH; latest: AuditEntry | None = None; expected_seq = 1
    for entry in entries:
        if entry.seq != expected_seq: raise AuditIntegrityError(f"audit sequence broken at seq {entry.seq}; expected {expected_seq}")
        if entry.prev_hash != previous: raise AuditIntegrityError(f"audit predecessor broken at seq {entry.seq}")
        if entry.hash != compute_hash(entry): raise AuditIntegrityError(f"audit hash broken at seq {entry.seq}")
        latest = entry; previous = entry.hash; expected_seq += 1
    return latest


class WormAuditLog:
    """Append-only ledger with verified cross-process sequence/hash ancestry."""

    def __init__(self, directory: str | os.PathLike[str], filename: str = "worm.log") -> None:
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / filename
        self._process_lock = FileLease(self.directory / f".{filename}.lock")
        self._lock = threading.RLock()
        with self._lock, self._process_lock.acquire(): self._refresh_locked()

    def _read_entries(self) -> list[AuditEntry]:
        if not self.path.exists(): return []
        entries: list[AuditEntry] = []
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line_number, raw in enumerate(handle, start=1):
                    raw = raw.strip()
                    if raw: entries.append(_decode_entry(raw, line_number))
        except OSError as exc: raise AuditIntegrityError("audit ledger unreadable") from exc
        return entries

    def _refresh_locked(self) -> AuditEntry | None:
        entries = self._read_entries(); latest = verify_entries(entries)
        self._latest = latest; self._seq = latest.seq if latest else 0
        return latest

    @property
    def latest(self) -> AuditEntry | None:
        with self._lock, self._process_lock.acquire(): return self._refresh_locked()

    @property
    def sequence(self) -> int:
        with self._lock, self._process_lock.acquire(): self._refresh_locked(); return self._seq

    def append(self, *, kind: str, seal: str, principal: str, route: str, detail: str, ts: datetime | None = None) -> AuditEntry:
        if ts is not None and ts.tzinfo is None: raise ValueError("audit timestamp must be timezone-aware")
        with self._lock, self._process_lock.acquire():
            self._refresh_locked()
            seq = self._seq + 1; stamp = (ts or datetime.now(UTC)).astimezone(UTC).isoformat()
            draft = AuditEntry(seq=seq, ts=stamp, kind=str(kind), seal=str(seal), principal=str(principal), route=str(route),
                               detail=str(detail), prev_hash=self._latest.hash if self._latest else GENESIS_HASH)
            entry = replace(draft, hash=compute_hash(draft))
            line = json.dumps(asdict(entry), ensure_ascii=False, separators=(",", ":")) + "\n"
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line); handle.flush(); os.fsync(handle.fileno())
            self._latest = entry; self._seq = seq; return entry

    def entries(self, *, limit: int | None = None) -> tuple[AuditEntry, ...]:
        if limit is not None and limit < 0: raise ValueError("limit cannot be negative")
        with self._lock, self._process_lock.acquire():
            entries = self._read_entries(); latest = verify_entries(entries)
            self._latest = latest; self._seq = latest.seq if latest else 0
            if limit is not None: entries = entries[-limit:] if limit else []
            return tuple(entries)

    def verify(self) -> AuditEntry | None:
        with self._lock, self._process_lock.acquire(): return self._refresh_locked()

    def health(self) -> dict[str, object]:
        with self._lock, self._process_lock.acquire():
            latest = self._refresh_locked()
            return {"sequence": self._seq, "head": latest.hash if latest else None, "cross_process_locking": True,
                    "lock_backend": self._process_lock.backend, "verified": True}
