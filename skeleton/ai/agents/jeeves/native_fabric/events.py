"""Bounded, hash-linked host events for offline Jeeves operational decisions.

An event chain detects a missing or altered record in its retained window.
It is NOT a signed log. Privileged mutation of every record and root cannot
be authenticated without separate cryptographic KMS custody and attestation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import threading
import time
from typing import Callable, Mapping, Sequence

from .contracts import (
    ContractHold, canonical_bytes, digest, exact_integer, fingerprint,
    identifier, text, finite,
)


@dataclass(frozen=True, slots=True)
class Event:
    sequence: int
    scope_sha256: str
    kind: str
    payload_sha256: str
    previous_sha256: str
    event_sha256: str
    occurred_ns: int
    facts: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self):
        exact_integer(self.sequence, minimum=1)
        exact_integer(self.occurred_ns, maximum=10**30)
        digest(self.scope_sha256)
        identifier(self.kind, "event kind")
        digest(self.payload_sha256)
        digest(self.previous_sha256)
        digest(self.event_sha256)
        if type(self.facts) is not dict:
            raise ContractHold("event facts require strict mapping")
        canonical_bytes(self.facts, max_bytes=16384)

    def derive(self) -> str:
        return fingerprint({
            "schema": "jeeves.fabric.event.v1",
            "sequence": self.sequence,
            "scope": self.scope_sha256,
            "kind": self.kind,
            "payload": self.payload_sha256,
            "previous": self.previous_sha256,
            "occurred_ns": self.occurred_ns,
            "facts": self.facts,
        })

    def to_public_record(self) -> dict[str, object]:
        return {
            "schema": "jeeves.fabric.event.v1",
            "sequence": self.sequence,
            "scope_sha256": self.scope_sha256,
            "kind": self.kind,
            "payload_sha256": self.payload_sha256,
            "previous_sha256": self.previous_sha256,
            "event_sha256": self.event_sha256,
            "occurred_ns": self.occurred_ns,
            "facts": dict(self.facts),
            "cryptographically_signed": False,
        }


class EventJournal:
    """Ordered events with explicit contiguous retention boundaries."""

    def __init__(
        self, *, maximum_events: int = 4096,
        clock_ns: Callable[[], int] = time.time_ns,
    ):
        exact_integer(maximum_events, minimum=1, maximum=100000)
        if not callable(clock_ns):
            raise ContractHold("event clock required")
        self.maximum_events = maximum_events
        self.clock_ns = clock_ns
        self._lock = threading.RLock()
        self._records: list[Event] = []
        self._anchor_seq = 0
        self._anchor_hash = "0" * 64

    @property
    def anchor(self) -> tuple[int, str]:
        with self._lock:
            return self._anchor_seq, self._anchor_hash

    @property
    def tip(self) -> tuple[int, str]:
        with self._lock:
            if not self._records:
                return self._anchor_seq, self._anchor_hash
            last = self._records[-1]
            return last.sequence, last.event_sha256

    def append(
        self, scope_sha256: str, kind: str, *,
        payload: object, facts: Mapping[str, object] | None = None,
    ) -> Event:
        digest(scope_sha256)
        identifier(kind, "kind")
        fact_values = dict(facts or {})
        canonical_bytes(fact_values, max_bytes=16384)
        payload_hash = fingerprint(payload)
        with self._lock:
            last_seq, last_hash = self.tip
            now_ns = self.clock_ns()
            exact_integer(now_ns, maximum=10**30)
            unsigned = Event(
                sequence=last_seq + 1,
                scope_sha256=scope_sha256, kind=kind,
                payload_sha256=payload_hash,
                previous_sha256=last_hash,
                event_sha256="0" * 64,
                occurred_ns=now_ns, facts=fact_values,
            )
            event = Event(
                sequence=unsigned.sequence,
                scope_sha256=scope_sha256, kind=kind,
                payload_sha256=payload_hash,
                previous_sha256=last_hash,
                event_sha256=unsigned.derive(),
                occurred_ns=now_ns, facts=fact_values,
            )
            self._records.append(event)
            if len(self._records) > self.maximum_events:
                removed = self._records.pop(0)
                self._anchor_seq = removed.sequence
                self._anchor_hash = removed.event_sha256
            return event

    def history(self, *, after_sequence: int = 0, limit: int = 4096) -> tuple[Event, ...]:
        exact_integer(after_sequence)
        exact_integer(limit, minimum=1, maximum=100000)
        with self._lock:
            if after_sequence < self._anchor_seq:
                raise ContractHold("event cursor predates retained chain anchor")
            return tuple(
                item for item in self._records
                if item.sequence > after_sequence
            )[:limit]

    def verify(self) -> None:
        with self._lock:
            validate_journal(
                tuple(self._records), self._anchor_seq, self._anchor_hash,
            )

    def export(self) -> dict[str, object]:
        with self._lock:
            self.verify()
            return {
                "schema": "jeeves.fabric.event_journal.v1",
                "anchor_sequence": self._anchor_seq,
                "anchor_sha256": self._anchor_hash,
                "tip_sequence": self.tip[0],
                "tip_sha256": self.tip[1],
                "events": [e.to_public_record() for e in self._records],
                "cryptographically_signed": False,
                "release_certified": False,
            }


def validate_journal(
    events: Sequence[Event], anchor_sequence: int,
    anchor_sha256: str,
) -> None:
    exact_integer(anchor_sequence)
    digest(anchor_sha256)
    if type(events) not in (list, tuple):
        raise ContractHold("bounded event collection required")
    if len(events) > 100000:
        raise ContractHold("event chain exceeds validation bound")
    previous = anchor_sha256
    seq = anchor_sequence
    for event in events:
        if not isinstance(event, Event):
            raise ContractHold("unexpected event type")
        seq += 1
        if (event.sequence != seq or event.previous_sha256 != previous
            or event.derive() != event.event_sha256):
            raise ContractHold("event journal continuity or integrity broken")
        previous = event.event_sha256


__all__ = ["Event", "EventJournal", "validate_journal"]
