"""Deterministic policy for governed memory writeback."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.contracts.memory_record import (
    MAX_MEMORY_CONTENT_CHARS,
    MemoryKind,
    MemoryWriteProposal,
)


class MemoryWriteDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class MemoryWritePolicy:
    allowed_kinds: frozenset[MemoryKind] = frozenset(
        {
            MemoryKind.EPISODIC,
            MemoryKind.SEMANTIC,
            MemoryKind.PROCEDURAL,
            MemoryKind.PREFERENCE,
        }
    )
    require_provenance: bool = True
    require_source_operation: bool = True
    max_inline_chars: int = MAX_MEMORY_CONTENT_CHARS
    review_restricted_data: bool = True

    def __post_init__(self) -> None:
        if not self.allowed_kinds:
            raise ValueError("allowed_kinds must not be empty")
        if (
            isinstance(self.max_inline_chars, bool)
            or not isinstance(self.max_inline_chars, int)
            or self.max_inline_chars < 1
            or self.max_inline_chars > MAX_MEMORY_CONTENT_CHARS
        ):
            raise ValueError("max_inline_chars is invalid")


@dataclass(frozen=True, slots=True)
class MemoryPolicyResult:
    decision: MemoryWriteDecision
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision is MemoryWriteDecision.ALLOW


class MemoryPolicyEngine:
    def __init__(self, policy: MemoryWritePolicy | None = None) -> None:
        self.policy = policy or MemoryWritePolicy()

    def evaluate(self, proposal: MemoryWriteProposal) -> MemoryPolicyResult:
        if not isinstance(proposal, MemoryWriteProposal):
            raise TypeError("proposal must be MemoryWriteProposal")
        if proposal.kind not in self.policy.allowed_kinds:
            return MemoryPolicyResult(MemoryWriteDecision.DENY, "kind_not_allowed")
        if self.policy.require_provenance and not proposal.provenance_refs:
            return MemoryPolicyResult(MemoryWriteDecision.DENY, "provenance_required")
        if self.policy.require_source_operation and proposal.source_operation_id is None:
            return MemoryPolicyResult(
                MemoryWriteDecision.DENY,
                "source_operation_required",
            )
        if proposal.content is not None and len(proposal.content) > self.policy.max_inline_chars:
            return MemoryPolicyResult(
                MemoryWriteDecision.DENY,
                "inline_content_too_large",
            )
        if self.policy.review_restricted_data and proposal.data_class == "restricted":
            return MemoryPolicyResult(
                MemoryWriteDecision.REVIEW,
                "restricted_data_requires_review",
            )
        return MemoryPolicyResult(MemoryWriteDecision.ALLOW, "policy_allows")


__all__ = [
    "MemoryPolicyEngine",
    "MemoryPolicyResult",
    "MemoryWriteDecision",
    "MemoryWritePolicy",
]
