"""Session-scoped commitments over a shared AI decision journal."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True)
class SessionJournalEvent:
    global_sequence: int
    event_hash: str
    kind: str
    proposal_id: str

    def __post_init__(self) -> None:
        if self.global_sequence <= 0:
            raise ValueError("global_sequence must be positive")
        if len(self.event_hash) != 64:
            raise ValueError("event_hash must be SHA-256 hex")
        if not self.kind or len(self.kind) > 128:
            raise ValueError("invalid session journal event kind")
        if len(self.proposal_id) > 160:
            raise ValueError("proposal_id too long")

    def to_dict(self) -> dict[str, object]:
        return {
            "global_sequence": self.global_sequence,
            "event_hash": self.event_hash,
            "kind": self.kind,
            "proposal_id": self.proposal_id,
        }


@dataclass(frozen=True)
class SessionJournalEvidence:
    session_id: str
    events: tuple[SessionJournalEvent, ...]

    def __post_init__(self) -> None:
        if not self.session_id or len(self.session_id) > 160:
            raise ValueError("invalid session journal evidence session_id")
        events = tuple(self.events)
        previous_sequence = 0
        for item in events:
            if item.global_sequence <= previous_sequence:
                raise ValueError("session journal events must preserve global order")
            previous_sequence = item.global_sequence
        object.__setattr__(self, "events", events)

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "events": [item.to_dict() for item in self.events],
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    @classmethod
    def from_journal(
        cls,
        journal,
        session_id: str,
    ) -> "SessionJournalEvidence":
        events = tuple(
            SessionJournalEvent(
                event.sequence,
                event.event_hash,
                event.kind,
                event.proposal_id,
            )
            for event in journal.snapshot()
            if event.session_id == session_id
        )
        return cls(session_id, events)
