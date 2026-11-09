"""Serializable checkpoint for AI shell sessions without secret material."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from skeleton.shells.ai.session import AISessionPhase, AIShellSession


@dataclass(frozen=True)
class AISessionCheckpoint:
    schema_version: int
    session_id: str
    phase: str
    intent_id: str
    intent_fingerprint: str
    proposal_id: str
    proposal_fingerprint: str
    transition_count: int
    journal_root: str
    receipt_root: str
    policy_fingerprint: str
    tool_catalog_digest: str
    effect_digest: str

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported AI session checkpoint schema")
        if not self.session_id or not self.intent_id:
            raise ValueError("checkpoint identity fields are required")
        for name in (
            "intent_fingerprint",
            "journal_root",
            "receipt_root",
            "policy_fingerprint",
            "tool_catalog_digest",
            "effect_digest",
        ):
            value = getattr(self, name)
            if len(value) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")
        if self.proposal_fingerprint and len(self.proposal_fingerprint) != 64:
            raise ValueError("proposal_fingerprint must be SHA-256 hex")
        AISessionPhase(self.phase)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "phase": self.phase,
            "intent_id": self.intent_id,
            "intent_fingerprint": self.intent_fingerprint,
            "proposal_id": self.proposal_id,
            "proposal_fingerprint": self.proposal_fingerprint,
            "transition_count": self.transition_count,
            "journal_root": self.journal_root,
            "receipt_root": self.receipt_root,
            "policy_fingerprint": self.policy_fingerprint,
            "tool_catalog_digest": self.tool_catalog_digest,
            "effect_digest": self.effect_digest,
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
    def capture(
        cls,
        session: AIShellSession,
        *,
        journal_root: str,
        receipt_root: str,
        policy_fingerprint: str,
        tool_catalog_digest: str,
        effect_digest: str,
    ) -> "AISessionCheckpoint":
        proposal = session.proposal
        return cls(
            1,
            session.session_id,
            session.phase.value,
            session.intent.intent_id,
            session.intent.fingerprint,
            "" if proposal is None else proposal.proposal_id,
            "" if proposal is None else proposal.fingerprint,
            len(session.history()),
            journal_root,
            receipt_root,
            policy_fingerprint,
            tool_catalog_digest,
            effect_digest,
        )
