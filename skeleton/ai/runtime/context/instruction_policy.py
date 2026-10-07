"""Versioned instruction-policy identities for canonical context assembly."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Iterable
from uuid import NAMESPACE_URL, uuid5

from skeleton.contracts.context import ContextKind, ContextSegment, ContextTrust


INSTRUCTION_POLICY_SCHEMA_VERSION = 1
_ALLOWED_KINDS = frozenset(
    {
        ContextKind.SYSTEM_POLICY,
        ContextKind.PRODUCT_INSTRUCTION,
        ContextKind.OPERATION_OBJECTIVE,
        ContextKind.SKILL_INSTRUCTION,
    }
)


class InstructionPolicyError(ValueError):
    """A versioned instruction policy violates canonical identity rules."""


def _text(value: object, field: str, *, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InstructionPolicyError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if normalized != value:
        raise InstructionPolicyError(f"{field} must be normalized")
    if len(normalized) > max_length:
        raise InstructionPolicyError(f"{field} exceeds maximum length")
    return normalized


@dataclass(frozen=True, slots=True)
class InstructionPolicy:
    """Immutable instruction content with a stable versioned identity."""

    policy_id: str
    version: str
    instructions: str
    source_type: str = "product-policy"
    data_class: str = "internal"
    schema_version: int = INSTRUCTION_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text(self.policy_id, "policy_id", max_length=256)
        _text(self.version, "version", max_length=64)
        _text(self.instructions, "instructions", max_length=100_000)
        _text(self.source_type, "source_type", max_length=128)
        data_class = _text(self.data_class, "data_class", max_length=32).lower()
        if data_class not in {"public", "internal", "confidential", "restricted"}:
            raise InstructionPolicyError("data_class is invalid")
        object.__setattr__(self, "data_class", data_class)
        if self.schema_version != INSTRUCTION_POLICY_SCHEMA_VERSION:
            raise InstructionPolicyError("unsupported instruction policy schema version")

    @property
    def digest(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "version": self.version,
            "instructions": self.instructions,
            "source_type": self.source_type,
            "data_class": self.data_class,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def identity(self) -> str:
        return f"{self.policy_id}@{self.version}#{self.digest}"

    def to_segment(
        self,
        *,
        tenant_id: str,
        purpose: str,
        created_at: datetime,
        kind: ContextKind = ContextKind.PRODUCT_INSTRUCTION,
        priority: int = 950,
        mandatory: bool = False,
        provenance: Iterable[str] = (),
    ) -> ContextSegment:
        try:
            normalized_kind = ContextKind(kind)
        except ValueError as exc:
            raise InstructionPolicyError("instruction policy context kind is invalid") from exc
        if normalized_kind not in _ALLOWED_KINDS:
            raise InstructionPolicyError(
                "instruction policy cannot project into non-instruction context kind"
            )
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise InstructionPolicyError("created_at must be timezone-aware")
        _text(tenant_id, "tenant_id", max_length=1024)
        _text(purpose, "purpose", max_length=256)

        segment_id = str(
            uuid5(
                NAMESPACE_URL,
                "instruction-policy:" + self.identity,
            )
        )
        refs = (
            "instruction-policy:" + self.policy_id,
            "instruction-version:" + self.version,
            "instruction-digest:" + self.digest,
            *tuple(provenance),
        )
        return ContextSegment.from_content(
            segment_id=segment_id,
            kind=normalized_kind,
            source_type=self.source_type,
            source_id=self.policy_id + "@" + self.version,
            content=self.instructions,
            trust_level=ContextTrust.TRUSTED_CONTROL,
            data_class=self.data_class,
            tenant_id=tenant_id,
            purpose=purpose,
            priority=priority,
            relevance=1.0,
            created_at=created_at.astimezone(timezone.utc),
            provenance=refs,
            retention_class="instruction-policy",
            mandatory=mandatory,
        )


class InstructionPolicyRegistry:
    """Small deterministic registry with explicit activation and rollback."""

    def __init__(self, policies: Iterable[InstructionPolicy] = ()) -> None:
        self._policies: dict[tuple[str, str], InstructionPolicy] = {}
        self._active: dict[str, str] = {}
        for policy in policies:
            self.register(policy)

    def register(
        self,
        policy: InstructionPolicy,
        *,
        activate: bool = False,
    ) -> InstructionPolicy:
        if not isinstance(policy, InstructionPolicy):
            raise TypeError("policy must be InstructionPolicy")
        key = (policy.policy_id, policy.version)
        existing = self._policies.get(key)
        if existing is not None and existing.digest != policy.digest:
            raise InstructionPolicyError(
                "instruction policy version cannot be redefined with different content"
            )
        self._policies[key] = policy
        if policy.policy_id not in self._active or activate:
            self._active[policy.policy_id] = policy.version
        return policy

    def get(
        self,
        policy_id: str,
        version: str | None = None,
    ) -> InstructionPolicy:
        _text(policy_id, "policy_id", max_length=256)
        resolved_version = version or self._active.get(policy_id)
        if resolved_version is None:
            raise InstructionPolicyError("instruction policy has no active version")
        try:
            return self._policies[(policy_id, resolved_version)]
        except KeyError as exc:
            raise InstructionPolicyError("instruction policy version is not registered") from exc

    def activate(self, policy_id: str, version: str) -> InstructionPolicy:
        policy = self.get(policy_id, version)
        self._active[policy_id] = policy.version
        return policy

    def rollback(self, policy_id: str, version: str) -> InstructionPolicy:
        return self.activate(policy_id, version)

    def active_identity(self, policy_id: str) -> str:
        return self.get(policy_id).identity

    def snapshot(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(
            sorted(
                (
                    policy_id,
                    version,
                    policy.digest,
                )
                for (policy_id, version), policy in self._policies.items()
            )
        )


__all__ = [
    "INSTRUCTION_POLICY_SCHEMA_VERSION",
    "InstructionPolicy",
    "InstructionPolicyError",
    "InstructionPolicyRegistry",
]
