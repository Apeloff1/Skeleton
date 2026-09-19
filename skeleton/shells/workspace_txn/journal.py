"""Tamper-evident transaction journal."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import threading
from types import MappingProxyType
from typing import Any, Mapping

from skeleton.shells.provenance import canonical_json

GENESIS = "0" * 64


@dataclass(frozen=True)
class JournalEvent:
    sequence: int
    previous_hash: str
    event_hash: str
    transaction_id: str
    kind: str
    created_at: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "payload",
            MappingProxyType(dict(self.payload)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
            "transaction_id": self.transaction_id,
            "kind": self.kind,
            "created_at": self.created_at,
            "payload": dict(self.payload),
        }


class TransactionJournal:
    def __init__(self, *, max_events: int = 1_000_000) -> None:
        if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events <= 0:
            raise ValueError("max_events must be positive")
        self.max_events = max_events
        self._events: list[JournalEvent] = []
        self._lock = threading.RLock()

    @staticmethod
    def _hash(
        sequence: int,
        previous: str,
        transaction_id: str,
        kind: str,
        created_at: str,
        payload: Mapping[str, Any],
    ) -> str:
        return hashlib.sha256(
            canonical_json(
                {
                    "sequence": sequence,
                    "previous_hash": previous,
                    "transaction_id": transaction_id,
                    "kind": kind,
                    "created_at": created_at,
                    "payload": dict(payload),
                }
            )
        ).hexdigest()

    def append(
        self,
        transaction_id: str,
        kind: str,
        payload: Mapping[str, Any] | None = None,
    ) -> JournalEvent:
        if not transaction_id or not kind:
            raise ValueError("transaction_id and kind are required")
        body = dict(payload or {})
        with self._lock:
            if len(self._events) >= self.max_events:
                raise RuntimeError("transaction journal capacity exhausted")
            sequence = len(self._events) + 1
            previous = self._events[-1].event_hash if self._events else GENESIS
            created_at = datetime.now(timezone.utc).isoformat()
            digest = self._hash(
                sequence,
                previous,
                transaction_id,
                kind,
                created_at,
                body,
            )
            event = JournalEvent(
                sequence,
                previous,
                digest,
                transaction_id,
                kind,
                created_at,
                body,
            )
            self._events.append(event)
            return event

    def events(
        self,
        *,
        transaction_id: str | None = None,
        kind: str | None = None,
        after_sequence: int = 0,
    ) -> tuple[JournalEvent, ...]:
        with self._lock:
            values = tuple(event for event in self._events if event.sequence > after_sequence)
        if transaction_id is not None:
            values = tuple(event for event in values if event.transaction_id == transaction_id)
        if kind is not None:
            values = tuple(event for event in values if event.kind == kind)
        return values

    def verify(self) -> bool:
        with self._lock:
            previous = GENESIS
            for expected_sequence, event in enumerate(self._events, start=1):
                if event.sequence != expected_sequence or event.previous_hash != previous:
                    return False
                expected = self._hash(
                    event.sequence,
                    event.previous_hash,
                    event.transaction_id,
                    event.kind,
                    event.created_at,
                    event.payload,
                )
                if expected != event.event_hash:
                    return False
                previous = event.event_hash
            return True

    def root_hash(self) -> str:
        with self._lock:
            return self._events[-1].event_hash if self._events else GENESIS

    def transaction_state(self, transaction_id: str) -> str | None:
        events = self.events(transaction_id=transaction_id)
        return events[-1].kind if events else None

    def transaction_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted({event.transaction_id for event in self._events}))

    def length(self) -> int:
        with self._lock:
            return len(self._events)
