"""Version-two recovery checkpoint with session-scoped evidence bindings."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.shells.ai.checkpoint import AISessionCheckpoint


@dataclass(frozen=True)
class AIRecoveryCheckpoint:
    schema_version: int
    session: AISessionCheckpoint
    session_evidence_digest: str = ""
    session_journal_digest: str = ""
    release_evidence_digest: str = ""
    sandbox_binding_digest: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("unsupported AI recovery checkpoint schema")
        for name in (
            "session_evidence_digest",
            "session_journal_digest",
            "release_evidence_digest",
            "sandbox_binding_digest",
        ):
            value = getattr(self, name)
            if value and len(value) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session": self.session.to_dict(),
            "session_evidence_digest": self.session_evidence_digest,
            "session_journal_digest": self.session_journal_digest,
            "release_evidence_digest": self.release_evidence_digest,
            "sandbox_binding_digest": self.sandbox_binding_digest,
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
    def wrap(
        cls,
        session: AISessionCheckpoint,
        *,
        session_evidence_digest: str = "",
        session_journal_digest: str = "",
        release_evidence_digest: str = "",
        sandbox_binding_digest: str = "",
    ) -> "AIRecoveryCheckpoint":
        return cls(
            2,
            session,
            session_evidence_digest,
            session_journal_digest,
            release_evidence_digest,
            sandbox_binding_digest,
        )
