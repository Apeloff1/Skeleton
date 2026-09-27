"""Fail-closed agent delegation, handoff, budget, and lease qualification.

Existing swarm runtimes remain the scheduling/lease authority. This module
binds a parent-to-child delegation to one durable handoff packet and the exact
live lease fence that may commit the delegated task. It does not execute work
or mint authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterable

from skeleton.agents.swarm_fencing import LeaseFence, assert_fence
from skeleton.agents.swarm_runtime import LeaseError, SwarmRuntime
from skeleton.contracts.canonical import EvidenceRef


AGENT_DELEGATION_SCHEMA_VERSION = 1
AGENT_DELEGATION_TASK_ID = "P1-AUTO-02"
AGENT_DELEGATION_ACCOUNTABILITY_ID = "ACC-P1-AUTO-02"
_MAX_SCOPES = 128
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AgentDelegationError(ValueError):
    """Delegation or handoff evidence is malformed."""


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise AgentDelegationError(f"{field} must be a canonical token")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise AgentDelegationError(f"{field} must be lowercase sha256")
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentDelegationError(f"{field} must be finite numeric")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise AgentDelegationError(f"{field} must be finite numeric")
    return normalized


def _nonnegative(value: object, field: str) -> float:
    normalized = _finite(value, field)
    if normalized < 0:
        raise AgentDelegationError(f"{field} must be non-negative")
    return normalized


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AgentDelegationError(f"{field} must be a non-negative integer")
    return value


def _positive_int(value: object, field: str) -> int:
    value = _nonnegative_int(value, field)
    if value < 1:
        raise AgentDelegationError(f"{field} must be positive")
    return value


def _scopes(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise AgentDelegationError(f"{field} must be an iterable")
    normalized: set[str] = set()
    for value in values:
        normalized.add(_token(value, field))
        if len(normalized) > _MAX_SCOPES:
            raise AgentDelegationError(f"{field} exceeds scope limit")
    return tuple(sorted(normalized))


def _canonical_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    agent_id: str
    tenant_id: str
    generation: int
    authority_scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", _token(self.agent_id, "agent_id"))
        object.__setattr__(self, "tenant_id", _token(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self,
            "generation",
            _positive_int(self.generation, "generation"),
        )
        object.__setattr__(
            self,
            "authority_scopes",
            _scopes(self.authority_scopes, "authority_scopes"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "generation": self.generation,
            "authority_scopes": list(self.authority_scopes),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class DelegationBudget:
    max_tool_calls: int
    max_tokens: int
    max_cost_units: float
    max_wall_time_s: float
    max_payload_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_tool_calls",
            _nonnegative_int(self.max_tool_calls, "max_tool_calls"),
        )
        object.__setattr__(
            self,
            "max_tokens",
            _nonnegative_int(self.max_tokens, "max_tokens"),
        )
        object.__setattr__(
            self,
            "max_cost_units",
            _nonnegative(self.max_cost_units, "max_cost_units"),
        )
        object.__setattr__(
            self,
            "max_wall_time_s",
            _nonnegative(self.max_wall_time_s, "max_wall_time_s"),
        )
        object.__setattr__(
            self,
            "max_payload_bytes",
            _nonnegative_int(self.max_payload_bytes, "max_payload_bytes"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "max_tool_calls": self.max_tool_calls,
            "max_tokens": self.max_tokens,
            "max_cost_units": self.max_cost_units,
            "max_wall_time_s": self.max_wall_time_s,
            "max_payload_bytes": self.max_payload_bytes,
        }

    def contains(self, other: "DelegationBudget") -> bool:
        if not isinstance(other, DelegationBudget):
            return False
        return (
            other.max_tool_calls <= self.max_tool_calls
            and other.max_tokens <= self.max_tokens
            and other.max_cost_units <= self.max_cost_units
            and other.max_wall_time_s <= self.max_wall_time_s
            and other.max_payload_bytes <= self.max_payload_bytes
        )


@dataclass(frozen=True, slots=True)
class DelegationUsage:
    tool_calls: int = 0
    tokens: int = 0
    cost_units: float = 0.0
    wall_time_s: float = 0.0
    payload_bytes: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tool_calls",
            _nonnegative_int(self.tool_calls, "tool_calls"),
        )
        object.__setattr__(
            self,
            "tokens",
            _nonnegative_int(self.tokens, "tokens"),
        )
        object.__setattr__(
            self,
            "cost_units",
            _nonnegative(self.cost_units, "cost_units"),
        )
        object.__setattr__(
            self,
            "wall_time_s",
            _nonnegative(self.wall_time_s, "wall_time_s"),
        )
        object.__setattr__(
            self,
            "payload_bytes",
            _nonnegative_int(self.payload_bytes, "payload_bytes"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "tool_calls": self.tool_calls,
            "tokens": self.tokens,
            "cost_units": self.cost_units,
            "wall_time_s": self.wall_time_s,
            "payload_bytes": self.payload_bytes,
        }

    def within(self, budget: DelegationBudget) -> bool:
        if not isinstance(budget, DelegationBudget):
            return False
        return (
            self.tool_calls <= budget.max_tool_calls
            and self.tokens <= budget.max_tokens
            and self.cost_units <= budget.max_cost_units
            and self.wall_time_s <= budget.max_wall_time_s
            and self.payload_bytes <= budget.max_payload_bytes
        )


@dataclass(frozen=True, slots=True)
class HandoffPacket:
    handoff_id: str
    delegation_id: str
    task_id: str
    parent_agent_id: str
    child_agent_id: str
    context_digest: str
    payload_digest: str
    checkpoint_ref: str
    required_scopes: tuple[str, ...]
    created_at: float

    def __post_init__(self) -> None:
        for field in (
            "handoff_id",
            "delegation_id",
            "task_id",
            "parent_agent_id",
            "child_agent_id",
            "checkpoint_ref",
        ):
            object.__setattr__(self, field, _token(getattr(self, field), field))
        object.__setattr__(
            self,
            "context_digest",
            _sha256(self.context_digest, "context_digest"),
        )
        object.__setattr__(
            self,
            "payload_digest",
            _sha256(self.payload_digest, "payload_digest"),
        )
        object.__setattr__(
            self,
            "required_scopes",
            _scopes(self.required_scopes, "required_scopes"),
        )
        created = _nonnegative(self.created_at, "created_at")
        object.__setattr__(self, "created_at", created)

    def payload(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "delegation_id": self.delegation_id,
            "task_id": self.task_id,
            "parent_agent_id": self.parent_agent_id,
            "child_agent_id": self.child_agent_id,
            "context_digest": self.context_digest,
            "payload_digest": self.payload_digest,
            "checkpoint_ref": self.checkpoint_ref,
            "required_scopes": list(self.required_scopes),
            "created_at": self.created_at,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class DelegationGrant:
    delegation_id: str
    parent: AgentIdentity
    child: AgentIdentity
    delegated_scopes: tuple[str, ...]
    parent_remaining_budget: DelegationBudget
    child_budget: DelegationBudget
    handoff_digest: str
    issued_at: float
    expires_at: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "delegation_id",
            _token(self.delegation_id, "delegation_id"),
        )
        if not isinstance(self.parent, AgentIdentity):
            raise AgentDelegationError("parent must be AgentIdentity")
        if not isinstance(self.child, AgentIdentity):
            raise AgentDelegationError("child must be AgentIdentity")
        if self.parent.agent_id == self.child.agent_id:
            raise AgentDelegationError("parent and child identities must differ")
        if self.parent.tenant_id != self.child.tenant_id:
            raise AgentDelegationError("delegation cannot cross tenant boundary")
        delegated = _scopes(self.delegated_scopes, "delegated_scopes")
        if not delegated:
            raise AgentDelegationError("delegated_scopes must not be empty")
        parent_scopes = set(self.parent.authority_scopes)
        child_scopes = set(self.child.authority_scopes)
        if not set(delegated).issubset(parent_scopes):
            raise AgentDelegationError(
                "delegated authority exceeds parent authority"
            )
        if not set(delegated).issubset(child_scopes):
            raise AgentDelegationError(
                "delegated authority exceeds child declared authority"
            )
        object.__setattr__(self, "delegated_scopes", delegated)
        if not isinstance(self.parent_remaining_budget, DelegationBudget):
            raise AgentDelegationError(
                "parent_remaining_budget must be DelegationBudget"
            )
        if not isinstance(self.child_budget, DelegationBudget):
            raise AgentDelegationError("child_budget must be DelegationBudget")
        if not self.parent_remaining_budget.contains(self.child_budget):
            raise AgentDelegationError(
                "child budget exceeds parent remaining budget"
            )
        object.__setattr__(
            self,
            "handoff_digest",
            _sha256(self.handoff_digest, "handoff_digest"),
        )
        issued = _nonnegative(self.issued_at, "issued_at")
        expires = _nonnegative(self.expires_at, "expires_at")
        if expires <= issued:
            raise AgentDelegationError("expires_at must follow issued_at")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)

    def payload(self) -> dict[str, Any]:
        return {
            "delegation_id": self.delegation_id,
            "parent": self.parent.payload(),
            "child": self.child.payload(),
            "delegated_scopes": list(self.delegated_scopes),
            "parent_remaining_budget": self.parent_remaining_budget.payload(),
            "child_budget": self.child_budget.payload(),
            "handoff_digest": self.handoff_digest,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class DelegationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    grant_digest: str
    handoff_digest: str
    fence_digest: str
    usage_digest: str
    checkpoint_persisted: bool
    task_id: str = AGENT_DELEGATION_TASK_ID
    accountability_id: str = AGENT_DELEGATION_ACCOUNTABILITY_ID
    schema_version: int = AGENT_DELEGATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.accepted, bool):
            raise AgentDelegationError("accepted must be boolean")
        if not isinstance(self.reasons, tuple) or any(
            not isinstance(reason, str) or not reason
            for reason in self.reasons
        ):
            raise AgentDelegationError("reasons must contain non-empty strings")
        for field in (
            "grant_digest",
            "handoff_digest",
            "fence_digest",
            "usage_digest",
        ):
            _sha256(getattr(self, field), field)
        if not isinstance(self.checkpoint_persisted, bool):
            raise AgentDelegationError(
                "checkpoint_persisted must be boolean"
            )
        if self.task_id != AGENT_DELEGATION_TASK_ID:
            raise AgentDelegationError("task_id drift")
        if self.accountability_id != AGENT_DELEGATION_ACCOUNTABILITY_ID:
            raise AgentDelegationError("accountability_id drift")
        if self.schema_version != AGENT_DELEGATION_SCHEMA_VERSION:
            raise AgentDelegationError("unsupported schema version")

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "grant_digest": self.grant_digest,
            "handoff_digest": self.handoff_digest,
            "fence_digest": self.fence_digest,
            "usage_digest": self.usage_digest,
            "checkpoint_persisted": self.checkpoint_persisted,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:auto-02:agent-delegation-handoff",
    ) -> EvidenceRef:
        if not self.accepted:
            raise AgentDelegationError(
                "rejected delegation cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_token(source, "source"),
            digest=self.decision_digest,
            category="agent_delegation",
        )


def qualify_agent_delegation(
    *,
    runtime: SwarmRuntime,
    grant: DelegationGrant,
    handoff: HandoffPacket,
    fence: LeaseFence,
    usage: DelegationUsage,
    observed_at: float,
    checkpoint_persisted: bool,
) -> DelegationDecision:
    """Qualify one child delegation against durable handoff and live lease."""

    if not isinstance(runtime, SwarmRuntime):
        raise TypeError("runtime must be SwarmRuntime")
    if not isinstance(grant, DelegationGrant):
        raise TypeError("grant must be DelegationGrant")
    if not isinstance(handoff, HandoffPacket):
        raise TypeError("handoff must be HandoffPacket")
    if not isinstance(fence, LeaseFence):
        raise TypeError("fence must be LeaseFence")
    if not isinstance(usage, DelegationUsage):
        raise TypeError("usage must be DelegationUsage")
    if not isinstance(checkpoint_persisted, bool):
        raise TypeError("checkpoint_persisted must be boolean")
    now = _nonnegative(observed_at, "observed_at")

    reasons: list[str] = []

    if handoff.delegation_id != grant.delegation_id:
        reasons.append("handoff-delegation-mismatch")
    if handoff.parent_agent_id != grant.parent.agent_id:
        reasons.append("handoff-parent-mismatch")
    if handoff.child_agent_id != grant.child.agent_id:
        reasons.append("handoff-child-mismatch")
    if handoff.digest != grant.handoff_digest:
        reasons.append("handoff-digest-mismatch")
    if not set(handoff.required_scopes).issubset(set(grant.delegated_scopes)):
        reasons.append("handoff-authority-exceeds-delegation")
    if handoff.created_at < grant.issued_at:
        reasons.append("handoff-predates-delegation")
    if handoff.created_at >= grant.expires_at:
        reasons.append("handoff-created-after-expiry")
    if now >= grant.expires_at:
        reasons.append("delegation-expired")
    if not usage.within(grant.child_budget):
        reasons.append("delegation-budget-exceeded")
    if not checkpoint_persisted:
        reasons.append("handoff-checkpoint-not-persisted")

    if fence.task_id != handoff.task_id:
        reasons.append("lease-task-mismatch")
    if fence.worker_id != grant.child.agent_id:
        reasons.append("lease-child-mismatch")
    if fence.deadline is None:
        reasons.append("lease-deadline-missing")
    elif not math.isfinite(fence.deadline):
        reasons.append("lease-deadline-invalid")
    elif now >= fence.deadline:
        reasons.append("lease-expired")

    try:
        assert_fence(runtime, fence)
    except LeaseError:
        reasons.append("lease-fence-stale")

    fence_digest = _canonical_digest(
        {
            "task_id": fence.task_id,
            "worker_id": fence.worker_id,
            "attempt": fence.attempt,
            "deadline": fence.deadline,
        }
    )

    return DelegationDecision(
        accepted=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        grant_digest=grant.digest,
        handoff_digest=handoff.digest,
        fence_digest=fence_digest,
        usage_digest=_canonical_digest(usage.payload()),
        checkpoint_persisted=checkpoint_persisted,
    )


__all__ = [
    "AGENT_DELEGATION_ACCOUNTABILITY_ID",
    "AGENT_DELEGATION_SCHEMA_VERSION",
    "AGENT_DELEGATION_TASK_ID",
    "AgentDelegationError",
    "AgentIdentity",
    "DelegationBudget",
    "DelegationDecision",
    "DelegationGrant",
    "DelegationUsage",
    "HandoffPacket",
    "qualify_agent_delegation",
]
