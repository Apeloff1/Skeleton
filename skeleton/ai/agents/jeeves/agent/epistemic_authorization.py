"""TOCTOU-safe authorization for epistemic Jeeves decisions.

An epistemic decision is evidence, not permission.  This module adds a separate,
one-time authorization boundary between a decision that recommends ``ACT`` and
any executor that may later perform the selected action.

The authorizer revalidates the exact world-model and learned-transition-model
fingerprints bound into the decision.  Issued tokens are short lived, bound to
one action, revocable, replay protected, and revalidated again at consumption.
No tool execution occurs here.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

from .epistemic_planning import DecisionDisposition, EpistemicDecision
from .model_based_control import AbstractAction, LearnedTransitionModel
from .types import (
    AgentContractError,
    finite_number,
    json_safe,
    positive_int,
    require_id,
    stable_fingerprint,
    stable_id,
)
from .world_model import BeliefGraph


class AuthorizationError(RuntimeError):
    """Raised for malformed authorization operations."""


class AuthorizationFailure(str, Enum):
    NOT_ACT_DECISION = "not_act_decision"
    MISSING_SELECTED_ACTION = "missing_selected_action"
    WORLD_STATE_CHANGED = "world_state_changed"
    MODEL_STATE_CHANGED = "model_state_changed"
    POLICY_CHANGED = "policy_changed"
    UNKNOWN_TOKEN = "unknown_token"
    ACTION_MISMATCH = "action_mismatch"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_REVOKED = "token_revoked"
    TOKEN_ALREADY_CONSUMED = "token_already_consumed"
    TOKEN_TAMPERED = "token_tampered"


@dataclass(frozen=True, slots=True)
class AuthorizationPolicy:
    token_ttl_seconds: float = 30.0
    maximum_live_tokens: int = 2048
    maximum_audit_events: int = 20_000
    require_policy_fingerprint: bool = True
    revalidate_on_consume: bool = True

    def __post_init__(self) -> None:
        ttl = finite_number("token_ttl_seconds", self.token_ttl_seconds)
        if not 0.01 <= ttl <= 86_400.0:
            raise AgentContractError("token_ttl_seconds must be in [0.01, 86400]")
        object.__setattr__(self, "token_ttl_seconds", ttl)
        object.__setattr__(
            self,
            "maximum_live_tokens",
            positive_int("maximum_live_tokens", self.maximum_live_tokens, maximum=1_000_000),
        )
        object.__setattr__(
            self,
            "maximum_audit_events",
            positive_int("maximum_audit_events", self.maximum_audit_events, maximum=5_000_000),
        )


@dataclass(frozen=True, slots=True)
class AuthorizationToken:
    token_id: str
    decision_id: str
    decision_fingerprint: str
    action_id: str
    world_fingerprint: str
    model_fingerprint: str
    policy_fingerprint: str
    issued_at: float
    expires_at: float
    sequence: int
    token_fingerprint: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "token_id",
            "decision_id",
            "action_id",
        ):
            object.__setattr__(self, name, require_id(name, getattr(self, name)))
        for name in (
            "decision_fingerprint",
            "world_fingerprint",
            "model_fingerprint",
            "policy_fingerprint",
            "token_fingerprint",
        ):
            value = str(getattr(self, name)).strip().lower()
            if len(value) != 64:
                raise AgentContractError(f"{name} must be a sha256 fingerprint")
            object.__setattr__(self, name, value)
        issued = finite_number("issued_at", self.issued_at)
        expires = finite_number("expires_at", self.expires_at)
        if issued < 0 or expires <= issued:
            raise AgentContractError("authorization token timestamps are invalid")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        sequence = positive_int("sequence", self.sequence, maximum=2_147_483_647)
        object.__setattr__(self, "sequence", sequence)
        object.__setattr__(self, "metadata", json_safe(dict(self.metadata)))

    @property
    def canonical_payload(self) -> Mapping[str, Any]:
        return {
            "decision_id": self.decision_id,
            "decision_fingerprint": self.decision_fingerprint,
            "action_id": self.action_id,
            "world_fingerprint": self.world_fingerprint,
            "model_fingerprint": self.model_fingerprint,
            "policy_fingerprint": self.policy_fingerprint,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "sequence": self.sequence,
            "metadata": self.metadata,
        }

    def verify_fingerprint(self) -> bool:
        return stable_fingerprint(self.canonical_payload) == self.token_fingerprint


@dataclass(frozen=True, slots=True)
class ExecutionPermit:
    permit_id: str
    token_id: str
    decision_id: str
    action: AbstractAction
    authorized_at: float
    world_fingerprint: str
    model_fingerprint: str
    policy_fingerprint: str
    permit_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "permit_id", require_id("permit_id", self.permit_id))
        object.__setattr__(self, "token_id", require_id("token_id", self.token_id))
        object.__setattr__(self, "decision_id", require_id("decision_id", self.decision_id))
        if not isinstance(self.action, AbstractAction):
            raise AgentContractError("action must be AbstractAction")
        at = finite_number("authorized_at", self.authorized_at)
        if at < 0:
            raise AgentContractError("authorized_at must be non-negative")
        object.__setattr__(self, "authorized_at", at)
        for name in (
            "world_fingerprint",
            "model_fingerprint",
            "policy_fingerprint",
            "permit_fingerprint",
        ):
            value = str(getattr(self, name)).strip().lower()
            if len(value) != 64:
                raise AgentContractError(f"{name} must be a sha256 fingerprint")
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    allowed: bool
    token: AuthorizationToken | None = None
    permit: ExecutionPermit | None = None
    failures: tuple[AuthorizationFailure, ...] = ()
    detail: tuple[str, ...] = ()
    fingerprint: str = ""


@dataclass(frozen=True, slots=True)
class AuthorizationAuditEvent:
    event_id: str
    kind: str
    at: float
    token_id: str | None
    decision_id: str | None
    action_id: str | None
    allowed: bool
    failures: tuple[AuthorizationFailure, ...]
    world_fingerprint: str
    model_fingerprint: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _TokenState:
    token: AuthorizationToken
    action: AbstractAction
    revoked: bool = False
    consumed: bool = False
    revoked_reason: str = ""
    consumed_at: float | None = None


class DecisionAuthorizer:
    """Issue and consume single-use execution permits for fresh ACT decisions."""

    def __init__(
        self,
        world: BeliefGraph,
        model: LearnedTransitionModel,
        *,
        policy: AuthorizationPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(world, BeliefGraph):
            raise TypeError("world must be BeliefGraph")
        if not isinstance(model, LearnedTransitionModel):
            raise TypeError("model must be LearnedTransitionModel")
        self.world = world
        self.model = model
        self.policy = policy or AuthorizationPolicy()
        self._clock = clock
        self._sequence = 0
        self._tokens: dict[str, _TokenState] = {}
        self._token_order: deque[str] = deque()
        self._audit: deque[AuthorizationAuditEvent] = deque(
            maxlen=self.policy.maximum_audit_events
        )
        self._lock = threading.RLock()

    def issue(
        self,
        decision: EpistemicDecision,
        *,
        expected_policy_fingerprint: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AuthorizationResult:
        if not isinstance(decision, EpistemicDecision):
            raise TypeError("decision must be EpistemicDecision")

        now = self._now()
        current_world, current_model = self._current_fingerprints()
        failures: list[AuthorizationFailure] = []
        detail: list[str] = []

        if decision.disposition is not DecisionDisposition.ACT:
            failures.append(AuthorizationFailure.NOT_ACT_DECISION)
        if decision.selected_action is None:
            failures.append(AuthorizationFailure.MISSING_SELECTED_ACTION)
        if decision.world_fingerprint != current_world:
            failures.append(AuthorizationFailure.WORLD_STATE_CHANGED)
        if decision.model_fingerprint != current_model:
            failures.append(AuthorizationFailure.MODEL_STATE_CHANGED)

        if self.policy.require_policy_fingerprint:
            if expected_policy_fingerprint is None:
                failures.append(AuthorizationFailure.POLICY_CHANGED)
                detail.append("expected policy fingerprint is required")
            elif expected_policy_fingerprint != decision.policy_fingerprint:
                failures.append(AuthorizationFailure.POLICY_CHANGED)

        if failures:
            return self._result(
                allowed=False,
                failures=failures,
                detail=detail,
                decision=decision,
                at=now,
                world_fingerprint=current_world,
                model_fingerprint=current_model,
                kind="issue_rejected",
            )

        assert decision.selected_action is not None
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
            payload = {
                "decision_id": decision.decision_id,
                "decision_fingerprint": decision.fingerprint,
                "action_id": decision.selected_action.action_id,
                "world_fingerprint": decision.world_fingerprint,
                "model_fingerprint": decision.model_fingerprint,
                "policy_fingerprint": decision.policy_fingerprint,
                "issued_at": now,
                "expires_at": now + self.policy.token_ttl_seconds,
                "sequence": sequence,
                "metadata": json_safe(dict(metadata or {})),
            }
            token_fingerprint = stable_fingerprint(payload)
            token = AuthorizationToken(
                token_id=stable_id(
                    "authz",
                    {
                        "fingerprint": token_fingerprint,
                        "sequence": sequence,
                    },
                ),
                decision_id=decision.decision_id,
                decision_fingerprint=decision.fingerprint,
                action_id=decision.selected_action.action_id,
                world_fingerprint=decision.world_fingerprint,
                model_fingerprint=decision.model_fingerprint,
                policy_fingerprint=decision.policy_fingerprint,
                issued_at=now,
                expires_at=now + self.policy.token_ttl_seconds,
                sequence=sequence,
                token_fingerprint=token_fingerprint,
                metadata=payload["metadata"],
            )
            self._tokens[token.token_id] = _TokenState(
                token=token,
                action=decision.selected_action,
            )
            self._token_order.append(token.token_id)
            self._evict_if_needed()

        return self._result(
            allowed=True,
            token=token,
            decision=decision,
            at=now,
            world_fingerprint=current_world,
            model_fingerprint=current_model,
            kind="issued",
        )

    def consume(
        self,
        token: AuthorizationToken,
        *,
        action_id: str,
        expected_policy_fingerprint: str | None = None,
    ) -> AuthorizationResult:
        if not isinstance(token, AuthorizationToken):
            raise TypeError("token must be AuthorizationToken")
        action_id = require_id("action_id", action_id)
        now = self._now()
        current_world, current_model = self._current_fingerprints()

        with self._lock:
            state = self._tokens.get(token.token_id)
            failures: list[AuthorizationFailure] = []
            detail: list[str] = []

            if not token.verify_fingerprint():
                failures.append(AuthorizationFailure.TOKEN_TAMPERED)
            if state is None:
                failures.append(AuthorizationFailure.UNKNOWN_TOKEN)
            else:
                if state.token.token_fingerprint != token.token_fingerprint:
                    failures.append(AuthorizationFailure.TOKEN_TAMPERED)
                if state.revoked:
                    failures.append(AuthorizationFailure.TOKEN_REVOKED)
                    if state.revoked_reason:
                        detail.append(state.revoked_reason)
                if state.consumed:
                    failures.append(AuthorizationFailure.TOKEN_ALREADY_CONSUMED)
                if now > state.token.expires_at:
                    failures.append(AuthorizationFailure.TOKEN_EXPIRED)
                if action_id != state.token.action_id:
                    failures.append(AuthorizationFailure.ACTION_MISMATCH)

                if self.policy.require_policy_fingerprint:
                    if expected_policy_fingerprint is None:
                        failures.append(AuthorizationFailure.POLICY_CHANGED)
                        detail.append("expected policy fingerprint is required")
                    elif expected_policy_fingerprint != state.token.policy_fingerprint:
                        failures.append(AuthorizationFailure.POLICY_CHANGED)

                if self.policy.revalidate_on_consume:
                    if current_world != state.token.world_fingerprint:
                        failures.append(AuthorizationFailure.WORLD_STATE_CHANGED)
                    if current_model != state.token.model_fingerprint:
                        failures.append(AuthorizationFailure.MODEL_STATE_CHANGED)

            if failures:
                decision_id = state.token.decision_id if state is not None else token.decision_id
                return self._result(
                    allowed=False,
                    token=token,
                    failures=failures,
                    detail=detail,
                    decision_id=decision_id,
                    action_id=action_id,
                    at=now,
                    world_fingerprint=current_world,
                    model_fingerprint=current_model,
                    kind="consume_rejected",
                )

            assert state is not None
            state.consumed = True
            state.consumed_at = now
            permit_payload = {
                "token": state.token.token_id,
                "decision": state.token.decision_id,
                "action": state.action.action_id,
                "authorized_at": now,
                "world": current_world,
                "model": current_model,
                "policy": state.token.policy_fingerprint,
            }
            permit_fingerprint = stable_fingerprint(permit_payload)
            permit = ExecutionPermit(
                permit_id=stable_id(
                    "permit",
                    {
                        "fingerprint": permit_fingerprint,
                        "token": state.token.token_id,
                    },
                ),
                token_id=state.token.token_id,
                decision_id=state.token.decision_id,
                action=state.action,
                authorized_at=now,
                world_fingerprint=current_world,
                model_fingerprint=current_model,
                policy_fingerprint=state.token.policy_fingerprint,
                permit_fingerprint=permit_fingerprint,
            )

        return self._result(
            allowed=True,
            token=token,
            permit=permit,
            decision_id=token.decision_id,
            action_id=action_id,
            at=now,
            world_fingerprint=current_world,
            model_fingerprint=current_model,
            kind="consumed",
        )

    def revoke(self, token_id: str, *, reason: str = "revoked") -> bool:
        token_id = require_id("token_id", token_id)
        reason = str(reason).strip()[:2048]
        now = self._now()
        current_world, current_model = self._current_fingerprints()
        with self._lock:
            state = self._tokens.get(token_id)
            if state is None:
                return False
            state.revoked = True
            state.revoked_reason = reason
            self._append_audit(
                kind="revoked",
                at=now,
                token_id=token_id,
                decision_id=state.token.decision_id,
                action_id=state.token.action_id,
                allowed=False,
                failures=(AuthorizationFailure.TOKEN_REVOKED,),
                world_fingerprint=current_world,
                model_fingerprint=current_model,
                metadata={"reason": reason},
            )
            return True

    def revoke_all(self, *, reason: str = "bulk revoke") -> int:
        reason = str(reason).strip()[:2048]
        count = 0
        with self._lock:
            ids = tuple(self._tokens)
        for token_id in ids:
            with self._lock:
                state = self._tokens.get(token_id)
                should_revoke = state is not None and not state.revoked and not state.consumed
            if should_revoke and self.revoke(token_id, reason=reason):
                count += 1
        return count

    def token_state(self, token_id: str) -> Mapping[str, Any] | None:
        token_id = require_id("token_id", token_id)
        with self._lock:
            state = self._tokens.get(token_id)
            if state is None:
                return None
            now = self._now()
            return {
                "token_id": state.token.token_id,
                "decision_id": state.token.decision_id,
                "action_id": state.token.action_id,
                "revoked": state.revoked,
                "consumed": state.consumed,
                "expired": now > state.token.expires_at,
                "issued_at": state.token.issued_at,
                "expires_at": state.token.expires_at,
                "consumed_at": state.consumed_at,
                "fingerprint_valid": state.token.verify_fingerprint(),
            }

    def audit_events(self, *, limit: int = 100) -> tuple[AuthorizationAuditEvent, ...]:
        limit = positive_int("limit", limit, maximum=self.policy.maximum_audit_events)
        with self._lock:
            return tuple(list(self._audit)[-limit:])

    @property
    def live_token_count(self) -> int:
        now = self._now()
        with self._lock:
            return sum(
                1
                for state in self._tokens.values()
                if not state.revoked
                and not state.consumed
                and now <= state.token.expires_at
            )

    def _evict_if_needed(self) -> None:
        while len(self._tokens) > self.policy.maximum_live_tokens and self._token_order:
            oldest = self._token_order.popleft()
            state = self._tokens.get(oldest)
            if state is None:
                continue
            if not state.consumed and not state.revoked:
                state.revoked = True
                state.revoked_reason = "evicted by authorization capacity bound"
            self._tokens.pop(oldest, None)

    def _result(
        self,
        *,
        allowed: bool,
        at: float,
        world_fingerprint: str,
        model_fingerprint: str,
        kind: str,
        token: AuthorizationToken | None = None,
        permit: ExecutionPermit | None = None,
        failures: list[AuthorizationFailure] | tuple[AuthorizationFailure, ...] = (),
        detail: list[str] | tuple[str, ...] = (),
        decision: EpistemicDecision | None = None,
        decision_id: str | None = None,
        action_id: str | None = None,
    ) -> AuthorizationResult:
        failures_tuple = tuple(dict.fromkeys(failures))
        detail_tuple = tuple(detail)
        resolved_decision_id = (
            decision.decision_id if decision is not None else decision_id
        )
        resolved_action_id = action_id
        if decision is not None and decision.selected_action is not None:
            resolved_action_id = decision.selected_action.action_id

        payload = {
            "allowed": allowed,
            "token": token.token_id if token else None,
            "permit": permit.permit_id if permit else None,
            "failures": [item.value for item in failures_tuple],
            "detail": detail_tuple,
            "decision": resolved_decision_id,
            "action": resolved_action_id,
            "world": world_fingerprint,
            "model": model_fingerprint,
            "kind": kind,
            "at": at,
        }
        fingerprint = stable_fingerprint(payload)
        result = AuthorizationResult(
            allowed=allowed,
            token=token,
            permit=permit,
            failures=failures_tuple,
            detail=detail_tuple,
            fingerprint=fingerprint,
        )
        self._append_audit(
            kind=kind,
            at=at,
            token_id=token.token_id if token else None,
            decision_id=resolved_decision_id,
            action_id=resolved_action_id,
            allowed=allowed,
            failures=failures_tuple,
            world_fingerprint=world_fingerprint,
            model_fingerprint=model_fingerprint,
            metadata={
                "result_fingerprint": fingerprint,
                "permit_id": permit.permit_id if permit else None,
                "detail": detail_tuple,
            },
        )
        return result

    def _append_audit(
        self,
        *,
        kind: str,
        at: float,
        token_id: str | None,
        decision_id: str | None,
        action_id: str | None,
        allowed: bool,
        failures: tuple[AuthorizationFailure, ...],
        world_fingerprint: str,
        model_fingerprint: str,
        metadata: Mapping[str, Any],
    ) -> None:
        payload = {
            "kind": kind,
            "at": at,
            "token_id": token_id,
            "decision_id": decision_id,
            "action_id": action_id,
            "allowed": allowed,
            "failures": [item.value for item in failures],
            "world": world_fingerprint,
            "model": model_fingerprint,
            "metadata": json_safe(dict(metadata)),
        }
        event = AuthorizationAuditEvent(
            event_id=stable_id("authz_event", payload),
            kind=kind,
            at=at,
            token_id=token_id,
            decision_id=decision_id,
            action_id=action_id,
            allowed=allowed,
            failures=failures,
            world_fingerprint=world_fingerprint,
            model_fingerprint=model_fingerprint,
            metadata=payload["metadata"],
        )
        with self._lock:
            self._audit.append(event)

    def _current_fingerprints(self) -> tuple[str, str]:
        return self.world.snapshot(persist=False).fingerprint, self.model.fingerprint

    def _now(self) -> float:
        value = finite_number("clock", self._clock())
        if value < 0:
            raise AuthorizationError("clock returned negative time")
        return value
