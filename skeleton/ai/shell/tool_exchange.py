"""Typed AI tool-call and tool-result envelopes around structured actions."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.ai.observation import AIObservation
from skeleton.shells.ai.types import AIAction


@dataclass(frozen=True)
class AIToolCall:
    call_id: str
    session_id: str
    proposal_id: str
    action: AIAction
    ordinal: int

    def __post_init__(self) -> None:
        if not self.call_id or len(self.call_id) > 160:
            raise ValueError("invalid tool call id")
        if not self.session_id or len(self.session_id) > 160:
            raise ValueError("invalid tool session id")
        if not self.proposal_id or len(self.proposal_id) > 160:
            raise ValueError("invalid tool proposal id")
        if self.ordinal < 0:
            raise ValueError("tool ordinal may not be negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "call_id": self.call_id,
            "session_id": self.session_id,
            "proposal_id": self.proposal_id,
            "ordinal": self.ordinal,
            "action": self.action.to_dict(),
        }

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class AIToolResult:
    call_id: str
    observation: AIObservation | None
    status: str
    message: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.call_id or len(self.call_id) > 160:
            raise ValueError("invalid tool result call_id")
        if self.status not in {"completed", "blocked", "failed", "cancelled"}:
            raise ValueError("invalid tool result status")
        if len(self.message) > 2048:
            raise ValueError("tool result message too long")
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise ValueError("too many tool result metadata fields")
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def to_dict(self) -> dict[str, object]:
        return {
            "call_id": self.call_id,
            "status": self.status,
            "message": self.message,
            "observation": None if self.observation is None else self.observation.to_dict(),
            "metadata": dict(self.metadata),
        }
