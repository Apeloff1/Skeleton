"""Append-only provenance ledger for cognitive execution.

The ledger is deliberately dependency-free and deterministic: records are hash
chained so callers can detect mutation, truncation, or reordering.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from time import time
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    sequence: int
    kind: str
    payload: dict[str, Any]
    previous_hash: str
    digest: str
    timestamp: float


class ProvenanceLedger:
    """Hash-chained execution journal with export and verification."""

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        return tuple(self._entries)

    @property
    def head(self) -> str:
        return self._entries[-1].digest if self._entries else "0" * 64

    def append(self, kind: str, payload: dict[str, Any], *, timestamp: float | None = None) -> LedgerEntry:
        if not kind or not kind.strip():
            raise ValueError("kind must be non-empty")
        sequence = len(self._entries)
        previous = self.head
        body = {
            "sequence": sequence,
            "kind": kind,
            "payload": payload,
            "previous_hash": previous,
            "timestamp": time() if timestamp is None else timestamp,
        }
        digest = sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        entry = LedgerEntry(digest=digest, **body)
        self._entries.append(entry)
        return entry

    def verify(self) -> bool:
        previous = "0" * 64
        for expected_sequence, entry in enumerate(self._entries):
            if entry.sequence != expected_sequence or entry.previous_hash != previous:
                return False
            body = {
                "sequence": entry.sequence,
                "kind": entry.kind,
                "payload": entry.payload,
                "previous_hash": entry.previous_hash,
                "timestamp": entry.timestamp,
            }
            digest = sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
            if digest != entry.digest:
                return False
            previous = entry.digest
        return True

    def export(self) -> list[dict[str, Any]]:
        return [asdict(entry) for entry in self._entries]

    @classmethod
    def from_entries(cls, entries: Iterable[dict[str, Any]]) -> "ProvenanceLedger":
        ledger = cls()
        for raw in entries:
            entry = LedgerEntry(**raw)
            ledger._entries.append(entry)
        if not ledger.verify():
            raise ValueError("invalid provenance chain")
        return ledger
