"""Tamper-evident journal of AI shell decisions, never hidden reasoning."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import threading
import time
from types import MappingProxyType
from typing import Callable, Mapping


@dataclass(frozen=True)
class AIDecisionEvent:
    sequence: int
    previous_hash: str
    event_hash: str
    kind: str
    observed_at: float
    session_id: str
    intent_id: str
    proposal_id: str
    summary: str
    data: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "previous_hash": self.previous_hash,
            "event_hash": self.event_hash,
            "kind": self.kind,
            "observed_at": self.observed_at,
            "session_id": self.session_id,
            "intent_id": self.intent_id,
            "proposal_id": self.proposal_id,
            "summary": self.summary,
            "data": dict(self.data),
        }


class AIDecisionJournal:
    GENESIS = "0" * 64

    def __init__(
        self,
        *,
        max_events: int = 10000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        self.max_events = max_events
        self._clock = clock
        self._items: list[AIDecisionEvent] = []
        self._lock = threading.RLock()

    @staticmethod
    def _hash(
        previous: str,
        sequence: int,
        kind: str,
        observed_at: float,
        session_id: str,
        intent_id: str,
        proposal_id: str,
        summary: str,
        data: Mapping[str, object],
    ) -> str:
        payload = {
            "previous_hash": previous,
            "sequence": sequence,
            "kind": kind,
            "observed_at": observed_at,
            "session_id": session_id,
            "intent_id": intent_id,
            "proposal_id": proposal_id,
            "summary": summary,
            "data": dict(data),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(raw).hexdigest()

    def append(
        self,
        kind: str,
        *,
        session_id: str,
        intent_id: str,
        proposal_id: str = "",
        summary: str = "",
        data: Mapping[str, object] | None = None,
    ) -> AIDecisionEvent:
        if not kind or len(kind) > 128:
            raise ValueError("invalid AI decision event kind")
        if len(summary) > 2048:
            raise ValueError("AI decision summary too long")
        payload = dict(data or {})
        if len(payload) > 128:
            raise ValueError("too many AI decision data fields")
        with self._lock:
            if len(self._items) >= self.max_events:
                raise RuntimeError("AI decision journal capacity exhausted")
            sequence = len(self._items) + 1
            previous = self._items[-1].event_hash if self._items else self.GENESIS
            observed_at = self._clock()
            event_hash = self._hash(
                previous,
                sequence,
                kind,
                observed_at,
                session_id,
                intent_id,
                proposal_id,
                summary,
                payload,
            )
            event = AIDecisionEvent(
                sequence,
                previous,
                event_hash,
                kind,
                observed_at,
                session_id,
                intent_id,
                proposal_id,
                summary,
                MappingProxyType(payload),
            )
            self._items.append(event)
            return event

    def verify(self) -> bool:
        with self._lock:
            previous = self.GENESIS
            for sequence, event in enumerate(self._items, start=1):
                if event.sequence != sequence or event.previous_hash != previous:
                    return False
                expected = self._hash(
                    previous,
                    sequence,
                    event.kind,
                    event.observed_at,
                    event.session_id,
                    event.intent_id,
                    event.proposal_id,
                    event.summary,
                    event.data,
                )
                if expected != event.event_hash:
                    return False
                previous = event.event_hash
            return True

    def snapshot(self) -> tuple[AIDecisionEvent, ...]:
        with self._lock:
            return tuple(self._items)

    def root_hash(self) -> str:
        with self._lock:
            return self._items[-1].event_hash if self._items else self.GENESIS
