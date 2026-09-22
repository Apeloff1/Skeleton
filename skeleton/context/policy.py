"""Admission policy for canonical context segments."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.contracts.context import (
    ContextKind,
    ContextSegment,
    ContextTrust,
)


class ContextPolicyError(PermissionError):
    """A mandatory context segment cannot be admitted safely."""


_DATA_CLASS_RANK = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}

_DEFAULT_TRUSTED_CONTROL_SOURCES = (
    "platform-policy",
    "product-policy",
    "operation",
    "skill-registry",
    "tool-registry",
)


@dataclass(frozen=True, slots=True)
class ContextAdmissionDecision:
    allowed: bool
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {"allowed": self.allowed, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class ContextCompilePolicy:
    max_data_class: str = "confidential"
    allow_global_trusted_control: bool = True
    trusted_control_sources: tuple[str, ...] = _DEFAULT_TRUSTED_CONTROL_SOURCES

    def __post_init__(self) -> None:
        if self.max_data_class not in _DATA_CLASS_RANK:
            raise ValueError("max_data_class is invalid")
        if not self.trusted_control_sources:
            raise ValueError("trusted_control_sources must not be empty")
        if any(not isinstance(item, str) or not item.strip() for item in self.trusted_control_sources):
            raise ValueError("trusted_control_sources entries must be non-empty strings")

    def inspect(
        self,
        segment: ContextSegment,
        *,
        tenant_id: str,
        purpose: str,
    ) -> ContextAdmissionDecision:
        if not isinstance(segment, ContextSegment):
            return ContextAdmissionDecision(False, "invalid_segment")

        if segment.tenant_id != tenant_id:
            global_control = (
                segment.tenant_id == "*"
                and self.allow_global_trusted_control
                and segment.trust_level is ContextTrust.TRUSTED_CONTROL
            )
            if not global_control:
                return ContextAdmissionDecision(False, "tenant_mismatch")

        if segment.purpose not in {purpose, "*"}:
            return ContextAdmissionDecision(False, "purpose_mismatch")

        if _DATA_CLASS_RANK[segment.data_class] > _DATA_CLASS_RANK[self.max_data_class]:
            return ContextAdmissionDecision(False, "data_class_denied")

        if segment.trust_level is ContextTrust.TRUSTED_CONTROL:
            if segment.source_type not in self.trusted_control_sources:
                return ContextAdmissionDecision(False, "untrusted_control_source")
            if segment.kind not in {
                ContextKind.SYSTEM_POLICY,
                ContextKind.PRODUCT_INSTRUCTION,
                ContextKind.OPERATION_OBJECTIVE,
                ContextKind.SKILL_INSTRUCTION,
                ContextKind.TOOL_SCHEMA,
            }:
                return ContextAdmissionDecision(False, "invalid_control_kind")
        elif segment.kind in {
            ContextKind.SYSTEM_POLICY,
            ContextKind.PRODUCT_INSTRUCTION,
            ContextKind.OPERATION_OBJECTIVE,
            ContextKind.TOOL_SCHEMA,
        }:
            return ContextAdmissionDecision(False, "control_kind_requires_trusted_source")

        return ContextAdmissionDecision(True, "allowed")

    def require(
        self,
        segment: ContextSegment,
        *,
        tenant_id: str,
        purpose: str,
    ) -> ContextAdmissionDecision:
        decision = self.inspect(segment, tenant_id=tenant_id, purpose=purpose)
        if not decision.allowed:
            raise ContextPolicyError(
                f"context segment {segment.segment_id} denied: {decision.reason}"
            )
        return decision


__all__ = [
    "ContextAdmissionDecision",
    "ContextCompilePolicy",
    "ContextPolicyError",
]
