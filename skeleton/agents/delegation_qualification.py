"""Fail-closed P1 agent handoff and delegation qualification.

This module composes existing handoff and lease-fencing primitives.  It does
not schedule agents, create leases, or grant authority.  It proves that an
already-created handoff is within an explicit parent delegation and that the
assignee still owns the exact live lease generation before the handoff may be
treated as qualified P1 evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Iterable

from skeleton.agents.swarm_fencing import LeaseFence
from skeleton.contracts.canonical import EvidenceRef
from skeleton.swarm.handoff import TaskEnvelope, TaskState


AGENT_DELEGATION_SCHEMA_VERSION = 1
AGENT_DELEGATION_TASK_ID = "P1-AUTO-02"
AGENT_DELEGATION_ACCOUNTABILITY_ID = "ACC-P1-AUTO-02"
_MAX_AUTHORITY_ITEMS = 256
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class AgentDelegationError(ValueError):
    """Agent delegation or handoff evidence is malformed."""


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not _TOKEN_RE.fullmatch(value):
        raise AgentDelegationError(f"{field} must be a canonical token")
    return value


def _finite(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AgentDelegationError(f"{field} must be finite numeric")
    result = float(value)
    if not math.isfinite(result):
        raise AgentDelegationError(f"{field} must be finite numeric")
    return result


def _positive(value: object, field: str) -> float:
    result = _finite(value, field)
    if result <= 0.0:
        raise AgentDelegationError(f"{field} must be positive")
    return result


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AgentDelegationError(f"{field} must be a positive integer")
    return value


def _tokens(values: Iterable[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise AgentDelegationError(f"{field} must be an iterable")
    normalized: set[str] = set()
    for raw in values:
        normalized.add(_token(raw, field))
        if len(normalized) > _MAX_AUTHORITY_ITEMS:
            raise AgentDelegationError(f"{field} exceeds item limit")
    if not normalized:
        raise AgentDelegationError(f"{field} must be non-empty")
    return tuple(sorted(normalized))


def _canonical_digest(value: Any) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AgentDelegationError(
            "handoff payload must be canonical JSON"
        ) from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class DelegationBudget:
    max_parallel_tasks: int
    max_steps: int
    max_tokens: int
    max_cost_units: float
    max_wall_time_s: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_parallel_tasks",
            _positive_int(self.max_parallel_tasks, "max_parallel_tasks"),
        )
        object.__setattr__(
            self,
            "max_steps",
            _positive_int(self.max_steps, "max_steps"),
        )
        object.__setattr__(
            self,
            "max_tokens",
            _positive_int(self.max_tokens, "max_tokens"),
        )
        object.__setattr__(
            self,
            "max_cost_units",
            _positive(self.max_cost_units, "max_cost_units"),
        )
        object.__setattr__(
            self,
            "max_wall_time_s",
            _positive(self.max_wall_time_s, "max_wall_time_s"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "max_parallel_tasks": self.max_parallel_tasks,
            "max_steps": self.max_steps,
            "max_tokens": self.max_tokens,
            "max_cost_units": self.max_cost_units,
            "max_wall_time_s": self.max_wall_time_s,
        }

    def within(self, parent: "DelegationBudget") -> bool:
        if not isinstance(parent, DelegationBudget):
            raise TypeError("parent must be DelegationBudget")
        return (
            self.max_parallel_tasks <= parent.max_parallel_tasks
            and self.max_steps <= parent.max_steps
            and self.max_tokens <= parent.max_tokens
            and self.max_cost_units <= parent.max_cost_units
            and self.max_wall_time_s <= parent.max_wall_time_s
        )


@dataclass(frozen=True, slots=True)
class AgentDelegationAuthority:
    agent_id: str
    parent_agent_id: str | None
    generation: int
    capabilities: tuple[str, ...]
    scopes: tuple[str, ...]
    budget: DelegationBudget
    expires_at: float
    delegation_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", _token(self.agent_id, "agent_id"))
        if self.parent_agent_id is not None:
            object.__setattr__(
                self,
                "parent_agent_id",
                _token(self.parent_agent_id, "parent_agent_id"),
            )
            if self.parent_agent_id == self.agent_id:
                raise AgentDelegationError(
                    "agent cannot delegate authority to itself"
                )
        object.__setattr__(
            self,
            "generation",
            _positive_int(self.generation, "generation"),
        )
        object.__setattr__(
            self,
            "capabilities",
            _tokens(self.capabilities, "capabilities"),
        )
        object.__setattr__(self, "scopes", _tokens(self.scopes, "scopes"))
        if not isinstance(self.budget, DelegationBudget):
            raise AgentDelegationError("budget must be DelegationBudget")
        expiry = _positive(self.expires_at, "expires_at")
        object.__setattr__(self, "expires_at", expiry)
        object.__setattr__(
            self,
            "delegation_id",
            _token(self.delegation_id, "delegation_id"),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "parent_agent_id": self.parent_agent_id,
            "generation": self.generation,
            "capabilities": list(self.capabilities),
            "scopes": list(self.scopes),
            "budget": self.budget.payload(),
            "expires_at": self.expires_at,
            "delegation_id": self.delegation_id,
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class AgentDelegationDecision:
    accepted: bool
    reasons: tuple[str, ...]
    parent_authority_digest: str
    child_authority_digest: str
    handoff_digest: str
    lease_fence_digest: str
    observed_at: float
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
            raise AgentDelegationError(
                "reasons must contain non-empty strings"
            )
        for field in (
            "parent_authority_digest",
            "child_authority_digest",
            "handoff_digest",
            "lease_fence_digest",
        ):
            value = getattr(self, field)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise AgentDelegationError(
                    f"{field} must be lowercase sha256"
                )
        observed = _positive(self.observed_at, "observed_at")
        object.__setattr__(self, "observed_at", observed)
        if self.task_id != AGENT_DELEGATION_TASK_ID:
            raise AgentDelegationError("task_id drift")
        if self.accountability_id != AGENT_DELEGATION_ACCOUNTABILITY_ID:
            raise AgentDelegationError("accountability_id drift")
        if self.schema_version != AGENT_DELEGATION_SCHEMA_VERSION:
            raise AgentDelegationError("unsupported schema version")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "accountability_id": self.accountability_id,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "parent_authority_digest": self.parent_authority_digest,
            "child_authority_digest": self.child_authority_digest,
            "handoff_digest": self.handoff_digest,
            "lease_fence_digest": self.lease_fence_digest,
        }

    def payload(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "observed_at": self.observed_at,
        }

    @property
    def decision_digest(self) -> str:
        return _canonical_digest(self.identity_payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:auto-02:agent-delegation-qualification",
    ) -> EvidenceRef:
        if not self.accepted:
            raise AgentDelegationError(
                "rejected delegation decision cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_token(source, "source"),
            digest=self.decision_digest,
            category="agent_delegation_qualification",
        )


def _handoff_payload(envelope: TaskEnvelope) -> dict[str, Any]:
    if not isinstance(envelope, TaskEnvelope):
        raise TypeError("envelope must be TaskEnvelope")
    return {
        "task_id": _token(envelope.task_id, "handoff task_id"),
        "capability": _token(envelope.capability, "handoff capability"),
        "input": envelope.input,
        "requester": _token(envelope.requester, "handoff requester"),
        "state": envelope.state.value,
        "assignee": (
            None
            if envelope.assignee is None
            else _token(envelope.assignee, "handoff assignee")
        ),
        "artefacts": envelope.artefacts,
        "error": envelope.error,
        "created_at": _finite(envelope.created_at, "handoff created_at"),
        "updated_at": _finite(envelope.updated_at, "handoff updated_at"),
    }


def _fence_payload(fence: LeaseFence) -> dict[str, Any]:
    if not isinstance(fence, LeaseFence):
        raise TypeError("fence must be LeaseFence")
    deadline = (
        None
        if fence.deadline is None
        else _finite(fence.deadline, "lease deadline")
    )
    return {
        "task_id": _token(fence.task_id, "lease task_id"),
        "worker_id": _token(fence.worker_id, "lease worker_id"),
        "attempt": _positive_int(fence.attempt, "lease attempt"),
        "deadline": deadline,
    }


def qualify_agent_delegation(
    *,
    parent: AgentDelegationAuthority,
    child: AgentDelegationAuthority,
    envelope: TaskEnvelope,
    fence: LeaseFence,
    observed_at: float,
) -> AgentDelegationDecision:
    """Qualify one accepted agent handoff against exact delegated authority."""

    if not isinstance(parent, AgentDelegationAuthority):
        raise TypeError("parent must be AgentDelegationAuthority")
    if not isinstance(child, AgentDelegationAuthority):
        raise TypeError("child must be AgentDelegationAuthority")
    now = _positive(observed_at, "observed_at")
    handoff = _handoff_payload(envelope)
    fence_payload = _fence_payload(fence)

    reasons: list[str] = []

    if child.parent_agent_id != parent.agent_id:
        reasons.append("parent-identity-mismatch")
    if child.agent_id == parent.agent_id:
        reasons.append("delegation-self-cycle")
    if child.generation <= parent.generation:
        reasons.append("delegation-generation-not-descending")
    if child.expires_at > parent.expires_at:
        reasons.append("child-expiry-exceeds-parent")
    if now > parent.expires_at:
        reasons.append("parent-authority-expired")
    if now > child.expires_at:
        reasons.append("child-authority-expired")
    if not set(child.capabilities).issubset(parent.capabilities):
        reasons.append("child-capability-authority-widened")
    if not set(child.scopes).issubset(parent.scopes):
        reasons.append("child-scope-authority-widened")
    if not child.budget.within(parent.budget):
        reasons.append("child-budget-authority-widened")

    if envelope.state is not TaskState.WORKING:
        reasons.append("handoff-not-working")
    if envelope.requester != parent.agent_id:
        reasons.append("handoff-requester-mismatch")
    if envelope.assignee != child.agent_id:
        reasons.append("handoff-assignee-mismatch")
    if envelope.capability not in child.capabilities:
        reasons.append("handoff-capability-not-delegated")
    if envelope.capability not in parent.capabilities:
        reasons.append("handoff-capability-not-parent-authorized")

    if fence.task_id != envelope.task_id:
        reasons.append("lease-task-mismatch")
    if fence.worker_id != child.agent_id:
        reasons.append("lease-worker-mismatch")
    if fence.attempt < 1:
        reasons.append("lease-attempt-invalid")
    if fence.deadline is None:
        reasons.append("lease-deadline-missing")
    elif now >= fence.deadline:
        reasons.append("lease-expired")
    if envelope.updated_at > now:
        reasons.append("handoff-future-dated")
    if envelope.created_at > envelope.updated_at:
        reasons.append("handoff-time-order-invalid")

    normalized_reasons = tuple(sorted(set(reasons)))
    return AgentDelegationDecision(
        accepted=not normalized_reasons,
        reasons=normalized_reasons,
        parent_authority_digest=parent.digest,
        child_authority_digest=child.digest,
        handoff_digest=_canonical_digest(handoff),
        lease_fence_digest=_canonical_digest(fence_payload),
        observed_at=now,
    )


__all__ = [
    "AGENT_DELEGATION_ACCOUNTABILITY_ID",
    "AGENT_DELEGATION_SCHEMA_VERSION",
    "AGENT_DELEGATION_TASK_ID",
    "AgentDelegationAuthority",
    "AgentDelegationDecision",
    "AgentDelegationError",
    "DelegationBudget",
    "qualify_agent_delegation",
]
