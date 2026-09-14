"""Durable write-once audit ledger mined from the Zaibatsu gate prototype.

The ledger is deliberately small and dependency-free so critical request paths can
record consequential decisions without importing the web stack. Entries form a
SHA-256 chain and are fsync'd before append returns. Existing ledgers are verified
on open; corruption fails closed instead of silently starting a new chain.
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
        data = asdict(self)
        data.pop("hash")
        return data


def compute_hash(entry: AuditEntry) -> str:
    payload = json.dumps(
        entry.payload(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _decode_entry(raw: str, line_number: int) -> AuditEntry:
    try:
        data = json.loads(raw)
        return AuditEntry(**data)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AuditIntegrityError(f"audit ledger unreadable at line {line_number}") from exc


def verify_entries(entries: Iterable[AuditEntry]) -> AuditEntry | None:
    previous = GENESIS_HASH
    latest: AuditEntry | None = None
    expected_seq = 1
    for entry in entries:
        if entry.seq != expected_seq:
            raise AuditIntegrityError(
                f"audit sequence broken at seq {entry.seq}; expected {expected_seq}"
            )
        if entry.prev_hash != previous:
            raise AuditIntegrityError(f"audit predecessor broken at seq {entry.seq}")
        if entry.hash != compute_hash(entry):
            raise AuditIntegrityError(f"audit hash broken at seq {entry.seq}")
        latest = entry
        previous = entry.hash
        expected_seq += 1
    return latest


class WormAuditLog:
    """Append-only, hash-chained ledger with startup verification and fsync."""

    def __init__(self, directory: str | os.PathLike[str], filename: str = "worm.log") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / filename
        self._lock = threading.RLock()
        self._latest = self._restore()
        self._seq = self._latest.seq if self._latest else 0

    @property
    def latest(self) -> AuditEntry | None:
        return self._latest

    @property
    def sequence(self) -> int:
        return self._seq

    def _read_entries(self) -> list[AuditEntry]:
        if not self.path.exists():
            return []
        entries: list[AuditEntry] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, raw in enumerate(handle, start=1):
                raw = raw.strip()
                if raw:
                    entries.append(_decode_entry(raw, line_number))
        return entries

    def _restore(self) -> AuditEntry | None:
        entries = self._read_entries()
        return verify_entries(entries)

    def append(
        self,
        *,
        kind: str,
        seal: str,
        principal: str,
        route: str,
        detail: str,
        ts: datetime | None = None,
    ) -> AuditEntry:
        if ts is not None and ts.tzinfo is None:
            raise ValueError("audit timestamp must be timezone-aware")
        with self._lock:
            seq = self._seq + 1
            stamp = (ts or datetime.now(UTC)).astimezone(UTC).isoformat()
            draft = AuditEntry(
                seq=seq,
                ts=stamp,
                kind=str(kind),
                seal=str(seal),
                principal=str(principal),
                route=str(route),
                detail=str(detail),
                prev_hash=self._latest.hash if self._latest else GENESIS_HASH,
            )
            entry = replace(draft, hash=compute_hash(draft))
            line = json.dumps(asdict(entry), ensure_ascii=False, separators=(",", ":")) + "\n"

            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())

            self._latest = entry
            self._seq = seq
            return entry

    def entries(self, *, limit: int | None = None) -> tuple[AuditEntry, ...]:
        """Return a verified history snapshot, optionally limited to the newest N."""
        if limit is not None and limit < 0:
            raise ValueError("limit cannot be negative")
        with self._lock:
            entries = self._read_entries()
            verify_entries(entries)
            if limit is not None:
                entries = entries[-limit:] if limit else []
            return tuple(entries)

    def verify(self) -> AuditEntry | None:
        """Re-read and verify the on-disk chain, returning its current head."""
        with self._lock:
            return self._restore()
