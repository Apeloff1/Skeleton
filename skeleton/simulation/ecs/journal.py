"""Append-only deterministic mutation and event journals.

Journals are evidence planes, not alternate authoritative state.  They retain
bounded, digest-chained facts about mutations and events so replay, debugging,
and audit tooling can prove exactly what happened without relying on logs.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .canonical import chained_digest, digest
from .errors import BoundsError, ValidationError

MAX_JOURNAL_ENTRIES = 100_000
GENESIS_DIGEST = "0" * 64


class JournalKind(str, Enum):
    MUTATION = "mutation"
    EVENT = "event"
    CHECKPOINT = "checkpoint"
    NOTE = "note"


@dataclass(frozen=True)
class JournalEntry:
    sequence: int
    kind: JournalKind
    tick: int
    source: str
    operation: str
    subject: str
    payload: Any
    payload_digest: str
    previous_digest: str
    entry_digest: str

    def to_record(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "kind": self.kind.value,
            "tick": self.tick,
            "source": self.source,
            "operation": self.operation,
            "subject": self.subject,
            "payload": copy.deepcopy(self.payload),
            "payload_digest": self.payload_digest,
            "previous_digest": self.previous_digest,
            "entry_digest": self.entry_digest,
        }


@dataclass(frozen=True)
class JournalSlice:
    start_sequence: int
    end_sequence: int
    entries: tuple[JournalEntry, ...]
    first_previous_digest: str
    final_digest: str

    @property
    def count(self) -> int:
        return len(self.entries)


@dataclass(frozen=True)
class JournalVerification:
    entries: int
    final_digest: str
    valid: bool
    first_invalid_sequence: int | None = None
    reason: str | None = None


class MutationJournal:
    """Bounded digest-chained journal.

    A journal may be snapshotted/restored, sliced for evidence transport, and
    verified independently.  Appends deep-copy payloads before hashing so later
    caller mutation cannot rewrite historical evidence.
    """

    def __init__(self, *, capacity: int = MAX_JOURNAL_ENTRIES) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int):
            raise ValidationError("journal capacity must be integer")
        if not 1 <= capacity <= MAX_JOURNAL_ENTRIES:
            raise ValidationError(
                "journal capacity out of range",
                context={"capacity": capacity, "maximum": MAX_JOURNAL_ENTRIES},
            )
        self.capacity = capacity
        self._entries: list[JournalEntry] = []
        self._next_sequence = 0
        self._head_digest = GENESIS_DIGEST

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def head_digest(self) -> str:
        return self._head_digest

    @property
    def next_sequence(self) -> int:
        return self._next_sequence

    def entries(self) -> tuple[JournalEntry, ...]:
        return tuple(self._entries)

    def append(
        self,
        kind: JournalKind | str,
        operation: str,
        subject: str,
        payload: Any,
        *,
        tick: int,
        source: str = "",
    ) -> JournalEntry:
        if len(self._entries) >= self.capacity:
            raise BoundsError(
                "journal capacity exhausted",
                context={"capacity": self.capacity},
            )
        if not isinstance(kind, JournalKind):
            try:
                kind = JournalKind(kind)
            except (TypeError, ValueError) as exc:
                raise ValidationError("unknown journal kind") from exc
        if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
            raise ValidationError("journal tick must be non-negative integer")
        if not isinstance(operation, str) or not operation:
            raise ValidationError("journal operation must be non-empty text")
        if not isinstance(subject, str):
            raise ValidationError("journal subject must be text")
        if not isinstance(source, str):
            raise ValidationError("journal source must be text")

        frozen_payload = copy.deepcopy(payload)
        payload_digest = digest(frozen_payload)
        material = {
            "domain": "skeleton.simulation.ecs.journal_entry.v1",
            "sequence": self._next_sequence,
            "kind": kind.value,
            "tick": tick,
            "source": source,
            "operation": operation,
            "subject": subject,
            "payload_digest": payload_digest,
        }
        entry_digest = chained_digest(self._head_digest, material)
        entry = JournalEntry(
            sequence=self._next_sequence,
            kind=kind,
            tick=tick,
            source=source,
            operation=operation,
            subject=subject,
            payload=frozen_payload,
            payload_digest=payload_digest,
            previous_digest=self._head_digest,
            entry_digest=entry_digest,
        )
        self._entries.append(entry)
        self._next_sequence += 1
        self._head_digest = entry_digest
        return entry

    def mutation(
        self,
        operation: str,
        subject: str,
        payload: Any,
        *,
        tick: int,
        source: str = "",
    ) -> JournalEntry:
        return self.append(
            JournalKind.MUTATION,
            operation,
            subject,
            payload,
            tick=tick,
            source=source,
        )

    def event(
        self,
        event_type: str,
        payload: Any,
        *,
        tick: int,
        source: str = "",
    ) -> JournalEntry:
        return self.append(
            JournalKind.EVENT,
            event_type,
            event_type,
            payload,
            tick=tick,
            source=source,
        )

    def checkpoint(
        self,
        label: str,
        state_digest: str,
        *,
        tick: int,
        source: str = "",
    ) -> JournalEntry:
        return self.append(
            JournalKind.CHECKPOINT,
            "checkpoint",
            label,
            {"state_digest": state_digest},
            tick=tick,
            source=source,
        )

    def find(
        self,
        *,
        kind: JournalKind | None = None,
        subject: str | None = None,
        operation: str | None = None,
        source: str | None = None,
        from_tick: int | None = None,
        through_tick: int | None = None,
    ) -> tuple[JournalEntry, ...]:
        rows: list[JournalEntry] = []
        for entry in self._entries:
            if kind is not None and entry.kind is not kind:
                continue
            if subject is not None and entry.subject != subject:
                continue
            if operation is not None and entry.operation != operation:
                continue
            if source is not None and entry.source != source:
                continue
            if from_tick is not None and entry.tick < from_tick:
                continue
            if through_tick is not None and entry.tick > through_tick:
                continue
            rows.append(entry)
        return tuple(rows)

    def slice(self, start: int = 0, stop: int | None = None) -> JournalSlice:
        if isinstance(start, bool) or not isinstance(start, int) or start < 0:
            raise ValidationError("journal slice start must be non-negative integer")
        if stop is None:
            stop = len(self._entries)
        if isinstance(stop, bool) or not isinstance(stop, int) or stop < start:
            raise ValidationError("journal slice stop is invalid")
        chosen = tuple(self._entries[start:stop])
        if chosen:
            first_previous = chosen[0].previous_digest
            final = chosen[-1].entry_digest
            end_sequence = chosen[-1].sequence
        else:
            first_previous = self._head_digest if start >= len(self._entries) else GENESIS_DIGEST
            final = first_previous
            end_sequence = start - 1
        return JournalSlice(
            start_sequence=start,
            end_sequence=end_sequence,
            entries=chosen,
            first_previous_digest=first_previous,
            final_digest=final,
        )

    def verify(self) -> JournalVerification:
        previous = GENESIS_DIGEST
        expected_sequence = 0
        for entry in self._entries:
            if entry.sequence != expected_sequence:
                return JournalVerification(
                    entries=len(self._entries),
                    final_digest=previous,
                    valid=False,
                    first_invalid_sequence=entry.sequence,
                    reason="sequence_gap",
                )
            if entry.previous_digest != previous:
                return JournalVerification(
                    entries=len(self._entries),
                    final_digest=previous,
                    valid=False,
                    first_invalid_sequence=entry.sequence,
                    reason="previous_digest_mismatch",
                )
            if digest(entry.payload) != entry.payload_digest:
                return JournalVerification(
                    entries=len(self._entries),
                    final_digest=previous,
                    valid=False,
                    first_invalid_sequence=entry.sequence,
                    reason="payload_digest_mismatch",
                )
            material = {
                "domain": "skeleton.simulation.ecs.journal_entry.v1",
                "sequence": entry.sequence,
                "kind": entry.kind.value,
                "tick": entry.tick,
                "source": entry.source,
                "operation": entry.operation,
                "subject": entry.subject,
                "payload_digest": entry.payload_digest,
            }
            expected_digest = chained_digest(previous, material)
            if expected_digest != entry.entry_digest:
                return JournalVerification(
                    entries=len(self._entries),
                    final_digest=previous,
                    valid=False,
                    first_invalid_sequence=entry.sequence,
                    reason="entry_digest_mismatch",
                )
            previous = entry.entry_digest
            expected_sequence += 1
        if previous != self._head_digest:
            return JournalVerification(
                entries=len(self._entries),
                final_digest=previous,
                valid=False,
                reason="head_digest_mismatch",
            )
        return JournalVerification(
            entries=len(self._entries),
            final_digest=previous,
            valid=True,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": "simulation.mutation_journal.v1",
            "capacity": self.capacity,
            "next_sequence": self._next_sequence,
            "head_digest": self._head_digest,
            "entries": [entry.to_record() for entry in self._entries],
        }

    @classmethod
    def restore(cls, record: Mapping[str, Any]) -> "MutationJournal":
        if not isinstance(record, Mapping):
            raise ValidationError("journal snapshot must be mapping")
        if record.get("schema") != "simulation.mutation_journal.v1":
            raise ValidationError("unsupported journal snapshot schema")
        journal = cls(capacity=int(record["capacity"]))
        entries = record.get("entries")
        if not isinstance(entries, list):
            raise ValidationError("journal snapshot entries must be list")
        for row in entries:
            if not isinstance(row, Mapping):
                raise ValidationError("journal entry record must be mapping")
            journal.append(
                JournalKind(row["kind"]),
                str(row["operation"]),
                str(row["subject"]),
                copy.deepcopy(row["payload"]),
                tick=int(row["tick"]),
                source=str(row["source"]),
            )
        if journal._next_sequence != int(record["next_sequence"]):
            raise ValidationError("journal next sequence mismatch")
        if journal._head_digest != record["head_digest"]:
            raise ValidationError("journal head digest mismatch")
        verification = journal.verify()
        if not verification.valid:
            raise ValidationError(
                "journal snapshot failed verification",
                context={"reason": verification.reason},
            )
        return journal
