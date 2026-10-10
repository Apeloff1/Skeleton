"""Agent edge facade: auth → routing → bus, with breaker feedback.

:class:`AgentEdge` is the single entry point the HTTP gateway (and in-process
callers) use. It never trusts caller-supplied identity: the sender of every
envelope is the authenticated :class:`AgentPrincipal`; delegated callers get
``on-behalf-of`` / ``delegation-chain`` provenance headers stamped by the
edge.

Breaker feedback loop: an ``ack`` scores a success and a ``nack`` a failure on
the recipient's gate-plane breaker (``agent:<id>``), so a consumer that keeps
failing is taken out of capability routing until its cool-down elapses and a
half-open probe succeeds. Poison messages are *not* scored (the message is
bad, not the agent).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from skeleton.gate_plane.agent_edge.auth import (
    SCOPE_DLQ_ADMIN,
    SCOPE_DLQ_READ,
    SCOPE_RESOLVE,
    AgentAuthError,
    AgentAuthority,
    AgentPrincipal,
)
from skeleton.gate_plane.agent_edge.bus import AgentBus, Delivery, PublishResult, UnknownLease
from skeleton.gate_plane.agent_edge.dlq import DeadLetter, DeadLetterReason
from skeleton.gate_plane.agent_edge.envelope import DEFAULT_PRIORITY, DEFAULT_TTL_S, Envelope, EnvelopeError
from skeleton.gate_plane.agent_edge.routing import AgentRouter, RouteDecision, RouteOutcome


class EdgeError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, detail: str = "", *, retry_after_s: Optional[float] = None, extra: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__(detail or self.code)
        self.detail = detail
        self.retry_after_s = retry_after_s
        self.extra = dict(extra or {})

    def body(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"error": self.code, "reason": self.detail or self.code}
        if self.retry_after_s is not None:
            out["retry_after_s"] = self.retry_after_s
        out.update(self.extra)
        return out


class NoRoute(EdgeError):
    status = 404
    code = "no_route"


class RouteUnavailable(EdgeError):
    status = 503
    code = "route_unavailable"


class LeaseNotFound(EdgeError):
    status = 404
    code = "lease_not_found"


class LeaseConflict(EdgeError):
    status = 409
    code = "lease_conflict"


@dataclass(frozen=True)
class SendRequest:
    """Caller intent; exactly one of ``recipient`` / ``capability`` is set."""

    topic: str
    payload: Mapping[str, Any]
    recipient: Optional[str] = None
    capability: Optional[str] = None
    lane: Optional[str] = None
    conversation_id: Optional[str] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    priority: int = DEFAULT_PRIORITY
    ttl_s: float = DEFAULT_TTL_S
    max_attempts: int = 5
    headers: Optional[Mapping[str, str]] = None
    message_id: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.recipient is None) == (self.capability is None):
            raise EdgeError("exactly one of recipient or capability is required")
        if self.lane is not None and self.capability is None:
            raise EdgeError("lane only applies to capability routing")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SendRequest":
        if not isinstance(data, Mapping):
            raise EdgeError("request body must be an object")
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]
        unknown = set(data) - known
        if unknown:
            raise EdgeError(f"unknown fields: {sorted(unknown)}")
        if "topic" not in data:
            raise EdgeError("topic is required")
        payload = data.get("payload") or {}
        if not isinstance(payload, Mapping):
            raise EdgeError("payload must be an object")
        try:
            return cls(
                topic=str(data["topic"]),
                payload=dict(payload),
                recipient=data.get("recipient"),
                capability=data.get("capability"),
                lane=data.get("lane"),
                conversation_id=data.get("conversation_id"),
                correlation_id=data.get("correlation_id"),
                causation_id=data.get("causation_id"),
                idempotency_key=data.get("idempotency_key"),
                priority=int(data.get("priority", DEFAULT_PRIORITY)),
                ttl_s=float(data.get("ttl_s", DEFAULT_TTL_S)),
                max_attempts=int(data.get("max_attempts", 5)),
                headers=dict(data.get("headers") or {}),
                message_id=data.get("message_id"),
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, EdgeError):
                raise
            raise EdgeError(str(exc)) from exc


@dataclass(frozen=True)
class SendOutcome:
    publish: PublishResult
    route: RouteDecision
    envelope: Envelope

    def as_dict(self) -> Dict[str, Any]:
        return {**self.publish.as_dict(), "recipient": self.envelope.recipient, "route": self.route.as_dict()}


_RESERVED_HEADERS = frozenset({"on-behalf-of", "delegation-chain"})


class AgentEdge:
    def __init__(self, bus: AgentBus, router: AgentRouter, authority: AgentAuthority, *, route_unknown_recipients: bool = False) -> None:
        self.bus = bus
        self.router = router
        self.authority = authority
        self.route_unknown_recipients = bool(route_unknown_recipients)
        if router.load_probe is None:
            router.load_probe = bus.depth
        self._lock = threading.Lock()
        self._counts: Dict[str, int] = {}

    def _count(self, key: str) -> None:
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1

    # -- send -----------------------------------------------------------------------
    def _resolve(self, request: SendRequest, conversation_id: str) -> RouteDecision:
        if request.capability is not None:
            return self.router.route(request.capability, lane=request.lane, conversation_id=conversation_id)
        assert request.recipient is not None
        decision = self.router.route_direct(request.recipient)
        if decision.outcome is RouteOutcome.NO_CANDIDATES and self.route_unknown_recipients:
            return RouteDecision(RouteOutcome.DIRECT, request.recipient, considered=(request.recipient,))
        return decision

    def send(self, principal: AgentPrincipal, request: SendRequest, *, now: Optional[float] = None) -> SendOutcome:
        t = self.bus.clock.now() if now is None else float(now)
        headers = dict(request.headers or {})
        if _RESERVED_HEADERS & {k.lower() for k in headers}:
            raise EdgeError("on-behalf-of / delegation-chain headers are set by the edge")
        headers.update(self.authority.provenance_headers(principal))
        from skeleton.gate_plane.agent_edge.envelope import new_id

        conversation_id = request.conversation_id or new_id("conv")
        placeholder_recipient = request.recipient or principal.agent_id
        try:
            draft = Envelope.new(
                sender=principal.agent_id,
                recipient=placeholder_recipient,
                topic=request.topic,
                payload=request.payload,
                conversation_id=conversation_id,
                correlation_id=request.correlation_id,
                causation_id=request.causation_id,
                priority=request.priority,
                ttl_s=request.ttl_s,
                max_attempts=request.max_attempts,
                idempotency_key=request.idempotency_key,
                headers=headers,
                now=t,
                message_id=request.message_id,
            )
        except EnvelopeError as exc:
            raise EdgeError(str(exc)) from exc
        try:
            self.authority.authorize_send(principal, draft)
        except ValueError as exc:  # scope grammar overflow for very long topics
            raise EdgeError(str(exc)) from exc
        if request.capability is not None:
            self.authority.require(principal, SCOPE_RESOLVE)

        try:
            decision = self._resolve(request, conversation_id)
        except ValueError as exc:  # invalid capability / lane
            raise EdgeError(str(exc)) from exc
        if not decision.routed:
            self._count(f"send_{decision.outcome.value}")
            if decision.outcome is RouteOutcome.NO_CANDIDATES:
                self.bus.reject_undeliverable(draft, DeadLetterReason.NO_ROUTE, error="no_candidates", now=t)
                raise NoRoute(decision.outcome.value, extra={"route": decision.as_dict()})
            raise RouteUnavailable(
                decision.outcome.value,
                retry_after_s=decision.retry_after_s if decision.retry_after_s is not None else 1.0,
                extra={"route": decision.as_dict()},
            )
        assert decision.agent_id is not None
        if decision.agent_id != draft.recipient:
            from dataclasses import replace

            draft = replace(draft, recipient=decision.agent_id)
        result = self.bus.publish(draft, now=t)
        self._count(f"send_{result.status.value}")
        return SendOutcome(result, decision, draft)

    # -- consume ------------------------------------------------------------------------
    def pull(
        self,
        principal: AgentPrincipal,
        agent_id: str,
        *,
        max_messages: int = 1,
        lease_s: Optional[float] = None,
        topics: Optional[Iterable[str]] = None,
        now: Optional[float] = None,
    ) -> List[Delivery]:
        self.authority.authorize_mailbox(principal, agent_id)
        try:
            deliveries = self.bus.pull(agent_id, max_messages=max_messages, lease_s=lease_s, topics=topics, now=now)
        except ValueError as exc:
            raise EdgeError(str(exc)) from exc
        self._count("pull")
        return deliveries

    def _own_lease(self, principal: AgentPrincipal, lease_id: str) -> str:
        owner = self.bus.lease_owner(lease_id)
        if owner is None:
            raise LeaseNotFound(lease_id)
        self.authority.authorize_mailbox(principal, owner)
        return owner

    def ack(self, principal: AgentPrincipal, lease_id: str, *, now: Optional[float] = None) -> Envelope:
        owner = self._own_lease(principal, lease_id)
        try:
            env = self.bus.ack(lease_id, now=now)
        except UnknownLease as exc:
            raise LeaseNotFound(str(exc)) from exc
        except Exception as exc:  # StaleLease
            raise LeaseConflict(str(exc) or "stale lease") from exc
        self.router.record(owner, ok=True)
        self._count("ack")
        return env

    def nack(
        self,
        principal: AgentPrincipal,
        lease_id: str,
        *,
        error: str = "",
        retry: bool = True,
        poison: bool = False,
        delay_s: Optional[float] = None,
        now: Optional[float] = None,
    ) -> Optional[DeadLetter]:
        owner = self._own_lease(principal, lease_id)
        try:
            letter = self.bus.nack(lease_id, error=error, retry=retry, poison=poison, delay_s=delay_s, now=now)
        except UnknownLease as exc:
            raise LeaseNotFound(str(exc)) from exc
        except Exception as exc:  # StaleLease
            raise LeaseConflict(str(exc) or "stale lease") from exc
        if not poison:
            self.router.record(owner, ok=False)
        self._count("nack")
        return letter

    def extend(self, principal: AgentPrincipal, lease_id: str, *, lease_s: Optional[float] = None, now: Optional[float] = None) -> float:
        self._own_lease(principal, lease_id)
        try:
            return self.bus.extend(lease_id, lease_s=lease_s, now=now)
        except UnknownLease as exc:
            raise LeaseNotFound(str(exc)) from exc
        except ValueError as exc:
            raise EdgeError(str(exc)) from exc
        except Exception as exc:
            raise LeaseConflict(str(exc) or "stale lease") from exc

    # -- routing / DLQ / ops ----------------------------------------------------------------
    def resolve(self, principal: AgentPrincipal, capability: str, *, lane: Optional[str] = None) -> RouteDecision:
        self.authority.require(principal, SCOPE_RESOLVE)
        try:
            return self.router.route(capability, lane=lane)
        except ValueError as exc:
            raise EdgeError(str(exc)) from exc

    def dead_letters(self, principal: AgentPrincipal, *, recipient: Optional[str] = None, reason: Optional[str] = None, limit: int = 100) -> List[DeadLetter]:
        self.authority.require(principal, SCOPE_DLQ_READ)
        try:
            why = None if reason is None else DeadLetterReason(reason)
        except ValueError as exc:
            raise EdgeError(f"unknown reason {reason!r}") from exc
        return self.bus.dlq.list(recipient=recipient, reason=why, limit=max(1, min(int(limit), 1000)))

    def replay(self, principal: AgentPrincipal, message_id: str, *, now: Optional[float] = None) -> PublishResult:
        self.authority.require(principal, SCOPE_DLQ_ADMIN)
        try:
            return self.bus.replay(message_id, now=now)
        except KeyError as exc:
            raise EdgeError(f"no dead letter {message_id!r}") from exc

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            counts = dict(self._counts)
        return {"edge": counts, "bus": self.bus.stats(), "router": self.router.stats()}


__all__ = [
    "AgentAuthError",
    "AgentEdge",
    "EdgeError",
    "LeaseConflict",
    "LeaseNotFound",
    "NoRoute",
    "RouteUnavailable",
    "SendOutcome",
    "SendRequest",
]
