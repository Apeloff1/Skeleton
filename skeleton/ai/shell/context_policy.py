"""Policy for admitting provenance-labeled context into model requests."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.context_provenance import (
    ContextBundle,
    ContextSensitivity,
    ContextTrust,
)


@dataclass(frozen=True)
class ContextPolicy:
    allow_confidential: bool = False
    allow_untrusted: bool = True
    max_items: int = 128
    max_total_bytes: int = 131072
    max_untrusted_bytes: int = 32768

    def __post_init__(self) -> None:
        if self.max_items <= 0:
            raise ValueError("max_items must be positive")
        if self.max_total_bytes <= 0 or self.max_untrusted_bytes < 0:
            raise ValueError("invalid context byte limits")
        if self.max_untrusted_bytes > self.max_total_bytes:
            raise ValueError("untrusted context budget exceeds total budget")


@dataclass(frozen=True)
class ContextPolicyDecision:
    allowed: bool
    reasons: tuple[str, ...]
    total_bytes: int
    untrusted_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "reasons": list(self.reasons),
            "total_bytes": self.total_bytes,
            "untrusted_bytes": self.untrusted_bytes,
        }


class ContextPolicyEngine:
    def __init__(self, policy: ContextPolicy | None = None) -> None:
        self.policy = policy or ContextPolicy()

    def inspect(self, bundle: ContextBundle) -> ContextPolicyDecision:
        reasons = []
        if len(bundle.items) > self.policy.max_items:
            reasons.append("context item count exceeds policy")
        total = sum(len(item.content.encode()) for item in bundle.items)
        if total > self.policy.max_total_bytes:
            reasons.append("context byte size exceeds policy")
        untrusted = sum(
            len(item.content.encode())
            for item in bundle.items
            if item.trust is ContextTrust.UNTRUSTED
        )
        if untrusted > self.policy.max_untrusted_bytes:
            reasons.append("untrusted context byte size exceeds policy")
        if not self.policy.allow_untrusted and bundle.untrusted_items:
            reasons.append("untrusted context is not permitted")
        if any(
            item.sensitivity is ContextSensitivity.SECRET
            for item in bundle.items
        ):
            reasons.append("secret context cannot be sent to model")
        if (
            not self.policy.allow_confidential
            and any(
                item.sensitivity is ContextSensitivity.CONFIDENTIAL
                for item in bundle.items
            )
        ):
            reasons.append("confidential context is not permitted")
        return ContextPolicyDecision(not reasons, tuple(reasons), total, untrusted)

    def require(self, bundle: ContextBundle) -> ContextPolicyDecision:
        decision = self.inspect(bundle)
        if not decision.allowed:
            raise PermissionError("; ".join(decision.reasons))
        return decision
