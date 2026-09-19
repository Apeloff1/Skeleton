"""CAS-backed authoritative AI decision journal.

The in-memory :class:`AIDecisionJournal` is useful for one process.  This
module preserves exactly the same public read/write surface while moving the
committed head and immutable events into a versioned backend.

Only the head mutates.  Events are addressed by their event hash.  Concurrent
writers may leave unreachable immutable candidate events after losing a head
CAS, but those candidates are never part of the committed chain and therefore
cannot change the journal root seen by readers.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from types import MappingProxyType
import time
from typing import Callable, Mapping

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.journal import AIDecisionEvent, AIDecisionJournal
from skeleton.shells.ai.store_protocol import VersionedStateBackend


GENESIS_HASH = AIDecisionJournal.GENESIS


def _sha256_hex(name: str, value: str) -> str:
    if len(value) != 64:
        raise ValueError(f"{name} must be SHA-256 hex")
    # Digest values are opaque 64-character authority tokens; production

    # hashes are hexadecimal, while deterministic test/adapter sentinels may

    # use the full string alphabet.
    return value.lower()


@dataclass(frozen=True)
class DistributedJournalHead:
    sequence: int
    root_hash: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError("journal sequence must be non-negative integer")
        object.__setattr__(
            self,
            "root_hash",
            _sha256_hex("root_hash", self.root_hash),
        )
        if self.sequence == 0 and self.root_hash != GENESIS_HASH:
            raise ValueError("empty journal head must use genesis hash")
        if self.sequence > 0 and self.root_hash == GENESIS_HASH:
            raise ValueError("non-empty journal head may not use genesis hash")

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "root_hash": self.root_hash,
        }


class DistributedJournalConflict(RuntimeError):
    pass


class DistributedJournalCorruption(RuntimeError):
    pass


class DistributedAIDecisionJournal:
    """Durable multi-writer implementation of the AI decision journal API."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-decision-journal",
        max_events: int = 100_000,
        max_cas_retries: int = 32,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid decision journal namespace")
        if (
            isinstance(max_events, bool)
            or not isinstance(max_events, int)
            or max_events <= 0
        ):
            raise ValueError("max_events must be positive integer")
        if (
            isinstance(max_cas_retries, bool)
            or not isinstance(max_cas_retries, int)
            or not 1 <= max_cas_retries <= 128
        ):
            raise ValueError("max_cas_retries outside supported range")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.backend = backend
        self.namespace = namespace
        self.max_events = max_events
        self.max_cas_retries = max_cas_retries
        self._clock = clock

    @staticmethod
    def _event_key(event_hash: str) -> str:
        return "event:" + _sha256_hex("event_hash", event_hash)

    def _head_record(self):
        return self.backend.get(self.namespace, "head")

    def _head_revision(
        self,
    ) -> tuple[int, DistributedJournalHead]:
        record = self._head_record()
        if record is None:
            return 0, DistributedJournalHead(0, GENESIS_HASH)
        if not isinstance(record.value, DistributedJournalHead):
            raise DistributedJournalCorruption(
                "decision journal head has invalid value type"
            )
        return record.revision, record.value

    def head(self) -> DistributedJournalHead:
        return self._head_revision()[1]

    @staticmethod
    def _validate_append(
        kind: str,
        session_id: str,
        intent_id: str,
        proposal_id: str,
        summary: str,
        data: Mapping[str, object] | None,
    ) -> Mapping[str, object]:
        if not kind or len(kind) > 128:
            raise ValueError("invalid AI decision event kind")
        if not session_id or len(session_id) > 160:
            raise ValueError("invalid AI decision session_id")
        if not intent_id or len(intent_id) > 160:
            raise ValueError("invalid AI decision intent_id")
        if len(proposal_id) > 160:
            raise ValueError("AI decision proposal_id too long")
        if len(summary) > 2048:
            raise ValueError("AI decision summary too long")
        payload = dict(data or {})
        if len(payload) > 128:
            raise ValueError("too many AI decision data fields")
        return MappingProxyType(payload)

    def _put_event(self, event: AIDecisionEvent) -> None:
        key = self._event_key(event.event_hash)
        existing = self.backend.get(self.namespace, key)
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    event,
                )
                return
            except DistributedStateConflict:
                existing = self.backend.get(self.namespace, key)
                if existing is None:
                    raise
        if not isinstance(existing.value, AIDecisionEvent):
            raise DistributedJournalCorruption(
                "decision event key has invalid value type"
            )
        if existing.value != event:
            raise DistributedJournalCorruption(
                "content-addressed decision event collision"
            )

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
        payload = self._validate_append(
            kind,
            session_id,
            intent_id,
            proposal_id,
            summary,
            data,
        )
        observed_at = self._clock()
        if (
            isinstance(observed_at, bool)
            or not isinstance(observed_at, (int, float))
            or not math.isfinite(float(observed_at))
            or float(observed_at) < 0.0
        ):
            raise ValueError(
                "decision journal clock must return finite non-negative time"
            )
        observed_at = float(observed_at)

        for _ in range(self.max_cas_retries):
            revision, head = self._head_revision()
            if head.sequence >= self.max_events:
                raise RuntimeError(
                    "AI decision journal capacity exhausted"
                )
            sequence = head.sequence + 1
            event_hash = AIDecisionJournal._hash(
                head.root_hash,
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
                head.root_hash,
                event_hash,
                kind,
                observed_at,
                session_id,
                intent_id,
                proposal_id,
                summary,
                payload,
            )
            self._put_event(event)
            next_head = DistributedJournalHead(
                sequence,
                event_hash,
            )
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    "head",
                    expected_revision=revision,
                    value=next_head,
                )
                return event
            except DistributedStateConflict:
                current_revision, current = self._head_revision()
                if (
                    current.sequence == sequence
                    and current.root_hash == event_hash
                    and current_revision >= revision
                ):
                    return event
                if (
                    current_revision == revision
                    and current == head
                ):
                    raise
                continue
        raise DistributedJournalConflict(
            "decision journal head CAS retry budget exhausted"
        )

    def get_event(self, event_hash: str) -> AIDecisionEvent:
        event_hash = _sha256_hex("event_hash", event_hash)
        record = self.backend.get(
            self.namespace,
            self._event_key(event_hash),
        )
        if record is None:
            raise DistributedJournalCorruption(
                "committed decision event is missing"
            )
        if not isinstance(record.value, AIDecisionEvent):
            raise DistributedJournalCorruption(
                "decision event has invalid value type"
            )
        event = record.value
        expected = AIDecisionJournal._hash(
            event.previous_hash,
            event.sequence,
            event.kind,
            event.observed_at,
            event.session_id,
            event.intent_id,
            event.proposal_id,
            event.summary,
            event.data,
        )
        if expected != event.event_hash:
            raise DistributedJournalCorruption(
                "decision event digest mismatch"
            )
        if event.event_hash != event_hash:
            raise DistributedJournalCorruption(
                "decision event key/hash mismatch"
            )
        return event

    def snapshot(self) -> tuple[AIDecisionEvent, ...]:
        head = self.head()
        if head.sequence == 0:
            return ()
        current_hash = head.root_hash
        expected_sequence = head.sequence
        reverse: list[AIDecisionEvent] = []
        seen: set[str] = set()
        while current_hash != GENESIS_HASH:
            if current_hash in seen:
                raise DistributedJournalCorruption(
                    "decision journal contains a cycle"
                )
            seen.add(current_hash)
            event = self.get_event(current_hash)
            if event.sequence != expected_sequence:
                raise DistributedJournalCorruption(
                    "decision journal sequence is not contiguous"
                )
            reverse.append(event)
            current_hash = event.previous_hash
            expected_sequence -= 1
            if expected_sequence < 0:
                raise DistributedJournalCorruption(
                    "decision journal sequence underflow"
                )
        if expected_sequence != 0:
            raise DistributedJournalCorruption(
                "decision journal terminated before genesis"
            )
        events = tuple(reversed(reverse))
        if len(events) != head.sequence:
            raise DistributedJournalCorruption(
                "decision journal snapshot length differs from head"
            )
        return events

    def snapshot_at(
        self,
        root_hash: str,
    ) -> tuple[AIDecisionEvent, ...]:
        """Return and verify the committed prefix ending at root_hash."""
        root_hash = _sha256_hex(
            "root_hash",
            root_hash,
        )
        if root_hash == GENESIS_HASH:
            return ()
        root_event = self.get_event(root_hash)
        expected_sequence = root_event.sequence
        current_hash = root_hash
        reverse: list[AIDecisionEvent] = []
        seen: set[str] = set()
        while current_hash != GENESIS_HASH:
            if current_hash in seen:
                raise DistributedJournalCorruption(
                    "historical decision journal contains a cycle"
                )
            seen.add(current_hash)
            event = self.get_event(current_hash)
            if event.sequence != expected_sequence:
                raise DistributedJournalCorruption(
                    "historical decision journal sequence is not contiguous"
                )
            reverse.append(event)
            current_hash = event.previous_hash
            expected_sequence -= 1
            if expected_sequence < 0:
                raise DistributedJournalCorruption(
                    "historical decision journal sequence underflow"
                )
        if expected_sequence != 0:
            raise DistributedJournalCorruption(
                "historical decision journal terminated before genesis"
            )
        events = tuple(reversed(reverse))
        if not events or events[-1].event_hash != root_hash:
            raise DistributedJournalCorruption(
                "historical decision journal root mismatch"
            )
        return events

    def verify_root(
        self,
        root_hash: str,
    ) -> bool:
        try:
            events = self.snapshot_at(root_hash)
        except (
            DistributedJournalCorruption,
            ValueError,
        ):
            return False
        previous = GENESIS_HASH
        for sequence, event in enumerate(events, start=1):
            if (
                event.sequence != sequence
                or event.previous_hash != previous
            ):
                return False
            expected = AIDecisionJournal._hash(
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
        return previous == root_hash

    def root_is_ancestor(
        self,
        root_hash: str,
    ) -> bool:
        root_hash = _sha256_hex(
            "root_hash",
            root_hash,
        )
        if root_hash == GENESIS_HASH:
            return True
        if not self.verify_root(root_hash):
            return False
        try:
            current = self.snapshot()
        except DistributedJournalCorruption:
            return False
        return any(
            event.event_hash == root_hash
            for event in current
        )

    def verify(self) -> bool:
        try:
            events = self.snapshot()
            head = self.head()
        except (
            DistributedJournalCorruption,
            ValueError,
        ):
            return False
        previous = GENESIS_HASH
        for sequence, event in enumerate(events, start=1):
            if (
                event.sequence != sequence
                or event.previous_hash != previous
            ):
                return False
            expected = AIDecisionJournal._hash(
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
        return (
            head.sequence == len(events)
            and head.root_hash == (
                previous if events else GENESIS_HASH
            )
        )

    def root_hash(self) -> str:
        return self.head().root_hash

    def length(self) -> int:
        return self.head().sequence

    def events_for_session(
        self,
        session_id: str,
        *,
        root_hash: str = "",
    ) -> tuple[AIDecisionEvent, ...]:
        if not session_id or len(session_id) > 160:
            raise ValueError("invalid session_id")
        events = (
            self.snapshot()
            if not root_hash
            else self.snapshot_at(root_hash)
        )
        return tuple(
            event
            for event in events
            if event.session_id == session_id
        )

    def require_root(
        self,
        expected_root: str,
    ) -> DistributedJournalHead:
        expected_root = _sha256_hex(
            "expected_root",
            expected_root,
        )
        head = self.head()
        if head.root_hash != expected_root:
            raise DistributedJournalConflict(
                "decision journal root differs from expected root"
            )
        if not self.verify():
            raise DistributedJournalCorruption(
                "decision journal failed integrity verification"
            )
        return head
