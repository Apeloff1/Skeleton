"""Fail-closed execution-authority contracts for the governed AI runtime.

This module binds one AI execution to a finite, expiring set of capabilities and
a monotonic resource budget.  The objects here are immutable data contracts:
they carry authority evidence but do not execute tools, providers, or jobs.

Design invariants:
* authority is explicitly bound to operation + execution + actor;
* capability sets are canonicalized and deny by default;
* every authority has an absolute UTC expiry;
* resource budgets are finite and integer-valued;
* canonical identity is content-addressed and transport-neutral;
* usage accounting is monotonic and can never be "refunded" by a caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import re
from typing import Any, Iterable, Mapping

from .canonical import canonical_json_bytes


EXECUTION_AUTHORITY_SCHEMA_VERSION = 1
MAX_AUTHORITY_CAPABILITIES = 256
MAX_AUTHORITY_LIFETIME_SECONDS = 86_400
MAX_CAPABILITY_LENGTH = 192
MAX_ID_LENGTH = 192
MAX_POLICY_DIGEST_LENGTH = 64

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,191}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CAPABILITY = re.compile(r"^[a-z0-9][a-z0-9_.:/-]{0,191}$")


class ExecutionAuthorityError(ValueError):
    """Raised when an execution-authority contract is malformed."""


class AuthorityEffect(str, Enum):
    """Effect of an authority decision.

    ALLOW is intentionally the only granting value.  Absence of an ALLOW grant
    is a denial; there is no implicit or wildcard authority.
    """

    ALLOW = "allow"


def _bounded_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ExecutionAuthorityError(f"invalid {field_name}")
    return value


def _digest(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ExecutionAuthorityError(f"{field_name} must be lowercase sha256")
    return value


def _aware_utc(value: object, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ExecutionAuthorityError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _finite_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExecutionAuthorityError(f"{field_name} must be a non-negative integer")
    return value


def _finite_positive_int(value: object, field_name: str) -> int:
    parsed = _finite_non_negative_int(value, field_name)
    if parsed == 0:
        raise ExecutionAuthorityError(f"{field_name} must be greater than zero")
    return parsed


def _canonical_capabilities(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ExecutionAuthorityError("capabilities must be an iterable of strings")
    normalized: set[str] = set()
    for raw in values:
        if not isinstance(raw, str) or _CAPABILITY.fullmatch(raw) is None:
            raise ExecutionAuthorityError("invalid capability")
        normalized.add(raw)
        if len(normalized) > MAX_AUTHORITY_CAPABILITIES:
            raise ExecutionAuthorityError("too many capabilities")
    if not normalized:
        raise ExecutionAuthorityError("at least one capability is required")
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class ResourceBudget:
    """Finite limits attached to one execution authority."""

    provider_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    artifact_bytes: int
    wall_time_ms: int
    parallelism: int = 1

    def __post_init__(self) -> None:
        for name in (
            "provider_calls",
            "tool_calls",
            "input_tokens",
            "output_tokens",
            "artifact_bytes",
            "wall_time_ms",
        ):
            _finite_non_negative_int(getattr(self, name), name)
        _finite_positive_int(self.parallelism, "parallelism")

    def as_dict(self) -> dict[str, int]:
        return {
            "provider_calls": self.provider_calls,
            "tool_calls": self.tool_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "artifact_bytes": self.artifact_bytes,
            "wall_time_ms": self.wall_time_ms,
            "parallelism": self.parallelism,
        }

    def permits(self, usage: "ResourceUsage") -> bool:
        if not isinstance(usage, ResourceUsage):
            raise ExecutionAuthorityError("usage must be ResourceUsage")
        return (
            usage.provider_calls <= self.provider_calls
            and usage.tool_calls <= self.tool_calls
            and usage.input_tokens <= self.input_tokens
            and usage.output_tokens <= self.output_tokens
            and usage.artifact_bytes <= self.artifact_bytes
            and usage.wall_time_ms <= self.wall_time_ms
            and usage.parallelism <= self.parallelism
        )

    def is_within(self, parent: "ResourceBudget") -> bool:
        """Return whether every child limit is no broader than the parent."""

        if not isinstance(parent, ResourceBudget):
            raise ExecutionAuthorityError("parent must be ResourceBudget")
        return (
            self.provider_calls <= parent.provider_calls
            and self.tool_calls <= parent.tool_calls
            and self.input_tokens <= parent.input_tokens
            and self.output_tokens <= parent.output_tokens
            and self.artifact_bytes <= parent.artifact_bytes
            and self.wall_time_ms <= parent.wall_time_ms
            and self.parallelism <= parent.parallelism
        )


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    """Monotonic resource-accounting vector."""

    provider_calls: int = 0
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    artifact_bytes: int = 0
    wall_time_ms: int = 0
    parallelism: int = 0

    def __post_init__(self) -> None:
        for name in (
            "provider_calls",
            "tool_calls",
            "input_tokens",
            "output_tokens",
            "artifact_bytes",
            "wall_time_ms",
            "parallelism",
        ):
            _finite_non_negative_int(getattr(self, name), name)

    def add(self, delta: "ResourceUsage") -> "ResourceUsage":
        if not isinstance(delta, ResourceUsage):
            raise ExecutionAuthorityError("delta must be ResourceUsage")
        return ResourceUsage(
            provider_calls=self.provider_calls + delta.provider_calls,
            tool_calls=self.tool_calls + delta.tool_calls,
            input_tokens=self.input_tokens + delta.input_tokens,
            output_tokens=self.output_tokens + delta.output_tokens,
            artifact_bytes=self.artifact_bytes + delta.artifact_bytes,
            wall_time_ms=self.wall_time_ms + delta.wall_time_ms,
            parallelism=max(self.parallelism, delta.parallelism),
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "provider_calls": self.provider_calls,
            "tool_calls": self.tool_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "artifact_bytes": self.artifact_bytes,
            "wall_time_ms": self.wall_time_ms,
            "parallelism": self.parallelism,
        }


@dataclass(frozen=True, slots=True)
class ExecutionAuthority:
    """Content-addressed, expiring authority for exactly one AI execution."""

    authority_id: str
    operation_id: str
    execution_id: str
    actor_id: str
    issuer_id: str
    issued_at: datetime
    expires_at: datetime
    capabilities: tuple[str, ...]
    budget: ResourceBudget
    policy_digest: str
    nonce: str
    parent_authority_digest: str | None = None
    schema_version: int = EXECUTION_AUTHORITY_SCHEMA_VERSION
    effect: AuthorityEffect = AuthorityEffect.ALLOW

    def __post_init__(self) -> None:
        for name in (
            "authority_id",
            "operation_id",
            "execution_id",
            "actor_id",
            "issuer_id",
            "nonce",
        ):
            object.__setattr__(self, name, _bounded_id(getattr(self, name), name))

        issued = _aware_utc(self.issued_at, "issued_at")
        expires = _aware_utc(self.expires_at, "expires_at")
        if expires <= issued:
            raise ExecutionAuthorityError("expires_at must be later than issued_at")
        lifetime = (expires - issued).total_seconds()
        if lifetime > MAX_AUTHORITY_LIFETIME_SECONDS:
            raise ExecutionAuthorityError("authority lifetime exceeds maximum")

        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(
            self, "capabilities", _canonical_capabilities(self.capabilities)
        )

        if not isinstance(self.budget, ResourceBudget):
            raise ExecutionAuthorityError("budget must be ResourceBudget")
        object.__setattr__(
            self, "policy_digest", _digest(self.policy_digest, "policy_digest")
        )
        if self.parent_authority_digest is not None:
            object.__setattr__(
                self,
                "parent_authority_digest",
                _digest(self.parent_authority_digest, "parent_authority_digest"),
            )
        if self.schema_version != EXECUTION_AUTHORITY_SCHEMA_VERSION:
            raise ExecutionAuthorityError("unsupported execution-authority schema")
        if not isinstance(self.effect, AuthorityEffect):
            try:
                object.__setattr__(self, "effect", AuthorityEffect(self.effect))
            except ValueError as exc:
                raise ExecutionAuthorityError("invalid authority effect") from exc

    def expired(self, *, now: datetime | None = None) -> bool:
        instant = _aware_utc(now or datetime.now(timezone.utc), "now")
        return instant >= self.expires_at

    def active(self, *, now: datetime | None = None) -> bool:
        instant = _aware_utc(now or datetime.now(timezone.utc), "now")
        return self.issued_at <= instant < self.expires_at

    def permits(
        self,
        capability: str,
        *,
        usage: ResourceUsage | None = None,
        now: datetime | None = None,
    ) -> bool:
        if not isinstance(capability, str) or _CAPABILITY.fullmatch(capability) is None:
            return False
        if self.effect is not AuthorityEffect.ALLOW or not self.active(now=now):
            return False
        if capability not in self.capabilities:
            return False
        return self.budget.permits(usage or ResourceUsage())

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authority_id": self.authority_id,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "actor_id": self.actor_id,
            "issuer_id": self.issuer_id,
            "issued_at": self.issued_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "effect": self.effect.value,
            "capabilities": list(self.capabilities),
            "budget": self.budget.as_dict(),
            "policy_digest": self.policy_digest,
            "nonce": self.nonce,
            "parent_authority_digest": self.parent_authority_digest,
        }

    @property
    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.canonical_payload())

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.canonical_bytes).hexdigest()


@dataclass(frozen=True, slots=True)
class AdmissionReceipt:
    """Immutable evidence that a concrete request was admitted under an authority."""

    receipt_id: str
    authority_digest: str
    request_identity_digest: str
    operation_id: str
    execution_id: str
    admitted_at: datetime
    expires_at: datetime
    replay_key: str
    schema_version: int = EXECUTION_AUTHORITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("receipt_id", "operation_id", "execution_id", "replay_key"):
            object.__setattr__(self, name, _bounded_id(getattr(self, name), name))
        object.__setattr__(
            self, "authority_digest", _digest(self.authority_digest, "authority_digest")
        )
        object.__setattr__(
            self,
            "request_identity_digest",
            _digest(self.request_identity_digest, "request_identity_digest"),
        )
        admitted = _aware_utc(self.admitted_at, "admitted_at")
        expires = _aware_utc(self.expires_at, "expires_at")
        if expires <= admitted:
            raise ExecutionAuthorityError("receipt expires_at must be later than admitted_at")
        object.__setattr__(self, "admitted_at", admitted)
        object.__setattr__(self, "expires_at", expires)
        if self.schema_version != EXECUTION_AUTHORITY_SCHEMA_VERSION:
            raise ExecutionAuthorityError("unsupported admission-receipt schema")

    def expired(self, *, now: datetime | None = None) -> bool:
        instant = _aware_utc(now or datetime.now(timezone.utc), "now")
        return instant >= self.expires_at

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "authority_digest": self.authority_digest,
            "request_identity_digest": self.request_identity_digest,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "admitted_at": self.admitted_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "replay_key": self.replay_key,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.canonical_payload())).hexdigest()



@dataclass(frozen=True, slots=True)
class AuthorityConsumptionReceipt:
    """Tamper-evident evidence for one granted capability consumption."""

    authority_digest: str
    operation_id: str
    execution_id: str
    actor_id: str
    capability: str
    sequence: int
    replay_key: str
    authorized_at: datetime
    delta_usage: ResourceUsage
    total_usage: ResourceUsage
    previous_receipt_digest: str | None = None
    schema_version: int = EXECUTION_AUTHORITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "authority_digest", _digest(self.authority_digest, "authority_digest")
        )
        for name in ("operation_id", "execution_id", "actor_id", "replay_key"):
            object.__setattr__(self, name, _bounded_id(getattr(self, name), name))
        if not isinstance(self.capability, str) or _CAPABILITY.fullmatch(self.capability) is None:
            raise ExecutionAuthorityError("invalid capability")
        _finite_positive_int(self.sequence, "sequence")
        object.__setattr__(
            self, "authorized_at", _aware_utc(self.authorized_at, "authorized_at")
        )
        if not isinstance(self.delta_usage, ResourceUsage):
            raise ExecutionAuthorityError("delta_usage must be ResourceUsage")
        if not isinstance(self.total_usage, ResourceUsage):
            raise ExecutionAuthorityError("total_usage must be ResourceUsage")
        if self.previous_receipt_digest is not None:
            object.__setattr__(
                self,
                "previous_receipt_digest",
                _digest(self.previous_receipt_digest, "previous_receipt_digest"),
            )
        if self.sequence == 1 and self.previous_receipt_digest is not None:
            raise ExecutionAuthorityError(
                "first consumption receipt cannot have previous_receipt_digest"
            )
        if self.sequence > 1 and self.previous_receipt_digest is None:
            raise ExecutionAuthorityError(
                "non-root consumption receipt requires previous_receipt_digest"
            )
        if self.schema_version != EXECUTION_AUTHORITY_SCHEMA_VERSION:
            raise ExecutionAuthorityError("unsupported consumption-receipt schema")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authority_digest": self.authority_digest,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "actor_id": self.actor_id,
            "capability": self.capability,
            "sequence": self.sequence,
            "replay_key": self.replay_key,
            "authorized_at": self.authorized_at.isoformat(),
            "delta_usage": self.delta_usage.as_dict(),
            "total_usage": self.total_usage.as_dict(),
            "previous_receipt_digest": self.previous_receipt_digest,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.canonical_payload())).hexdigest()


@dataclass(frozen=True, slots=True)
class AuthorityEvidenceBundle:
    """Compact final evidence binding authority admission to accounted consumption."""

    authority_digest: str
    operation_id: str
    execution_id: str
    admission_receipt_digest: str
    consumption_count: int
    latest_consumption_digest: str | None
    final_usage: ResourceUsage
    revoked: bool
    sealed_at: datetime
    schema_version: int = EXECUTION_AUTHORITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("authority_digest", "admission_receipt_digest"):
            object.__setattr__(self, name, _digest(getattr(self, name), name))
        for name in ("operation_id", "execution_id"):
            object.__setattr__(self, name, _bounded_id(getattr(self, name), name))
        _finite_non_negative_int(self.consumption_count, "consumption_count")
        if self.latest_consumption_digest is not None:
            object.__setattr__(
                self,
                "latest_consumption_digest",
                _digest(self.latest_consumption_digest, "latest_consumption_digest"),
            )
        if self.consumption_count == 0 and self.latest_consumption_digest is not None:
            raise ExecutionAuthorityError(
                "empty authority evidence cannot have latest consumption digest"
            )
        if self.consumption_count > 0 and self.latest_consumption_digest is None:
            raise ExecutionAuthorityError(
                "non-empty authority evidence requires latest consumption digest"
            )
        if not isinstance(self.final_usage, ResourceUsage):
            raise ExecutionAuthorityError("final_usage must be ResourceUsage")
        if not isinstance(self.revoked, bool):
            raise ExecutionAuthorityError("revoked must be boolean")
        object.__setattr__(self, "sealed_at", _aware_utc(self.sealed_at, "sealed_at"))
        if self.schema_version != EXECUTION_AUTHORITY_SCHEMA_VERSION:
            raise ExecutionAuthorityError("unsupported authority-evidence schema")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authority_digest": self.authority_digest,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "admission_receipt_digest": self.admission_receipt_digest,
            "consumption_count": self.consumption_count,
            "latest_consumption_digest": self.latest_consumption_digest,
            "final_usage": self.final_usage.as_dict(),
            "revoked": self.revoked,
            "sealed_at": self.sealed_at.isoformat(),
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.canonical_payload())).hexdigest()


def verify_authority_receipt_chain(
    authority: ExecutionAuthority,
    receipts: Iterable[AuthorityConsumptionReceipt],
) -> ResourceUsage:
    """Verify receipt identity, hash continuity, sequence, and cumulative accounting."""

    if not isinstance(authority, ExecutionAuthority):
        raise ExecutionAuthorityError("authority must be ExecutionAuthority")
    if isinstance(receipts, (str, bytes)):
        raise ExecutionAuthorityError("receipts must be an iterable")

    total = ResourceUsage()
    previous_digest: str | None = None
    previous_authorized_at: datetime | None = None
    expected_sequence = 1
    for receipt in receipts:
        if not isinstance(receipt, AuthorityConsumptionReceipt):
            raise ExecutionAuthorityError(
                "receipt chain contains non-consumption receipt"
            )
        if receipt.authority_digest != authority.digest:
            raise ExecutionAuthorityError("receipt authority digest mismatch")
        for name in ("operation_id", "execution_id", "actor_id"):
            if getattr(receipt, name) != getattr(authority, name):
                raise ExecutionAuthorityError(f"receipt {name} mismatch")
        if receipt.sequence != expected_sequence:
            raise ExecutionAuthorityError("receipt sequence is not contiguous")
        if receipt.previous_receipt_digest != previous_digest:
            raise ExecutionAuthorityError("receipt hash chain is discontinuous")
        if (
            previous_authorized_at is not None
            and receipt.authorized_at < previous_authorized_at
        ):
            raise ExecutionAuthorityError("receipt authorization time regressed")
        total = total.add(receipt.delta_usage)
        if receipt.total_usage != total:
            raise ExecutionAuthorityError("receipt cumulative usage mismatch")
        if not authority.budget.permits(total):
            raise ExecutionAuthorityError("receipt chain exceeds authority budget")
        previous_digest = receipt.digest
        previous_authorized_at = receipt.authorized_at
        expected_sequence += 1
    return total


def validate_authority_attenuation(
    parent: ExecutionAuthority,
    child: ExecutionAuthority,
) -> None:
    """Reject delegated authority that can exceed its parent in any dimension."""

    if not isinstance(parent, ExecutionAuthority) or not isinstance(
        child, ExecutionAuthority
    ):
        raise ExecutionAuthorityError("parent and child must be ExecutionAuthority")
    if child.parent_authority_digest != parent.digest:
        raise ExecutionAuthorityError("child is not bound to parent authority digest")
    for name in ("operation_id", "execution_id"):
        if getattr(child, name) != getattr(parent, name):
            raise ExecutionAuthorityError(f"delegated {name} mismatch")
    if child.issuer_id != parent.actor_id:
        raise ExecutionAuthorityError("child issuer is not the parent actor")
    if child.issued_at < parent.issued_at:
        raise ExecutionAuthorityError("child authority predates parent")
    if child.expires_at > parent.expires_at:
        raise ExecutionAuthorityError("child authority outlives parent")
    if not set(child.capabilities).issubset(parent.capabilities):
        raise ExecutionAuthorityError("child authority escalates capabilities")
    if not child.budget.is_within(parent.budget):
        raise ExecutionAuthorityError("child authority escalates resource budget")


def authority_policy_digest(policy: Mapping[str, Any]) -> str:
    """Return the stable policy digest used to bind an authority to policy input."""

    if not isinstance(policy, Mapping):
        raise ExecutionAuthorityError("policy must be a mapping")
    return hashlib.sha256(canonical_json_bytes(dict(policy))).hexdigest()


__all__ = [
    "AdmissionReceipt",
    "AuthorityConsumptionReceipt",
    "AuthorityEffect",
    "AuthorityEvidenceBundle",
    "EXECUTION_AUTHORITY_SCHEMA_VERSION",
    "ExecutionAuthority",
    "ExecutionAuthorityError",
    "MAX_AUTHORITY_CAPABILITIES",
    "MAX_AUTHORITY_LIFETIME_SECONDS",
    "ResourceBudget",
    "ResourceUsage",
    "authority_policy_digest",
    "validate_authority_attenuation",
    "verify_authority_receipt_chain",
]
