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
from typing import Callable, Iterable, Mapping

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.durable_hot_floor import (
    DurableHotFloorStore,
    HotFloorPosition,
)
from skeleton.shells.ai.journal import AIDecisionEvent, AIDecisionJournal
from skeleton.shells.ai.store_protocol import VersionedStateBackend
from skeleton.shells.sequence_index import SequenceIndexBackfillBatch


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


@dataclass(frozen=True)
class DistributedJournalSequenceIndex:
    sequence: int
    event_hash: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence <= 0
        ):
            raise ValueError("journal sequence index must be positive")
        object.__setattr__(
            self,
            "event_hash",
            _sha256_hex("event_hash", self.event_hash),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "event_hash": self.event_hash,
        }


@dataclass(frozen=True)
class DistributedJournalIndexHealth:
    head_sequence: int
    inspected: int
    indexed: int
    missing: int
    corrupt: int
    first_missing_sequence: int | None = None
    first_corrupt_sequence: int | None = None

    def __post_init__(self) -> None:
        for name in (
            "head_sequence",
            "inspected",
            "indexed",
            "missing",
            "corrupt",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(f"{name} must be non-negative integer")
        for name in (
            "first_missing_sequence",
            "first_corrupt_sequence",
        ):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(f"{name} must be positive when present")

    @property
    def healthy(self) -> bool:
        return self.missing == 0 and self.corrupt == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "head_sequence": self.head_sequence,
            "inspected": self.inspected,
            "indexed": self.indexed,
            "missing": self.missing,
            "corrupt": self.corrupt,
            "first_missing_sequence": self.first_missing_sequence,
            "first_corrupt_sequence": self.first_corrupt_sequence,
            "healthy": self.healthy,
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
        hot_floor_store: DurableHotFloorStore | None = None,
        hot_floor_chain_id: str = "",
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
        if (hot_floor_store is None) != (not hot_floor_chain_id):
            raise ValueError(
                "hot_floor_store and hot_floor_chain_id must be configured together"
            )
        if hot_floor_store is not None and not isinstance(
            hot_floor_store,
            DurableHotFloorStore,
        ):
            raise TypeError(
                "hot_floor_store must be DurableHotFloorStore"
            )
        if hot_floor_chain_id and len(hot_floor_chain_id) > 128:
            raise ValueError("hot_floor_chain_id too long")
        self.hot_floor_store = hot_floor_store
        self.hot_floor_chain_id = hot_floor_chain_id

    def hot_floor(self) -> HotFloorPosition:
        if self.hot_floor_store is None:
            return HotFloorPosition.genesis()
        return self.hot_floor_store.position(
            self.hot_floor_chain_id
        )

    def _hot_floor_active(
        self,
        floor: HotFloorPosition | None = None,
    ) -> bool:
        floor = floor or self.hot_floor()
        if floor.sequence == 0:
            return False
        return self.backend.get(
            self.namespace,
            self._event_key(floor.root_hash),
        ) is None

    def hot_length(self) -> int:
        head = self.head()
        floor = self.hot_floor()
        if self._hot_floor_active(floor):
            return max(0, head.sequence - floor.sequence)
        return head.sequence

    @staticmethod
    def _event_key(event_hash: str) -> str:
        return "event:" + _sha256_hex("event_hash", event_hash)

    @staticmethod
    def _sequence_key(sequence: int) -> str:
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
        ):
            raise ValueError("sequence must be positive integer")
        return f"sequence:{sequence:020d}"

    def _sequence_index(
        self,
        sequence: int,
    ) -> DistributedJournalSequenceIndex | None:
        record = self.backend.get(
            self.namespace,
            self._sequence_key(sequence),
        )
        if record is None:
            return None
        if not isinstance(
            record.value,
            DistributedJournalSequenceIndex,
        ):
            raise DistributedJournalCorruption(
                "journal sequence index has invalid value type"
            )
        if record.value.sequence != sequence:
            raise DistributedJournalCorruption(
                "journal sequence index key/value mismatch"
            )
        return record.value

    def _put_sequence_index(
        self,
        event: AIDecisionEvent,
    ) -> DistributedJournalSequenceIndex:
        entry = DistributedJournalSequenceIndex(
            event.sequence,
            event.event_hash,
        )
        key = self._sequence_key(event.sequence)
        existing = self.backend.get(
            self.namespace,
            key,
        )
        if existing is None:
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    key,
                    entry,
                )
                return entry
            except DistributedStateConflict:
                existing = self.backend.get(
                    self.namespace,
                    key,
                )
                if existing is None:
                    raise
        if not isinstance(
            existing.value,
            DistributedJournalSequenceIndex,
        ):
            raise DistributedJournalCorruption(
                "journal sequence index has invalid value type"
            )
        if existing.value != entry:
            raise DistributedJournalCorruption(
                "journal sequence already indexes a different event"
            )
        return existing.value

    def _repair_sequence_index(
        self,
        sequence: int,
    ) -> DistributedJournalSequenceIndex:
        head = self.head()
        if sequence > head.sequence:
            raise IndexError(
                "journal sequence is beyond committed head"
            )
        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and sequence <= floor.sequence
        ):
            raise DistributedJournalConflict(
                "journal sequence was compacted from hot storage"
            )
        current_hash = head.root_hash
        current_sequence = head.sequence
        while current_sequence > sequence:
            event = self.get_event(current_hash)
            if event.sequence != current_sequence:
                raise DistributedJournalCorruption(
                    "journal sequence repair encountered non-contiguous chain"
                )
            current_hash = event.previous_hash
            current_sequence -= 1
        event = self.get_event(current_hash)
        if event.sequence != sequence:
            raise DistributedJournalCorruption(
                "journal sequence repair reached wrong sequence"
            )
        return self._put_sequence_index(event)

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
            floor = self.hot_floor()
            live_events = max(
                0,
                head.sequence - (
                    floor.sequence
                    if self._hot_floor_active(floor)
                    else 0
                ),
            )
            if live_events >= self.max_events:
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
                self._put_sequence_index(event)
                return event
            except DistributedStateConflict:
                current_revision, current = self._head_revision()
                if (
                    current.sequence == sequence
                    and current.root_hash == event_hash
                    and current_revision >= revision
                ):
                    self._put_sequence_index(event)
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

    def get_by_sequence(
        self,
        sequence: int,
        *,
        repair_missing: bool = True,
    ) -> AIDecisionEvent:
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence <= 0
        ):
            raise ValueError("sequence must be positive integer")
        head = self.head()
        if sequence > head.sequence:
            raise IndexError(
                "journal sequence is beyond committed head"
            )
        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and sequence <= floor.sequence
        ):
            raise DistributedJournalConflict(
                "journal sequence was compacted from hot storage"
            )
        entry = self._sequence_index(sequence)
        if entry is None:
            if not repair_missing:
                raise DistributedJournalConflict(
                    "journal sequence index is missing"
                )
            entry = self._repair_sequence_index(sequence)
        event = self.get_event(entry.event_hash)
        if event.sequence != sequence:
            raise DistributedJournalCorruption(
                "journal sequence index resolves wrong event sequence"
            )
        return event

    def root_for_sequence(
        self,
        sequence: int,
        *,
        repair_missing: bool = True,
    ) -> str:
        if sequence == 0:
            return GENESIS_HASH
        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and sequence == floor.sequence
        ):
            return floor.root_hash
        if (
            self._hot_floor_active(floor)
            and sequence < floor.sequence
        ):
            raise DistributedJournalConflict(
                "journal root sequence was compacted from hot storage"
            )
        return self.get_by_sequence(
            sequence,
            repair_missing=repair_missing,
        ).event_hash

    def snapshot_range(
        self,
        start_sequence: int,
        end_sequence: int,
        *,
        max_items: int = 4096,
        repair_missing: bool = True,
    ) -> tuple[AIDecisionEvent, ...]:
        if (
            isinstance(start_sequence, bool)
            or not isinstance(start_sequence, int)
            or start_sequence <= 0
        ):
            raise ValueError(
                "start_sequence must be positive integer"
            )
        if (
            isinstance(end_sequence, bool)
            or not isinstance(end_sequence, int)
            or end_sequence < start_sequence
        ):
            raise ValueError(
                "end_sequence must be >= start_sequence"
            )
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError("max_items must be positive integer")
        count = end_sequence - start_sequence + 1
        if count > max_items:
            raise DistributedJournalConflict(
                "journal range exceeds bounded verification window"
            )
        head = self.head()
        if end_sequence > head.sequence:
            raise IndexError(
                "journal range extends beyond committed head"
            )
        start_root = self.root_for_sequence(
            start_sequence - 1,
            repair_missing=repair_missing,
        )
        end_root = self.root_for_sequence(
            end_sequence,
            repair_missing=repair_missing,
        )
        return self.snapshot_segment(
            start_root,
            end_root,
            max_items=max_items,
        )

    def backfill_sequence_indexes_batch(
        self,
        *,
        end_sequence: int | None = None,
        end_root: str = "",
        max_items: int = 1024,
    ) -> SequenceIndexBackfillBatch:
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError("max_items must be positive integer")
        head = self.head()
        if end_sequence is None:
            end_sequence = head.sequence
            end_root = head.root_hash
        if (
            isinstance(end_sequence, bool)
            or not isinstance(end_sequence, int)
            or end_sequence < 0
            or end_sequence > head.sequence
        ):
            raise ValueError(
                "end_sequence outside committed journal range"
            )
        if end_sequence == 0:
            if end_root and end_root != GENESIS_HASH:
                raise DistributedJournalConflict(
                    "zero-sequence backfill root must be genesis"
                )
            return SequenceIndexBackfillBatch(
                0,
                GENESIS_HASH,
                None,
                None,
                0,
                0,
                0,
                GENESIS_HASH,
                True,
            )
        if not end_root:
            if end_sequence != head.sequence:
                raise ValueError(
                    "historical journal backfill requires explicit end_root"
                )
            end_root = head.root_hash
        end_root = _sha256_hex(
            "end_root",
            end_root,
        )
        terminal = self.get_event(end_root)
        if terminal.sequence != end_sequence:
            raise DistributedJournalCorruption(
                "journal backfill root/sequence mismatch"
            )

        requested_end_sequence = end_sequence
        requested_end_root = end_root
        current_sequence = end_sequence
        current_root = end_root
        indexed = 0
        already_indexed = 0
        processed = 0

        while current_sequence > 0 and processed < max_items:
            event = self.get_event(current_root)
            if event.sequence != current_sequence:
                raise DistributedJournalCorruption(
                    "journal backfill encountered non-contiguous sequence"
                )
            entry = self._sequence_index(
                current_sequence
            )
            if entry is None:
                self._put_sequence_index(event)
                indexed += 1
            elif entry.event_hash != event.event_hash:
                raise DistributedJournalCorruption(
                    "journal backfill found conflicting sequence index"
                )
            else:
                already_indexed += 1
            current_root = event.previous_hash
            current_sequence -= 1
            processed += 1

        covered_start = current_sequence + 1
        return SequenceIndexBackfillBatch(
            requested_end_sequence,
            requested_end_root,
            covered_start,
            requested_end_sequence,
            indexed,
            already_indexed,
            current_sequence,
            current_root,
            current_sequence == 0,
        )

    def inspect_sequence_indexes(
        self,
        *,
        max_items: int = 100_000,
    ) -> DistributedJournalIndexHealth:
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError("max_items must be positive integer")
        events = self.snapshot()
        if len(events) > max_items:
            raise DistributedJournalConflict(
                "journal index inspection exceeds bounded window"
            )
        indexed = 0
        missing = 0
        corrupt = 0
        first_missing = None
        first_corrupt = None
        for event in events:
            try:
                entry = self._sequence_index(event.sequence)
            except DistributedJournalCorruption:
                corrupt += 1
                if first_corrupt is None:
                    first_corrupt = event.sequence
                continue
            if entry is None:
                missing += 1
                if first_missing is None:
                    first_missing = event.sequence
                continue
            if entry.event_hash != event.event_hash:
                corrupt += 1
                if first_corrupt is None:
                    first_corrupt = event.sequence
                continue
            indexed += 1
        return DistributedJournalIndexHealth(
            self.head().sequence,
            len(events),
            indexed,
            missing,
            corrupt,
            first_missing,
            first_corrupt,
        )

    def repair_sequence_indexes(
        self,
        *,
        max_items: int = 100_000,
    ) -> DistributedJournalIndexHealth:
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError("max_items must be positive integer")
        events = self.snapshot()
        if len(events) > max_items:
            raise DistributedJournalConflict(
                "journal index repair exceeds bounded window"
            )
        for event in events:
            self._put_sequence_index(event)
        return self.inspect_sequence_indexes(
            max_items=max_items,
        )

    def snapshot(self) -> tuple[AIDecisionEvent, ...]:
        head = self.head()
        if head.sequence == 0:
            return ()
        floor = self.hot_floor()
        floor_active = self._hot_floor_active(floor)
        current_hash = head.root_hash
        expected_sequence = head.sequence
        reverse: list[AIDecisionEvent] = []
        seen: set[str] = set()
        while current_hash != GENESIS_HASH:
            if (
                floor_active
                and current_hash == floor.root_hash
            ):
                break
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
        expected_base = (
            floor.sequence
            if floor_active
            else 0
        )
        if expected_sequence != expected_base:
            raise DistributedJournalCorruption(
                "decision journal terminated before trusted hot floor"
            )
        events = tuple(reversed(reverse))
        if len(events) != (
            head.sequence - expected_base
        ):
            raise DistributedJournalCorruption(
                "decision journal snapshot length differs from live suffix"
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
        floor = self.hot_floor()
        floor_active = self._hot_floor_active(floor)
        if floor_active and root_hash == floor.root_hash:
            return ()
        if floor_active:
            try:
                target_sequence = self.sequence_for_root(
                    root_hash
                )
            except (
                DistributedJournalConflict,
                DistributedJournalCorruption,
            ) as exc:
                raise DistributedJournalCorruption(
                    "historical journal root is below compacted hot floor"
                ) from exc
            if target_sequence < floor.sequence:
                raise DistributedJournalCorruption(
                    "historical journal root is below compacted hot floor"
                )
        root_event = self.get_event(root_hash)
        expected_sequence = root_event.sequence
        current_hash = root_hash
        reverse: list[AIDecisionEvent] = []
        seen: set[str] = set()
        while current_hash != GENESIS_HASH:
            if (
                floor_active
                and current_hash == floor.root_hash
            ):
                break
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
        expected_base = (
            floor.sequence
            if floor_active
            else 0
        )
        if expected_sequence != expected_base:
            raise DistributedJournalCorruption(
                "historical decision journal did not reach trusted hot floor"
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
        floor = self.hot_floor()
        floor_active = self._hot_floor_active(floor)
        if floor_active and root_hash == floor.root_hash:
            return True
        previous = (
            floor.root_hash
            if floor_active
            else GENESIS_HASH
        )
        start_sequence = (
            floor.sequence + 1
            if floor_active
            else 1
        )
        for sequence, event in enumerate(
            events,
            start=start_sequence,
        ):
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
        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and root_hash == floor.root_hash
        ):
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

    def sequence_for_root(
        self,
        root_hash: str,
    ) -> int:
        root_hash = _sha256_hex(
            "root_hash",
            root_hash,
        )
        if root_hash == GENESIS_HASH:
            return 0
        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and root_hash == floor.root_hash
        ):
            return floor.sequence
        return self.get_event(root_hash).sequence

    def snapshot_segment(
        self,
        start_exclusive_root: str,
        end_inclusive_root: str = "",
        *,
        max_items: int = 4096,
    ) -> tuple[AIDecisionEvent, ...]:
        """Verify and return only the chain segment after a trusted root."""
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError("max_items must be positive integer")
        start_exclusive_root = _sha256_hex(
            "start_exclusive_root",
            start_exclusive_root,
        )
        head = self.head()
        end_inclusive_root = _sha256_hex(
            "end_inclusive_root",
            end_inclusive_root or head.root_hash,
        )
        start_sequence = self.sequence_for_root(
            start_exclusive_root
        )
        end_sequence = self.sequence_for_root(
            end_inclusive_root
        )
        if end_sequence < start_sequence:
            raise DistributedJournalCorruption(
                "segment end precedes trusted start"
            )
        distance = end_sequence - start_sequence
        if distance > max_items:
            raise DistributedJournalConflict(
                "decision journal segment exceeds bounded verification window"
            )
        if distance == 0:
            if end_inclusive_root != start_exclusive_root:
                raise DistributedJournalCorruption(
                    "equal segment sequence has different roots"
                )
            return ()

        current_hash = end_inclusive_root
        expected_sequence = end_sequence
        reverse: list[AIDecisionEvent] = []
        seen: set[str] = set()
        while current_hash != start_exclusive_root:
            if len(reverse) >= max_items:
                raise DistributedJournalConflict(
                    "decision journal segment exceeds bounded verification window"
                )
            if current_hash == GENESIS_HASH:
                raise DistributedJournalCorruption(
                    "trusted segment start is not an ancestor"
                )
            if current_hash in seen:
                raise DistributedJournalCorruption(
                    "decision journal segment contains a cycle"
                )
            seen.add(current_hash)
            event = self.get_event(current_hash)
            if event.sequence != expected_sequence:
                raise DistributedJournalCorruption(
                    "decision journal segment sequence is not contiguous"
                )
            reverse.append(event)
            current_hash = event.previous_hash
            expected_sequence -= 1

        if expected_sequence != start_sequence:
            raise DistributedJournalCorruption(
                "decision journal segment did not reach expected start sequence"
            )
        events = tuple(reversed(reverse))
        previous = start_exclusive_root
        sequence = start_sequence + 1
        for event in events:
            if (
                event.sequence != sequence
                or event.previous_hash != previous
            ):
                raise DistributedJournalCorruption(
                    "decision journal segment linkage mismatch"
                )
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
                raise DistributedJournalCorruption(
                    "decision journal segment digest mismatch"
                )
            previous = event.event_hash
            sequence += 1
        if previous != end_inclusive_root:
            raise DistributedJournalCorruption(
                "decision journal segment end root mismatch"
            )
        return events

    def restore_segment(
        self,
        events: Iterable[AIDecisionEvent],
        *,
        max_items: int = 4096,
    ) -> DistributedJournalHead:
        """Restore an exact committed segment onto this chain.

        The target may be empty, behind the segment, or already contain an
        identical prefix. Same-sequence different-root state is treated as
        divergence and is never overwritten.
        """
        if (
            isinstance(max_items, bool)
            or not isinstance(max_items, int)
            or max_items <= 0
        ):
            raise ValueError("max_items must be positive integer")
        values = tuple(events)
        if len(values) > max_items:
            raise DistributedJournalConflict(
                "journal restore exceeds bounded segment size"
            )
        if not values:
            return self.head()

        previous_hash = values[0].previous_hash
        previous_sequence = values[0].sequence - 1
        if previous_sequence < 0:
            raise DistributedJournalCorruption(
                "journal restore begins before sequence one"
            )
        for offset, event in enumerate(values):
            if not isinstance(event, AIDecisionEvent):
                raise TypeError(
                    "journal restore items must be AIDecisionEvent"
                )
            expected_sequence = previous_sequence + offset + 1
            if event.sequence != expected_sequence:
                raise DistributedJournalCorruption(
                    "journal restore sequence is not contiguous"
                )
            expected_previous = (
                previous_hash
                if offset == 0
                else values[offset - 1].event_hash
            )
            if event.previous_hash != expected_previous:
                raise DistributedJournalCorruption(
                    "journal restore linkage mismatch"
                )
            expected_hash = AIDecisionJournal._hash(
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
            if expected_hash != event.event_hash:
                raise DistributedJournalCorruption(
                    "journal restore event digest mismatch"
                )
            if event.sequence > self.max_events:
                raise DistributedJournalConflict(
                    "journal restore exceeds chain capacity"
                )

        floor = self.hot_floor()
        if (
            self._hot_floor_active(floor)
            and values[0].sequence <= floor.sequence
        ):
            raise DistributedJournalConflict(
                "journal restore overlaps compacted hot floor"
            )

        for event in values:
            for _ in range(self.max_cas_retries):
                revision, head = self._head_revision()
                if head.sequence >= event.sequence:
                    try:
                        existing_root = self.root_for_sequence(
                            event.sequence,
                            repair_missing=True,
                        )
                    except (
                        DistributedJournalConflict,
                        DistributedJournalCorruption,
                        IndexError,
                    ) as exc:
                        raise DistributedJournalConflict(
                            "journal restore cannot verify existing target prefix"
                        ) from exc
                    if existing_root != event.event_hash:
                        raise DistributedJournalConflict(
                            "journal restore diverges from existing target prefix"
                        )
                    self._put_event(event)
                    self._put_sequence_index(event)
                    break

                if head.sequence != event.sequence - 1:
                    raise DistributedJournalConflict(
                        "journal restore target has a sequence gap"
                    )
                if head.root_hash != event.previous_hash:
                    raise DistributedJournalConflict(
                        "journal restore target root diverges from segment"
                    )

                self._put_event(event)
                next_head = DistributedJournalHead(
                    event.sequence,
                    event.event_hash,
                )
                try:
                    self.backend.compare_and_swap(
                        self.namespace,
                        "head",
                        expected_revision=revision,
                        value=next_head,
                    )
                except DistributedStateConflict:
                    continue
                self._put_sequence_index(event)
                break
            else:
                raise DistributedJournalConflict(
                    "journal restore CAS retry budget exhausted"
                )

        last = values[-1]
        current = self.head()
        if current.sequence < last.sequence:
            raise DistributedJournalCorruption(
                "journal restore ended before requested segment"
            )
        if self.root_for_sequence(last.sequence) != last.event_hash:
            raise DistributedJournalConflict(
                "journal restore final prefix differs from segment"
            )
        return current

    def verify_segment(
        self,
        start_exclusive_root: str,
        end_inclusive_root: str = "",
        *,
        max_items: int = 4096,
    ) -> bool:
        try:
            self.snapshot_segment(
                start_exclusive_root,
                end_inclusive_root,
                max_items=max_items,
            )
        except (
            DistributedJournalConflict,
            DistributedJournalCorruption,
            ValueError,
        ):
            return False
        return True

    def verify(self) -> bool:
        try:
            events = self.snapshot()
            head = self.head()
        except (
            DistributedJournalCorruption,
            ValueError,
        ):
            return False
        floor = self.hot_floor()
        floor_active = self._hot_floor_active(floor)
        previous = (
            floor.root_hash
            if floor_active
            else GENESIS_HASH
        )
        start_sequence = (
            floor.sequence + 1
            if floor_active
            else 1
        )
        for sequence, event in enumerate(
            events,
            start=start_sequence,
        ):
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
        expected_base = (
            floor.sequence
            if floor_active
            else 0
        )
        expected_root = (
            previous
            if events
            else (
                floor.root_hash
                if floor_active
                else GENESIS_HASH
            )
        )
        return (
            head.sequence
            == expected_base + len(events)
            and head.root_hash == expected_root
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
