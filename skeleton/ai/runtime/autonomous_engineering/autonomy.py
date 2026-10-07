"""Bounded, evidence-driven autonomy control for P3 engineering agents."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import IntEnum
import hashlib
import json
from typing import Iterable

from .safe_change import SafeChangePlan


class AutonomyLevel(IntEnum):
    OBSERVE = 0
    PLAN = 1
    READ = 2
    WRITE = 3
    EXTERNAL = 4


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _id(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    text = value.strip()
    if not text or len(text) > 192:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


def _refs(values: Iterable[str], field: str, *, required: bool = False) -> tuple[str, ...]:
    refs = tuple(sorted({_id(value, field) for value in values}))
    if required and not refs:
        raise ValueError(f"{field} requires evidence")
    if len(refs) > 64:
        raise ValueError(f"{field} exceeds maximum references")
    return refs


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class AutonomyGrant:
    grant_id: str
    actor_id: str
    max_level: AutonomyLevel
    capabilities: tuple[str, ...]
    max_actions: int
    max_risk_score: int
    issued_at: datetime
    expires_at: datetime
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "grant_id", _id(self.grant_id, "grant_id"))
        object.__setattr__(self, "actor_id", _id(self.actor_id, "actor_id"))
        if not isinstance(self.max_level, AutonomyLevel):
            raise TypeError("max_level must be AutonomyLevel")
        caps = tuple(sorted({_id(item, "capability") for item in self.capabilities}))
        if not caps:
            raise ValueError("autonomy grant requires capabilities")
        object.__setattr__(self, "capabilities", caps)
        if (
            isinstance(self.max_actions, bool)
            or not isinstance(self.max_actions, int)
            or not 1 <= self.max_actions <= 10000
        ):
            raise ValueError("max_actions must be integer in [1,10000]")
        if (
            isinstance(self.max_risk_score, bool)
            or not isinstance(self.max_risk_score, int)
            or not 0 <= self.max_risk_score <= 100
        ):
            raise ValueError("max_risk_score must be integer in [0,100]")
        issued = _utc(self.issued_at, "issued_at")
        expires = _utc(self.expires_at, "expires_at")
        if expires <= issued:
            raise ValueError("autonomy grant must expire after issuance")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "grant_evidence_ref", required=True),
        )


@dataclass(frozen=True, slots=True)
class AutonomyState:
    actor_id: str
    level: AutonomyLevel = AutonomyLevel.OBSERVE
    actions_used: int = 0
    revision: int = 0
    revoked: bool = False
    last_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor_id", _id(self.actor_id, "actor_id"))
        if not isinstance(self.level, AutonomyLevel):
            raise TypeError("level must be AutonomyLevel")
        for field in ("actions_used", "revision"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field} must be non-negative integer")
        if not isinstance(self.revoked, bool):
            raise TypeError("revoked must be boolean")
        if self.last_receipt_digest is not None:
            digest = self.last_receipt_digest
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("last_receipt_digest must be lowercase sha256")


@dataclass(frozen=True, slots=True)
class AutonomyDecision:
    permitted: bool
    reason_code: str
    actor_id: str
    grant_id: str
    required_level: AutonomyLevel
    current_level: AutonomyLevel
    capability: str
    risk_score: int
    actions_before: int
    actions_after: int
    state_revision: int
    evidence_refs: tuple[str, ...]
    receipt_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.permitted, bool):
            raise TypeError("permitted must be boolean")
        if not 0 <= self.risk_score <= 100:
            raise ValueError("risk_score must be in [0,100]")
        if self.actions_after < self.actions_before:
            raise ValueError("actions_after cannot decrease")
        if len(self.receipt_digest) != 64:
            raise ValueError("receipt_digest must be sha256")


def _require_binding(grant: AutonomyGrant, state: AutonomyState) -> None:
    if grant.actor_id != state.actor_id:
        raise ValueError("grant/state actor mismatch")


def _transition_receipt(
    *,
    event: str,
    grant: AutonomyGrant,
    before: AutonomyState,
    after: AutonomyState,
    evidence_refs: tuple[str, ...],
    target_level: AutonomyLevel,
) -> str:
    return _digest(
        {
            "event": event,
            "grant_id": grant.grant_id,
            "actor_id": grant.actor_id,
            "before_level": before.level.name,
            "after_level": after.level.name,
            "before_revision": before.revision,
            "after_revision": after.revision,
            "actions_used": after.actions_used,
            "target_level": target_level.name,
            "evidence_refs": list(evidence_refs),
        }
    )


def escalate(
    grant: AutonomyGrant,
    state: AutonomyState,
    *,
    target_level: AutonomyLevel,
    evidence_refs: Iterable[str],
    operator_approval_ref: str | None = None,
) -> AutonomyState:
    """Escalate only within the grant and with evidence/approval for effects."""

    _require_binding(grant, state)
    if state.revoked:
        raise PermissionError("autonomy state is revoked")
    if not isinstance(target_level, AutonomyLevel):
        raise TypeError("target_level must be AutonomyLevel")
    if target_level <= state.level:
        raise ValueError("escalation target must exceed current level")
    if target_level > grant.max_level:
        raise PermissionError("escalation exceeds grant maximum")
    refs = list(_refs(evidence_refs, "escalation_evidence_ref", required=True))
    if target_level >= AutonomyLevel.WRITE:
        if operator_approval_ref is None:
            raise PermissionError("write/external escalation requires operator approval")
        refs.append(_id(operator_approval_ref, "operator_approval_ref"))
    normalized = tuple(sorted(set(refs)))
    after = replace(
        state,
        level=target_level,
        revision=state.revision + 1,
    )
    receipt = _transition_receipt(
        event="escalate",
        grant=grant,
        before=state,
        after=after,
        evidence_refs=normalized,
        target_level=target_level,
    )
    return replace(after, last_receipt_digest=receipt)


def deescalate(
    grant: AutonomyGrant,
    state: AutonomyState,
    *,
    target_level: AutonomyLevel = AutonomyLevel.OBSERVE,
    evidence_refs: Iterable[str] = (),
) -> AutonomyState:
    _require_binding(grant, state)
    if not isinstance(target_level, AutonomyLevel):
        raise TypeError("target_level must be AutonomyLevel")
    if target_level >= state.level:
        raise ValueError("deescalation target must be below current level")
    refs = _refs(evidence_refs, "deescalation_evidence_ref")
    after = replace(state, level=target_level, revision=state.revision + 1)
    receipt = _transition_receipt(
        event="deescalate",
        grant=grant,
        before=state,
        after=after,
        evidence_refs=refs,
        target_level=target_level,
    )
    return replace(after, last_receipt_digest=receipt)


def revoke(
    grant: AutonomyGrant,
    state: AutonomyState,
    *,
    evidence_refs: Iterable[str],
) -> AutonomyState:
    _require_binding(grant, state)
    refs = _refs(evidence_refs, "revocation_evidence_ref", required=True)
    after = replace(
        state,
        level=AutonomyLevel.OBSERVE,
        revoked=True,
        revision=state.revision + 1,
    )
    receipt = _transition_receipt(
        event="revoke",
        grant=grant,
        before=state,
        after=after,
        evidence_refs=refs,
        target_level=AutonomyLevel.OBSERVE,
    )
    return replace(after, last_receipt_digest=receipt)


def authorize_change_plan(
    grant: AutonomyGrant,
    state: AutonomyState,
    plan: SafeChangePlan,
    *,
    capability: str = "repo.write",
    now: datetime,
    evidence_refs: Iterable[str] = (),
) -> tuple[AutonomyDecision, AutonomyState]:
    """Consume one bounded action budget if a safe-change plan is authorized."""

    _require_binding(grant, state)
    instant = _utc(now, "now")
    cap = _id(capability, "capability")
    refs = _refs(evidence_refs, "authorization_evidence_ref")
    required = AutonomyLevel.WRITE
    reason = "permitted"
    permitted = True

    if state.revoked:
        permitted, reason = False, "state_revoked"
    elif instant < grant.issued_at:
        permitted, reason = False, "grant_not_yet_valid"
    elif instant >= grant.expires_at:
        permitted, reason = False, "grant_expired"
    elif state.level < required:
        permitted, reason = False, "insufficient_autonomy_level"
    elif state.level > grant.max_level:
        permitted, reason = False, "state_exceeds_grant"
    elif cap not in grant.capabilities:
        permitted, reason = False, "capability_not_granted"
    elif state.actions_used >= grant.max_actions:
        permitted, reason = False, "action_budget_exhausted"
    elif plan.risk_score > grant.max_risk_score:
        permitted, reason = False, "risk_budget_exceeded"
    elif plan.author_id != state.actor_id:
        permitted, reason = False, "plan_actor_mismatch"
    elif "operator-approval" not in plan.required_gates:
        permitted, reason = False, "plan_missing_operator_approval_gate"

    actions_after = state.actions_used + (1 if permitted else 0)
    revision = state.revision + (1 if permitted else 0)
    material = {
        "permitted": permitted,
        "reason_code": reason,
        "actor_id": state.actor_id,
        "grant_id": grant.grant_id,
        "required_level": required.name,
        "current_level": state.level.name,
        "capability": cap,
        "risk_score": plan.risk_score,
        "actions_before": state.actions_used,
        "actions_after": actions_after,
        "state_revision": revision,
        "plan_digest": plan.plan_digest,
        "evidence_refs": list(refs),
        "at": instant.isoformat(),
    }
    decision = AutonomyDecision(
        permitted=permitted,
        reason_code=reason,
        actor_id=state.actor_id,
        grant_id=grant.grant_id,
        required_level=required,
        current_level=state.level,
        capability=cap,
        risk_score=plan.risk_score,
        actions_before=state.actions_used,
        actions_after=actions_after,
        state_revision=revision,
        evidence_refs=refs,
        receipt_digest=_digest(material),
    )
    if not permitted:
        return decision, state
    return decision, replace(
        state,
        actions_used=actions_after,
        revision=revision,
        last_receipt_digest=decision.receipt_digest,
    )


__all__ = [
    "AutonomyDecision",
    "AutonomyGrant",
    "AutonomyLevel",
    "AutonomyState",
    "authorize_change_plan",
    "deescalate",
    "escalate",
    "revoke",
]
