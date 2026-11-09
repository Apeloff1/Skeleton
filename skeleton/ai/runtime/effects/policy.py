"""Host-side policy and authorization providers for AI effects."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping, Protocol, Sequence
from uuid import NAMESPACE_URL, uuid5

from .contracts import EffectAuthorization, EffectProposal, ensure_aware


class EffectPolicyError(RuntimeError):
    pass


class AuthorizationProvider(Protocol):
    async def authorize(
        self, proposal: EffectProposal, *, subject_id: str, now: datetime
    ) -> EffectAuthorization: ...


@dataclass(frozen=True, slots=True)
class EffectPolicy:
    max_effects: int = 16
    max_timeout_ms: int = 120_000
    allowed_risk_classes: frozenset[str] = frozenset({"low", "medium", "high"})
    allowed_kinds: frozenset[str] | None = None
    require_postconditions: bool = True
    allow_irreversible: bool = False
    allow_irreversible_batch: bool = False

    def validate(self, proposals: Sequence[EffectProposal]) -> tuple[EffectProposal, ...]:
        items = tuple(proposals)
        if len(items) > self.max_effects:
            raise EffectPolicyError("effect budget exceeded")
        if len({p.proposal_id for p in items}) != len(items):
            raise EffectPolicyError("duplicate proposal_id")
        if len({p.idempotency_key for p in items}) != len(items):
            raise EffectPolicyError("duplicate idempotency_key in batch")
        for proposal in items:
            if proposal.timeout_ms > self.max_timeout_ms:
                raise EffectPolicyError("proposal timeout exceeds policy")
            if proposal.risk_class not in self.allowed_risk_classes:
                raise EffectPolicyError("risk class denied by policy")
            if self.allowed_kinds is not None and proposal.kind not in self.allowed_kinds:
                raise EffectPolicyError("effect kind denied by policy")
            if self.require_postconditions and not proposal.postconditions:
                raise EffectPolicyError("effect requires declared postconditions")
            if not proposal.reversible and not self.allow_irreversible:
                raise EffectPolicyError("irreversible effects denied by policy")
        irreversible = [p for p in items if not p.reversible]
        if len(items) > 1 and irreversible and not self.allow_irreversible_batch:
            raise EffectPolicyError("irreversible effects cannot share an atomic batch")
        return items


@dataclass(slots=True)
class DenyAllAuthorizer:
    policy_id: str = "effects.deny_all"
    ttl: timedelta = timedelta(minutes=5)

    async def authorize(self, proposal: EffectProposal, *, subject_id: str, now: datetime) -> EffectAuthorization:
        instant = ensure_aware(now, "now")
        return EffectAuthorization(
            authorization_id=str(uuid5(NAMESPACE_URL, f"deny:{proposal.digest}:{subject_id}")),
            proposal_digest=proposal.digest,
            subject_id=subject_id,
            decision="deny",
            capabilities=(),
            policy_id=self.policy_id,
            reason="default-deny effect boundary",
            issued_at=instant,
            expires_at=instant + self.ttl,
        )


@dataclass(slots=True)
class CapabilityAuthorizer:
    """Trusted host capability map; model output never populates it."""

    capabilities_by_subject: Mapping[str, frozenset[str]]
    policy_id: str = "effects.capability.v1"
    ttl: timedelta = timedelta(minutes=5)
    approval_refs_by_subject: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    async def authorize(self, proposal: EffectProposal, *, subject_id: str, now: datetime) -> EffectAuthorization:
        instant = ensure_aware(now, "now")
        caps = tuple(sorted(self.capabilities_by_subject.get(subject_id, frozenset())))
        allowed = proposal.required_capability in caps
        return EffectAuthorization(
            authorization_id=str(uuid5(NAMESPACE_URL, f"auth:{proposal.digest}:{subject_id}:{self.policy_id}")),
            proposal_digest=proposal.digest,
            subject_id=subject_id,
            decision="allow" if allowed else "deny",
            capabilities=caps,
            policy_id=self.policy_id,
            reason="required capability present" if allowed else "required capability absent",
            issued_at=instant,
            expires_at=instant + self.ttl,
            approval_refs=tuple(self.approval_refs_by_subject.get(subject_id, ())),
        )
