"""Bounded agent delegation, handoff, lease and fencing authority.

This module is a pure authorization contract layered over the existing swarm
runtime. It does not schedule work or execute tools. It proves that a child
agent's authority and resources are strict subsets of its parent's grant and
that only the current, unexpired lease holder may commit.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from skeleton.contracts.canonical import EvidenceRef
from skeleton.agents.swarm_fencing import LeaseFence, assert_fence
from skeleton.agents.swarm_runtime import LeaseError, SwarmRuntime


DELEGATION_SCHEMA_VERSION = 1
MAX_CAPABILITIES = 128
MAX_HANDOFF_REFS = 128
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DelegationContractError(ValueError):
    """Delegation input or authority proof is malformed."""


def _text(value: object, field: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value:
        raise DelegationContractError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise DelegationContractError(f"{field} must be normalized")
    if len(value) > max_length:
        raise DelegationContractError(f"{field} exceeds maximum length")
    return value


def _identifier(value: object, field: str) -> str:
    text = _text(value, field)
    if not _ID_RE.fullmatch(text):
        raise DelegationContractError(f"{field} must be a canonical identifier")
    return text


def _positive_int(value: object, field: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DelegationContractError(f"{field} must be an integer")
    floor = 0 if allow_zero else 1
    if value < floor:
        raise DelegationContractError(f"{field} must be >= {floor}")
    return value


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DelegationContractError(f"{field} must be numeric")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise DelegationContractError(f"{field} must be finite and non-negative")
    return normalized


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise DelegationContractError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _capabilities(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise DelegationContractError(f"{field} must be an iterable")
    normalized = sorted({_identifier(item, field) for item in values})
    if not normalized:
        raise DelegationContractError(f"{field} must be non-empty")
    if len(normalized) > MAX_CAPABILITIES:
        raise DelegationContractError(f"{field} exceeds capability budget")
    return tuple(normalized)


def _sha256(value: object, field: str) -> str:
    text = _text(value, field, max_length=64)
    if not _SHA256_RE.fullmatch(text):
        raise DelegationContractError(f"{field} must be lowercase sha256")
    return text


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    agent_id: str
    principal_id: str
    tenant_id: str
    capabilities: tuple[str, ...]
    schema_version: int = DELEGATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", _identifier(self.agent_id, "agent_id"))
        object.__setattr__(
            self,
            "principal_id",
            _identifier(self.principal_id, "principal_id"),
        )
        object.__setattr__(self, "tenant_id", _identifier(self.tenant_id, "tenant_id"))
        object.__setattr__(
            self,
            "capabilities",
            _capabilities(self.capabilities, "capabilities"),
        )
        if self.schema_version != DELEGATION_SCHEMA_VERSION:
            raise DelegationContractError("unsupported delegation schema version")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "agent_id": self.agent_id,
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "capabilities": list(self.capabilities),
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class DelegationBudget:
    max_steps: int
    max_tokens: int
    max_cost_micros: int
    max_wall_seconds: float
    max_tool_calls: int
    max_delegation_depth: int

    def __post_init__(self) -> None:
        for field in ("max_steps", "max_tokens", "max_cost_micros", "max_tool_calls"):
            object.__setattr__(
                self,
                field,
                _positive_int(getattr(self, field), field),
            )
        object.__setattr__(
            self,
            "max_delegation_depth",
            _positive_int(
                self.max_delegation_depth,
                "max_delegation_depth",
                allow_zero=True,
            ),
        )
        object.__setattr__(
            self,
            "max_wall_seconds",
            _finite_nonnegative(self.max_wall_seconds, "max_wall_seconds"),
        )
        if self.max_wall_seconds <= 0:
            raise DelegationContractError("max_wall_seconds must be positive")

    def is_subset_of(self, parent: "DelegationBudget") -> bool:
        return (
            self.max_steps <= parent.max_steps
            and self.max_tokens <= parent.max_tokens
            and self.max_cost_micros <= parent.max_cost_micros
            and self.max_wall_seconds <= parent.max_wall_seconds
            and self.max_tool_calls <= parent.max_tool_calls
            and self.max_delegation_depth <= parent.max_delegation_depth
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
            "max_cost_micros": self.max_cost_micros,
            "max_wall_seconds": self.max_wall_seconds,
            "max_tool_calls": self.max_tool_calls,
            "max_delegation_depth": self.max_delegation_depth,
        }


@dataclass(frozen=True, slots=True)
class DelegationUsage:
    steps: int = 0
    tokens: int = 0
    cost_micros: int = 0
    wall_seconds: float = 0.0
    tool_calls: int = 0

    def __post_init__(self) -> None:
        for field in ("steps", "tokens", "cost_micros", "tool_calls"):
            object.__setattr__(
                self,
                field,
                _positive_int(getattr(self, field), field, allow_zero=True),
            )
        object.__setattr__(
            self,
            "wall_seconds",
            _finite_nonnegative(self.wall_seconds, "wall_seconds"),
        )

    def within(self, budget: DelegationBudget) -> bool:
        return (
            self.steps <= budget.max_steps
            and self.tokens <= budget.max_tokens
            and self.cost_micros <= budget.max_cost_micros
            and self.wall_seconds <= budget.max_wall_seconds
            and self.tool_calls <= budget.max_tool_calls
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "steps": self.steps,
            "tokens": self.tokens,
            "cost_micros": self.cost_micros,
            "wall_seconds": self.wall_seconds,
            "tool_calls": self.tool_calls,
        }


@dataclass(frozen=True, slots=True)
class HandoffPacket:
    operation_id: str
    objective_digest: str
    context_digest: str
    state_refs: tuple[str, ...]
    checkpoint_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _identifier(self.operation_id, "operation_id"),
        )
        object.__setattr__(
            self,
            "objective_digest",
            _sha256(self.objective_digest, "objective_digest"),
        )
        object.__setattr__(
            self,
            "context_digest",
            _sha256(self.context_digest, "context_digest"),
        )
        if isinstance(self.state_refs, (str, bytes)):
            raise DelegationContractError("state_refs must be an iterable")
        refs = tuple(sorted({_identifier(item, "state_ref") for item in self.state_refs}))
        if not refs:
            raise DelegationContractError("state_refs must be non-empty")
        if len(refs) > MAX_HANDOFF_REFS:
            raise DelegationContractError("state_refs exceed reference budget")
        object.__setattr__(self, "state_refs", refs)
        if self.checkpoint_digest is not None:
            object.__setattr__(
                self,
                "checkpoint_digest",
                _sha256(self.checkpoint_digest, "checkpoint_digest"),
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "objective_digest": self.objective_digest,
            "context_digest": self.context_digest,
            "state_refs": list(self.state_refs),
            "checkpoint_digest": self.checkpoint_digest,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class DelegationGrant:
    delegation_id: str
    lease_task_id: str
    parent: AgentIdentity
    child: AgentIdentity
    parent_budget: DelegationBudget
    budget: DelegationBudget
    handoff: HandoffPacket
    issued_at: datetime
    expires_at: datetime
    lease_epoch: int
    delegation_depth: int
    task_id: str = "P1-AUTO-02"
    accountability_id: str = "ACC-P1-AUTO-02"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "delegation_id",
            _identifier(self.delegation_id, "delegation_id"),
        )
        object.__setattr__(
            self,
            "lease_task_id",
            _identifier(self.lease_task_id, "lease_task_id"),
        )
        if not isinstance(self.parent, AgentIdentity) or not isinstance(
            self.child, AgentIdentity
        ):
            raise DelegationContractError("parent and child must be AgentIdentity")
        if self.parent.agent_id == self.child.agent_id:
            raise DelegationContractError("parent and child agent identity must differ")
        if self.parent.tenant_id != self.child.tenant_id:
            raise DelegationContractError("delegation cannot cross tenant boundary")
        parent_caps = set(self.parent.capabilities)
        child_caps = set(self.child.capabilities)
        if not child_caps.issubset(parent_caps):
            raise DelegationContractError("child capabilities exceed parent authority")
        if not isinstance(self.parent_budget, DelegationBudget) or not isinstance(
            self.budget, DelegationBudget
        ):
            raise DelegationContractError("delegation budgets are malformed")
        if not self.budget.is_subset_of(self.parent_budget):
            raise DelegationContractError("child budget exceeds parent budget")
        if not isinstance(self.handoff, HandoffPacket):
            raise DelegationContractError("handoff must be HandoffPacket")
        issued = _utc(self.issued_at, "issued_at")
        expires = _utc(self.expires_at, "expires_at")
        if expires <= issued:
            raise DelegationContractError("expires_at must follow issued_at")
        if (expires - issued).total_seconds() > self.budget.max_wall_seconds:
            raise DelegationContractError("lease duration exceeds delegated wall budget")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(
            self,
            "lease_epoch",
            _positive_int(self.lease_epoch, "lease_epoch"),
        )
        object.__setattr__(
            self,
            "delegation_depth",
            _positive_int(
                self.delegation_depth,
                "delegation_depth",
            ),
        )
        if self.delegation_depth > self.budget.max_delegation_depth:
            raise DelegationContractError("delegation depth exceeds delegated budget")
        object.__setattr__(self, "task_id", _identifier(self.task_id, "task_id"))
        object.__setattr__(
            self,
            "accountability_id",
            _identifier(self.accountability_id, "accountability_id"),
        )

    def authority_payload(self) -> dict[str, Any]:
        return {
            "schema_version": DELEGATION_SCHEMA_VERSION,
            "delegation_id": self.delegation_id,
            "lease_task_id": self.lease_task_id,
            "parent": self.parent.as_dict(),
            "child": self.child.as_dict(),
            "parent_budget": self.parent_budget.as_dict(),
            "budget": self.budget.as_dict(),
            "handoff_digest": self.handoff.digest,
            "issued_at": self.issued_at.isoformat().replace("+00:00", "Z"),
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "lease_epoch": self.lease_epoch,
            "delegation_depth": self.delegation_depth,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
        }

    @property
    def digest(self) -> str:
        return _digest(self.authority_payload())

    @property
    def fencing_token(self) -> str:
        return _digest(
            {
                "delegation_digest": self.digest,
                "lease_epoch": self.lease_epoch,
                "child_agent_id": self.child.agent_id,
            }
        )


@dataclass(frozen=True, slots=True)
class DelegationCommitDecision:
    accepted: bool
    reason: str
    delegation_digest: str
    handoff_digest: str
    child_agent_id: str
    lease_epoch: int
    fencing_token: str
    usage: DelegationUsage
    required_capability: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "delegation_digest": self.delegation_digest,
            "handoff_digest": self.handoff_digest,
            "child_agent_id": self.child_agent_id,
            "lease_epoch": self.lease_epoch,
            "fencing_token": self.fencing_token,
            "usage": self.usage.as_dict(),
            "required_capability": self.required_capability,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())

    def accepted_evidence_ref(self) -> EvidenceRef:
        if not self.accepted:
            raise DelegationContractError(
                "rejected delegation decision cannot become promotion evidence"
            )
        return EvidenceRef(
            source=f"p1:auto-02:{self.child_agent_id}",
            digest=self.digest,
            category="agent_delegation_authority",
        )



def derive_child_grant(
    parent_grant: DelegationGrant,
    *,
    delegation_id: str,
    lease_task_id: str,
    child: AgentIdentity,
    budget: DelegationBudget,
    handoff: HandoffPacket,
    issued_at: datetime,
    expires_at: datetime,
    lease_epoch: int,
) -> DelegationGrant:
    """Derive one narrower descendant grant with monotonic delegation depth."""

    if not isinstance(parent_grant, DelegationGrant):
        raise DelegationContractError("parent_grant must be DelegationGrant")
    next_depth = parent_grant.delegation_depth + 1
    if next_depth > parent_grant.budget.max_delegation_depth:
        raise DelegationContractError("delegation depth exhausted")
    return DelegationGrant(
        delegation_id=delegation_id,
        lease_task_id=lease_task_id,
        parent=parent_grant.child,
        child=child,
        parent_budget=parent_grant.budget,
        budget=budget,
        handoff=handoff,
        issued_at=issued_at,
        expires_at=expires_at,
        lease_epoch=lease_epoch,
        delegation_depth=next_depth,
    )

def authorize_child_commit(
    grant: DelegationGrant,
    *,
    child_agent_id: str,
    presented_task_id: str,
    presented_epoch: int,
    presented_fencing_token: str,
    handoff_digest: str,
    usage: DelegationUsage,
    required_capability: str,
    now: datetime,
) -> DelegationCommitDecision:
    """Return an exact delegation decision without mutating runtime state."""

    if not isinstance(grant, DelegationGrant):
        raise DelegationContractError("grant must be DelegationGrant")
    child = _identifier(child_agent_id, "child_agent_id")
    task = _identifier(presented_task_id, "presented_task_id")
    epoch = _positive_int(presented_epoch, "presented_epoch")
    fence = _sha256(presented_fencing_token, "presented_fencing_token")
    handoff = _sha256(handoff_digest, "handoff_digest")
    capability = _identifier(required_capability, "required_capability")
    observed_at = _utc(now, "now")
    if not isinstance(usage, DelegationUsage):
        raise DelegationContractError("usage must be DelegationUsage")

    accepted = True
    reason = "authorized"
    if child != grant.child.agent_id:
        accepted = False
        reason = "child identity mismatch"
    elif task != grant.lease_task_id:
        accepted = False
        reason = "lease task mismatch"
    elif epoch != grant.lease_epoch:
        accepted = False
        reason = "stale lease epoch"
    elif fence != grant.fencing_token:
        accepted = False
        reason = "fencing token mismatch"
    elif observed_at < grant.issued_at:
        accepted = False
        reason = "lease not yet valid"
    elif observed_at >= grant.expires_at:
        accepted = False
        reason = "lease expired"
    elif handoff != grant.handoff.digest:
        accepted = False
        reason = "handoff digest mismatch"
    elif capability not in grant.child.capabilities:
        accepted = False
        reason = "required capability not delegated"
    elif not usage.within(grant.budget):
        accepted = False
        reason = "delegation budget exceeded"

    return DelegationCommitDecision(
        accepted=accepted,
        reason=reason,
        delegation_digest=grant.digest,
        handoff_digest=grant.handoff.digest,
        child_agent_id=child,
        lease_epoch=epoch,
        fencing_token=fence,
        usage=usage,
        required_capability=capability,
    )

def authorize_swarm_child_commit(
    runtime: SwarmRuntime,
    fence: LeaseFence,
    grant: DelegationGrant,
    *,
    usage: DelegationUsage,
    required_capability: str,
    now: datetime,
) -> DelegationCommitDecision:
    """Bind AUTO-02 authority to the live swarm lease/fence without mutation."""

    if not isinstance(runtime, SwarmRuntime):
        raise DelegationContractError("runtime must be SwarmRuntime")
    if not isinstance(fence, LeaseFence):
        raise DelegationContractError("fence must be LeaseFence")
    if not isinstance(grant, DelegationGrant):
        raise DelegationContractError("grant must be DelegationGrant")

    try:
        assert_fence(runtime, fence)
    except LeaseError:
        return DelegationCommitDecision(
            accepted=False,
            reason="runtime lease fence rejected",
            delegation_digest=grant.digest,
            handoff_digest=grant.handoff.digest,
            child_agent_id=fence.worker_id,
            lease_epoch=fence.attempt,
            fencing_token=grant.fencing_token,
            usage=usage,
            required_capability=_identifier(
                required_capability,
                "required_capability",
            ),
        )

    now_mono = runtime._clock()
    if fence.deadline is not None and now_mono >= fence.deadline:
        return DelegationCommitDecision(
            accepted=False,
            reason="runtime lease expired",
            delegation_digest=grant.digest,
            handoff_digest=grant.handoff.digest,
            child_agent_id=fence.worker_id,
            lease_epoch=fence.attempt,
            fencing_token=grant.fencing_token,
            usage=usage,
            required_capability=_identifier(
                required_capability,
                "required_capability",
            ),
        )

    return authorize_child_commit(
        grant,
        child_agent_id=fence.worker_id,
        presented_task_id=fence.task_id,
        presented_epoch=fence.attempt,
        presented_fencing_token=grant.fencing_token,
        handoff_digest=grant.handoff.digest,
        usage=usage,
        required_capability=required_capability,
        now=now,
    )

