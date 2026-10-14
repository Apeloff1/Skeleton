"""Append-only evidence ledger with deterministic hash-chain verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ReverseEngineeringError, is_sha256_digest, stable_digest


@dataclass(frozen=True)
class EvidenceLedgerEntry:
    sequence: int
    event_kind: str
    subject_id: str
    evidence_digest: str
    previous_digest: str | None
    entry_digest: str


@dataclass(frozen=True)
class EvidenceLedger:
    entries: tuple[EvidenceLedgerEntry, ...] = ()

    def append(
        self,
        *,
        event_kind: str,
        subject_id: str,
        evidence_digest: str,
    ) -> "EvidenceLedger":
        if not event_kind or not subject_id:
            raise ReverseEngineeringError("ledger event identity is required")
        if not is_sha256_digest(evidence_digest):
            raise ReverseEngineeringError("evidence_digest must be sha256 hex")
        sequence = len(self.entries)
        previous = self.entries[-1].entry_digest if self.entries else None
        payload = {
            "sequence": sequence,
            "event_kind": event_kind,
            "subject_id": subject_id,
            "evidence_digest": evidence_digest,
            "previous_digest": previous,
        }
        entry = EvidenceLedgerEntry(
            sequence=sequence,
            event_kind=event_kind,
            subject_id=subject_id,
            evidence_digest=evidence_digest,
            previous_digest=previous,
            entry_digest=stable_digest(payload),
        )
        return EvidenceLedger(self.entries + (entry,))

    def verify(self) -> bool:
        previous: str | None = None
        for expected_sequence, entry in enumerate(self.entries):
            if entry.sequence != expected_sequence:
                return False
            if not is_sha256_digest(entry.evidence_digest):
                return False
            if entry.previous_digest != previous:
                return False
            payload = {
                "sequence": entry.sequence,
                "event_kind": entry.event_kind,
                "subject_id": entry.subject_id,
                "evidence_digest": entry.evidence_digest,
                "previous_digest": entry.previous_digest,
            }
            if stable_digest(payload) != entry.entry_digest:
                return False
            previous = entry.entry_digest
        return True

    @property
    def head_digest(self) -> str | None:
        return self.entries[-1].entry_digest if self.entries else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "entries": [
                {
                    "sequence": entry.sequence,
                    "event_kind": entry.event_kind,
                    "subject_id": entry.subject_id,
                    "evidence_digest": entry.evidence_digest,
                    "previous_digest": entry.previous_digest,
                    "entry_digest": entry.entry_digest,
                }
                for entry in self.entries
            ],
            "head_digest": self.head_digest,
        }
