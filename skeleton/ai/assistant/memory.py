"""Governed memory decisions for the assistant control plane.

The policy distinguishes retrieval from persistence. A model may suggest memory,
but durable writes are admitted by deterministic rules and explicit user intent.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import AssistantRequest, IntentSignals, digest_json


class MemoryAction(str, Enum):
    RETRIEVE = "retrieve"
    SAVE = "save"
    FORGET = "forget"
    IGNORE = "ignore"


class MemorySensitivity(str, Enum):
    ORDINARY = "ordinary"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    content: str
    source_ref: str
    sensitivity: MemorySensitivity = MemorySensitivity.ORDINARY
    useful_beyond_session: bool = False
    explicit_user_request: bool = False
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("memory content must be non-empty")
        if len(self.content) > 32_768:
            raise ValueError("memory content exceeds hard bound")
        if not isinstance(self.source_ref, str) or not self.source_ref.strip():
            raise ValueError("memory source_ref must be non-empty")
        if not isinstance(self.sensitivity, MemorySensitivity):
            object.__setattr__(
                self, "sensitivity", MemorySensitivity(str(self.sensitivity))
            )
        if isinstance(self.confidence, bool) or not isinstance(
            self.confidence, (int, float)
        ):
            raise ValueError("memory confidence must be numeric")
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("memory confidence must be in [0, 1]")
        object.__setattr__(self, "content", self.content.strip())
        object.__setattr__(self, "source_ref", self.source_ref.strip())
        object.__setattr__(self, "confidence", confidence)

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "content": self.content,
                "source_ref": self.source_ref,
                "sensitivity": self.sensitivity.value,
            }
        )


@dataclass(frozen=True, slots=True)
class MemoryDecision:
    action: MemoryAction
    reason_code: str
    candidate_digest: str | None = None
    requires_confirmation: bool = False


class MemoryPolicy:
    """Small deterministic policy for retrieval, persistence and forgetting."""

    def decide_retrieval(
        self,
        request: AssistantRequest,
        signals: IntentSignals,
    ) -> MemoryDecision:
        if signals.references_personal_history:
            return MemoryDecision(
                action=MemoryAction.RETRIEVE,
                reason_code="request-references-prior-personal-context",
            )
        if request.metadata.get("personalization_required") is True:
            return MemoryDecision(
                action=MemoryAction.RETRIEVE,
                reason_code="request-declares-personalization-dependency",
            )
        return MemoryDecision(
            action=MemoryAction.IGNORE,
            reason_code="current-request-is-self-contained",
        )

    def decide_persistence(self, candidate: MemoryCandidate) -> MemoryDecision:
        if candidate.explicit_user_request:
            return MemoryDecision(
                action=MemoryAction.SAVE,
                reason_code="explicit-user-save-request",
                candidate_digest=candidate.digest,
            )
        if candidate.sensitivity is MemorySensitivity.SENSITIVE:
            return MemoryDecision(
                action=MemoryAction.IGNORE,
                reason_code="sensitive-memory-requires-explicit-request",
                candidate_digest=candidate.digest,
            )
        if not candidate.useful_beyond_session:
            return MemoryDecision(
                action=MemoryAction.IGNORE,
                reason_code="session-local-information",
                candidate_digest=candidate.digest,
            )
        if candidate.confidence < 0.75:
            return MemoryDecision(
                action=MemoryAction.IGNORE,
                reason_code="insufficient-persistence-confidence",
                candidate_digest=candidate.digest,
            )
        return MemoryDecision(
            action=MemoryAction.SAVE,
            reason_code="durable-nonsensitive-user-context",
            candidate_digest=candidate.digest,
            requires_confirmation=True,
        )

    def decide_forget(
        self,
        *,
        target_ref: str,
        explicit_user_request: bool,
    ) -> MemoryDecision:
        if not isinstance(target_ref, str) or not target_ref.strip():
            raise ValueError("target_ref must be non-empty")
        if not explicit_user_request:
            return MemoryDecision(
                action=MemoryAction.IGNORE,
                reason_code="forget-requires-explicit-user-request",
            )
        return MemoryDecision(
            action=MemoryAction.FORGET,
            reason_code="explicit-user-forget-request",
            candidate_digest=digest_json({"target_ref": target_ref.strip()}),
        )


__all__ = [
    "MemoryAction",
    "MemoryCandidate",
    "MemoryDecision",
    "MemoryPolicy",
    "MemorySensitivity",
]
