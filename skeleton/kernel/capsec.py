"""Capsec — the deny-by-default capability gate (B031, frozen interface v1).

This module *extends* :mod:`skeleton.kernel.capabilities` (owned by Internal
Systems); it does not fork or rewrite it. Token minting, HMAC signing,
attenuation and revocation stay in :class:`~.capabilities.TokenIssuer`. Capsec
adds the pieces every tool and provider call needs on top of that:

- :class:`CapabilityToken` — re-exported unchanged from ``capabilities``. A
  token is *scoped* (each :class:`Capability` carries ``scope``/``action``/
  ``constraints``) and *expiring* (each capability carries ``expires_at``);
  :func:`token_expires_at` exposes the effective token-level expiry.
- :class:`Action` — what a caller is about to do (``scope``, ``verb``, an
  optional ``resource`` label for audit, optional ``constraints``).
- :class:`Decision` — the gate's verdict. ``allowed`` is ``False`` unless a
  live, verified, unrevoked capability covers the action.
- :class:`AuditRecord` — one immutable, serialisable record per decision,
  allowed *or* denied, delivered to an :class:`AuditSink`.
- :class:`CapabilityGate` — the frozen ``check(cap, action) -> Decision``
  Protocol. Klint (``skeleton/tools/``) and Bork (``skeleton/integrations/``)
  code against this Protocol, never against a concrete gate.
- :class:`KernelCapabilityGate` — the reference implementation backed by a
  :class:`~.capabilities.TokenIssuer`.

Deny-by-default contract (normative for every ``CapabilityGate``):

1. ``check`` never raises for a bad, missing, forged, expired or revoked
   token, nor for a malformed action; it returns a denying ``Decision``.
2. Only a signed, serialised token string is accepted as ``cap``. Anything
   else (``None``, a decoded :class:`CapabilityToken`, bytes) is denied with
   reason ``"unsigned_token"`` because its authority cannot be verified.
3. Every call produces exactly one :class:`AuditRecord`. If the audit sink
   itself fails, the decision is forced to *deny* (``"audit_unavailable"``):
   no unaudited authority.

Stdlib only, so this stays inside the kernel's no-framework/no-I/O boundary.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Protocol, Tuple, runtime_checkable

from .capabilities import (
    Capability,
    CapabilityError,
    CapabilityToken,
    ForgeryError,
    TokenExpired,
    TokenIssuer,
    TokenRevoked,
)

__all__ = [
    "CAPSEC_INTERFACE_VERSION",
    "Action",
    "AuditRecord",
    "AuditSink",
    "Capability",
    "CapabilityGate",
    "CapabilityToken",
    "CompositeAuditSink",
    "Decision",
    "DenyAllGate",
    "InMemoryAuditSink",
    "KernelCapabilityGate",
    "ReasonCode",
    "capability_for",
    "mint_scoped",
    "token_expires_at",
]

#: Bumped only on a breaking change to the dataclasses or the Protocol.
CAPSEC_INTERFACE_VERSION = 1


class ReasonCode:
    """Stable machine-readable reasons carried on :class:`Decision`."""

    ALLOWED = "allowed"
    UNSIGNED_TOKEN = "unsigned_token"
    MALFORMED_ACTION = "malformed_action"
    FORGED = "forged"
    EXPIRED = "expired"
    REVOKED = "revoked"
    NOT_COVERED = "not_covered"
    INVALID_TOKEN = "invalid_token"
    AUDIT_UNAVAILABLE = "audit_unavailable"
    GATE_DISABLED = "gate_disabled"


def token_expires_at(token: CapabilityToken) -> Optional[float]:
    """Effective expiry of ``token``: the earliest capability expiry.

    ``None`` means no capability on the token expires. Tokens are verified
    capability-by-capability, so a token stops verifying as soon as *any* of
    its capabilities lapses; the earliest expiry is therefore authoritative.
    """

    expiries = [c.expires_at for c in token.capabilities if c.expires_at is not None]
    return min(expiries) if expiries else None


@dataclass(frozen=True)
class Action:
    """A sensitive operation a caller is about to perform.

    ``scope`` and ``verb`` are matched against :class:`Capability` ``scope``
    and ``action`` (``"*"`` on the capability side is a wildcard; it is *not*
    a wildcard here). ``resource`` is an audit label only (e.g. a tool name or
    ``provider_id``) and never widens authority. ``constraints`` must match a
    constrained capability exactly, per :meth:`Capability.covers`.

    Conventions used by B031 callers:

    - tools (Klint):        ``Action("tool.<name>", "invoke", resource=...)``
    - providers (Bork/AI):  ``Action("provider.<provider_id>", "call", ...)``
    - integrations (Bork):  ``Action("integration.<name>", "<verb>", ...)``
    """

    scope: str
    verb: str
    resource: Optional[str] = None
    constraints: FrozenSet[Tuple[str, str]] = field(default_factory=frozenset)

    def is_well_formed(self) -> bool:
        return (
            isinstance(self.scope, str)
            and isinstance(self.verb, str)
            and bool(self.scope.strip())
            and bool(self.verb.strip())
            and self.scope != "*"
            and self.verb != "*"
        )

    def as_probe(self, now: Optional[float] = None) -> Capability:
        """The capability that must be covered for this action to proceed.

        The probe carries ``expires_at=now`` so that an *expiring* grant can
        cover it: :meth:`Capability.covers` only lets a capability with an
        expiry cover a request whose own expiry is no later than it.
        """

        return Capability(scope=self.scope, action=self.verb,
                          constraints=self.constraints,
                          expires_at=time.time() if now is None else now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "verb": self.verb,
            "resource": self.resource,
            "constraints": sorted(list(self.constraints)),
        }


@dataclass(frozen=True)
class AuditRecord:
    """Immutable audit entry; one per :meth:`CapabilityGate.check` call.

    Never contains the serialised token (it is a bearer credential); only
    ``token_id``/``parent_id``/``subject`` derived from a *verified* token.
    """

    record_id: str
    decided_at: float
    allowed: bool
    reason: str
    action: Action
    subject: Optional[str] = None
    token_id: Optional[str] = None
    parent_id: Optional[str] = None
    matched_scope: Optional[str] = None
    matched_action: Optional[str] = None
    gate: str = "capsec"
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "decided_at": self.decided_at,
            "allowed": self.allowed,
            "reason": self.reason,
            "action": self.action.to_dict(),
            "subject": self.subject,
            "token_id": self.token_id,
            "parent_id": self.parent_id,
            "matched_scope": self.matched_scope,
            "matched_action": self.matched_action,
            "gate": self.gate,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True)
class Decision:
    """Verdict of a capability check. Falsy unless explicitly allowed."""

    allowed: bool
    reason: str
    action: Action
    audit: AuditRecord
    subject: Optional[str] = None
    token_id: Optional[str] = None
    expires_at: Optional[float] = None

    def __bool__(self) -> bool:
        return self.allowed

    def require(self) -> "Decision":
        """Return ``self`` if allowed, else raise :class:`CapabilityError`."""

        if not self.allowed:
            raise CapabilityError(
                "capability check denied",
                context={
                    "reason": self.reason,
                    "scope": self.action.scope,
                    "verb": self.action.verb,
                    "record_id": self.audit.record_id,
                },
            )
        return self


@runtime_checkable
class AuditSink(Protocol):
    """Receives every :class:`AuditRecord`. Must be durable enough for policy;
    raising from :meth:`record` forces the gate to deny."""

    def record(self, entry: AuditRecord) -> None: ...


@runtime_checkable
class CapabilityGate(Protocol):
    """Frozen gate Protocol: every tool and provider call goes through here.

    ``cap`` is the signed, serialised token string produced by
    :meth:`TokenIssuer.mint`/``attenuate``. Implementations MUST honour the
    deny-by-default contract in the module docstring.
    """

    def check(self, cap: Optional[str], action: Action) -> Decision: ...


class InMemoryAuditSink:
    """Thread-safe bounded in-memory sink (tests, dev, local runtimes)."""

    def __init__(self, max_records: int = 10_000) -> None:
        self._max = max(1, int(max_records))
        self._lock = threading.Lock()
        self._records: List[AuditRecord] = []

    def record(self, entry: AuditRecord) -> None:
        with self._lock:
            self._records.append(entry)
            overflow = len(self._records) - self._max
            if overflow > 0:
                del self._records[:overflow]

    @property
    def records(self) -> Tuple[AuditRecord, ...]:
        with self._lock:
            return tuple(self._records)

    # Additive (phase 2) read helpers; ``records`` is unchanged.
    def query(self, *, allowed: Optional[bool] = None, reason: Optional[str] = None,
              token_id: Optional[str] = None, subject: Optional[str] = None,
              scope: Optional[str] = None) -> Tuple[AuditRecord, ...]:
        """Records matching every given filter, oldest first."""

        return tuple(
            r for r in self.records
            if (allowed is None or r.allowed is allowed)
            and (reason is None or r.reason == reason)
            and (token_id is None or r.token_id == token_id)
            and (subject is None or r.subject == subject)
            and (scope is None or r.action.scope == scope)
        )

    def denied(self) -> Tuple[AuditRecord, ...]:
        return self.query(allowed=False)


class CompositeAuditSink:
    """Fan one record out to several sinks, in order.

    If any sink raises, the error propagates, so the gate forces a deny
    (``audit_unavailable``). Use it to pair a local sink with a durable one.
    """

    def __init__(self, *sinks: AuditSink) -> None:
        if not sinks:
            raise ValueError("CompositeAuditSink needs at least one sink")
        for sink in sinks:
            if not isinstance(sink, AuditSink):
                raise TypeError("every sink must implement AuditSink.record")
        self._sinks: Tuple[AuditSink, ...] = tuple(sinks)

    @property
    def sinks(self) -> Tuple[AuditSink, ...]:
        return self._sinks

    def record(self, entry: AuditRecord) -> None:
        for sink in self._sinks:
            sink.record(entry)


def capability_for(action: Action, *, ttl_seconds: Optional[float] = None,
                   now: Optional[float] = None) -> Capability:
    """The narrowest :class:`Capability` that lets ``action`` through.

    Exact ``scope``/``verb``/``constraints`` (no wildcards). With
    ``ttl_seconds`` the grant expires ``ttl_seconds`` after ``now``.
    """

    if not isinstance(action, Action) or not action.is_well_formed():
        raise ValueError("capability_for needs a well-formed Action")
    expires_at: Optional[float] = None
    if ttl_seconds is not None:
        if isinstance(ttl_seconds, bool) or not float(ttl_seconds) > 0:
            raise ValueError("ttl_seconds must be > 0")
        expires_at = (time.time() if now is None else float(now)) + float(ttl_seconds)
    return Capability(scope=action.scope, action=action.verb,
                      constraints=action.constraints, expires_at=expires_at)


def mint_scoped(issuer: TokenIssuer, subject: str, actions: Iterable[Action], *,
                ttl_seconds: Optional[float] = None, now: Optional[float] = None) -> str:
    """Mint a token scoped to exactly ``actions``, optionally expiring.

    Thin wrapper over :meth:`TokenIssuer.mint` with :func:`capability_for`
    per action; signing and revocation stay in ``capabilities``.
    """

    caps = [capability_for(a, ttl_seconds=ttl_seconds, now=now) for a in actions]
    return issuer.mint(subject, caps)


class _Ids:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._n = 0

    def next(self) -> str:
        with self._lock:
            self._n += 1
            return f"capsec-{int(time.time() * 1000):x}-{self._n:x}"


class _GateBase:
    _name = "capsec"

    def __init__(self, audit: Optional[AuditSink]) -> None:
        self._audit: AuditSink = audit if audit is not None else InMemoryAuditSink()
        self._ids = _Ids()

    @property
    def audit_sink(self) -> AuditSink:
        return self._audit

    def _decide(self, action: Any, allowed: bool, reason: str, *, now: float,
                token: Optional[CapabilityToken] = None,
                matched: Optional[Capability] = None,
                detail: Optional[Mapping[str, Any]] = None) -> Decision:
        safe_action = action if isinstance(action, Action) else Action(
            scope=str(getattr(action, "scope", "<invalid>")),
            verb=str(getattr(action, "verb", "<invalid>")),
        )
        record = AuditRecord(
            record_id=self._ids.next(),
            decided_at=now,
            allowed=allowed,
            reason=reason,
            action=safe_action,
            subject=token.subject if token else None,
            token_id=token.token_id if token else None,
            parent_id=token.parent_id if token else None,
            matched_scope=matched.scope if matched else None,
            matched_action=matched.action if matched else None,
            gate=self._name,
            detail=dict(detail or {}),
        )
        try:
            self._audit.record(record)
        except Exception as exc:  # noqa: BLE001 — no unaudited authority
            record = AuditRecord(
                record_id=record.record_id,
                decided_at=now,
                allowed=False,
                reason=ReasonCode.AUDIT_UNAVAILABLE,
                action=safe_action,
                subject=record.subject,
                token_id=record.token_id,
                parent_id=record.parent_id,
                gate=self._name,
                detail={"audit_error": type(exc).__name__, "original_reason": reason},
            )
            allowed, reason = False, ReasonCode.AUDIT_UNAVAILABLE
        return Decision(
            allowed=allowed,
            reason=reason,
            action=safe_action,
            audit=record,
            subject=record.subject,
            token_id=record.token_id,
            expires_at=token_expires_at(token) if (token and allowed) else None,
        )


class DenyAllGate(_GateBase):
    """A gate that denies everything (still audited). Useful as the default
    wiring before a real issuer is configured: absence of policy == deny."""

    _name = "capsec.deny_all"

    def __init__(self, audit: Optional[AuditSink] = None) -> None:
        super().__init__(audit)

    def check(self, cap: Optional[str], action: Action) -> Decision:
        return self._decide(action, False, ReasonCode.GATE_DISABLED, now=time.time())


class KernelCapabilityGate(_GateBase):
    """Reference :class:`CapabilityGate` over a kernel :class:`TokenIssuer`.

    Verification (signature, revocation, expiry) is delegated to
    :meth:`TokenIssuer.verify`; coverage uses :meth:`Capability.covers`.
    """

    _name = "capsec.kernel"

    def __init__(self, issuer: TokenIssuer, audit: Optional[AuditSink] = None,
                 *, clock: Optional[Any] = None) -> None:
        if not isinstance(issuer, TokenIssuer):
            raise TypeError("issuer must be a kernel TokenIssuer")
        super().__init__(audit)
        self._issuer = issuer
        self._clock = clock or time.time

    def check(self, cap: Optional[str], action: Action) -> Decision:
        now = float(self._clock())
        if not isinstance(action, Action) or not action.is_well_formed():
            return self._decide(action, False, ReasonCode.MALFORMED_ACTION, now=now)
        if not isinstance(cap, str) or not cap:
            return self._decide(action, False, ReasonCode.UNSIGNED_TOKEN, now=now,
                                detail={"cap_type": type(cap).__name__})
        try:
            token = self._issuer.verify(cap, now=now)
        except ForgeryError:
            return self._decide(action, False, ReasonCode.FORGED, now=now)
        except TokenRevoked:
            return self._decide(action, False, ReasonCode.REVOKED, now=now)
        except TokenExpired:
            return self._decide(action, False, ReasonCode.EXPIRED, now=now)
        except Exception as exc:  # noqa: BLE001 — deny-by-default on anything else
            return self._decide(action, False, ReasonCode.INVALID_TOKEN, now=now,
                                detail={"error": type(exc).__name__})
        probe = action.as_probe(now)
        for capability in token.capabilities:
            if capability.is_live(now) and capability.covers(probe):
                return self._decide(action, True, ReasonCode.ALLOWED, now=now,
                                    token=token, matched=capability)
        return self._decide(action, False, ReasonCode.NOT_COVERED, now=now, token=token)
