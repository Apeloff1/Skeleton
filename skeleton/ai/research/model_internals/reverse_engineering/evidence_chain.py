"""Tamper-evident append-only evidence-chain primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ReverseEngineeringError, stable_digest


@dataclass(frozen=True)
class EvidenceChainEntry:
    sequence: int
    evidence_digest: str
    evidence_kind: str
    previous_entry_digest: str | None
    entry_digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "evidence_digest": self.evidence_digest,
            "evidence_kind": self.evidence_kind,
            "previous_entry_digest": self.previous_entry_digest,
            "entry_digest": self.entry_digest,
        }


@dataclass(frozen=True)
class EvidenceChain:
    entries: tuple[EvidenceChainEntry, ...] = ()

    @property
    def head_digest(self) -> str | None:
        return self.entries[-1].entry_digest if self.entries else None

    def append(self, *, evidence_digest: str, evidence_kind: str) -> "EvidenceChain":
        if len(evidence_digest) != 64:
            raise ReverseEngineeringError("evidence_digest must be sha256 length")
        if not evidence_kind.strip():
            raise ReverseEngineeringError("evidence_kind is required")
        sequence = len(self.entries)
        previous = self.head_digest
        entry_digest = stable_digest(
            {
                "sequence": sequence,
                "evidence_digest": evidence_digest,
                "evidence_kind": evidence_kind,
                "previous_entry_digest": previous,
            }
        )
        entry = EvidenceChainEntry(
            sequence=sequence,
            evidence_digest=evidence_digest,
            evidence_kind=evidence_kind,
            previous_entry_digest=previous,
            entry_digest=entry_digest,
        )
        return EvidenceChain(entries=self.entries + (entry,))

    def verify(self) -> bool:
        previous: str | None = None
        for expected_sequence, entry in enumerate(self.entries):
            if entry.sequence != expected_sequence or entry.previous_entry_digest != previous:
                return False
            expected = stable_digest(
                {
                    "sequence": entry.sequence,
                    "evidence_digest": entry.evidence_digest,
                    "evidence_kind": entry.evidence_kind,
                    "previous_entry_digest": entry.previous_entry_digest,
                }
            )
            if entry.entry_digest != expected:
                return False
            previous = entry.entry_digest
        return True
