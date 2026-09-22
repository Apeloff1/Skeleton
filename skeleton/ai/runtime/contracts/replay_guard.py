"""Replay and duplicate admission guards for canonical automation envelopes."""

from __future__ import annotations

from dataclasses import dataclass, field

from .canonical import CanonicalEnvelope


class ReplayGuardError(ValueError):
    """Raised when an envelope cannot be safely replayed."""


@dataclass
class ReplayGuard:
    """Tracks accepted canonical digests for deterministic admission."""

    accepted: set[str] = field(default_factory=set)

    def check(self, envelope: CanonicalEnvelope) -> str:
        digest = envelope.digest
        if digest in self.accepted:
            raise ReplayGuardError("duplicate canonical envelope")
        return digest

    def accept(self, envelope: CanonicalEnvelope) -> str:
        digest = self.check(envelope)
        self.accepted.add(digest)
        return digest

    def contains(self, envelope: CanonicalEnvelope) -> bool:
        return envelope.digest in self.accepted
