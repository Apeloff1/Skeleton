"""Agent-to-agent authentication, scoped capabilities and delegation.

Agents authenticate with the Pack F service-token plane
(:mod:`skeleton.gate_plane.s2s`): an agent id *is* an s2s service name, its
token is minted by :class:`~skeleton.gate_plane.s2s.tokens.TokenSigner`
against the shared :class:`~skeleton.gate_plane.s2s.keyring.KeyRing` and is
addressed to the edge audience (``agent-edge`` by default).

Capability scopes (all validated by the s2s scope grammar)::

    msg:send:<topic>        publish on <topic>      (msg:send:* / msg:send:plan.* wildcards)
    msg:recv                pull/ack/nack own mailbox
    route:resolve           ask the router for a capability-addressed recipient
    agent:delegate          mint attenuated delegation tokens for another agent
    dlq:read / dlq:admin    inspect / replay dead letters

Delegation
----------

An agent holding ``agent:delegate`` can let another agent act *on its
behalf* with a subset of its own scopes (attenuation only — a delegate can
never gain a scope the delegator lacks) for at most the delegator's
remaining token lifetime. The delegation token is signed for the delegator
(``iss``) and names the delegate in ``ext.sub``; ``ext.chain`` records the
full ``root>...>delegate`` chain and ``ext.depth`` its length, bounded by
``max_delegation_depth``. When the delegate presents it the edge treats the
delegate as the acting agent and stamps ``on-behalf-of`` with the chain
root. Revoking any agent in a chain revokes every token derived through it.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Iterable, Mapping, Optional, Set, Tuple

from skeleton.gate_plane.agent_edge.envelope import Envelope, validate_agent_id
from skeleton.gate_plane.s2s.clock import Clock, system_clock
from skeleton.gate_plane.s2s.keyring import KeyRing
from skeleton.gate_plane.s2s.tokens import (
    MAX_TTL_S,
    ReplayCache,
    TokenError,
    TokenErrorCode,
    TokenSigner,
    TokenVerifier,
    VerifiedToken,
    scope_granted,
    validate_scope,
)

EDGE_AUDIENCE = "agent-edge"
SCOPE_SEND_PREFIX = "msg:send:"
SCOPE_RECV = "msg:recv"
SCOPE_RESOLVE = "route:resolve"
SCOPE_DELEGATE = "agent:delegate"
SCOPE_DLQ_READ = "dlq:read"
SCOPE_DLQ_ADMIN = "dlq:admin"
HEADER_ON_BEHALF_OF = "on-behalf-of"
HEADER_DELEGATION_CHAIN = "delegation-chain"
DEFAULT_MAX_DELEGATION_DEPTH = 3
_CHAIN_SEP = ">"
_DEPTH_RE = re.compile(r"^[0-9]{1,2}$")


def cap_granted(granted: Iterable[str], required: str) -> bool:
    """s2s ``prefix:*`` wildcards plus dotted topic wildcards (``msg:send:plan.*``)."""
    granted = tuple(granted)
    if scope_granted(granted, required):
        return True
    for g in granted:
        if g.endswith(".*") and required.startswith(g[:-1]) and len(required) > len(g) - 1:
            return True
    return False


def send_scope(topic: str) -> str:
    return validate_scope(f"{SCOPE_SEND_PREFIX}{topic}")


class AuthFailure(str, Enum):
    TOKEN_INVALID = "token_invalid"
    BAD_DELEGATION = "bad_delegation"
    DELEGATION_TOO_DEEP = "delegation_too_deep"
    REVOKED_AGENT = "revoked_agent"
    SENDER_MISMATCH = "sender_mismatch"
    MISSING_SCOPE = "missing_scope"
    NOT_MAILBOX_OWNER = "not_mailbox_owner"
    SCOPE_ESCALATION = "scope_escalation"
    NOT_DELEGABLE = "not_delegable"
    CEILING_EXCEEDED = "ceiling_exceeded"


class AgentAuthError(Exception):
    def __init__(self, failure: AuthFailure, detail: str = "", *, token_error: Optional[TokenErrorCode] = None) -> None:
        super().__init__(f"{failure.value}: {detail}" if detail else failure.value)
        self.failure = failure
        self.detail = detail
        self.token_error = token_error

    @property
    def http_status(self) -> int:
        if self.failure in (AuthFailure.TOKEN_INVALID, AuthFailure.BAD_DELEGATION, AuthFailure.REVOKED_AGENT):
            return 401
        return 403

    def body(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"error": "unauthenticated" if self.http_status == 401 else "forbidden",
                               "reason": self.failure.value}
        if self.failure is AuthFailure.MISSING_SCOPE and self.detail:
            out["missing_scope"] = self.detail
        return out


@dataclass(frozen=True)
class AgentPrincipal:
    """Acting agent after token verification (delegation-aware)."""

    agent_id: str
    scopes: FrozenSet[str]
    expires_at: float
    kid: Optional[str] = None
    chain: Tuple[str, ...] = ()
    jti: Optional[str] = None

    @property
    def delegated(self) -> bool:
        return len(self.chain) > 1

    @property
    def on_behalf_of(self) -> Optional[str]:
        return self.chain[0] if self.delegated else None

    @property
    def depth(self) -> int:
        return max(0, len(self.chain) - 1)

    def can(self, scope: str) -> bool:
        return cap_granted(self.scopes, scope)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "scopes": sorted(self.scopes),
            "expires_at": self.expires_at,
            "delegated": self.delegated,
            "on_behalf_of": self.on_behalf_of,
            "chain": list(self.chain),
        }


class ScopeCeiling:
    """Upper bound of scopes each agent may ever be issued (default: none)."""

    def __init__(self, ceilings: Optional[Mapping[str, Iterable[str]]] = None, *, default: Iterable[str] = ()) -> None:
        self._lock = threading.Lock()
        self._ceilings: Dict[str, FrozenSet[str]] = {}
        self.default = frozenset(validate_scope(s) for s in default)
        for agent, scopes in (ceilings or {}).items():
            self.set(agent, scopes)

    def set(self, agent_id: str, scopes: Iterable[str]) -> None:
        validate_agent_id(agent_id)
        with self._lock:
            self._ceilings[agent_id] = frozenset(validate_scope(s) for s in scopes)

    def of(self, agent_id: str) -> FrozenSet[str]:
        with self._lock:
            return self._ceilings.get(agent_id, self.default)

    def allows(self, agent_id: str, scopes: Iterable[str]) -> Tuple[bool, Tuple[str, ...]]:
        ceiling = self.of(agent_id)
        over = tuple(sorted(s for s in scopes if not cap_granted(ceiling, s)))
        return (not over, over)


@dataclass
class AgentAuthority:
    """Issues and verifies agent credentials on top of the s2s token plane."""

    keyring: KeyRing
    ceiling: ScopeCeiling = field(default_factory=ScopeCeiling)
    audience: str = EDGE_AUDIENCE
    clock: Clock = field(default_factory=system_clock)
    default_ttl_s: float = 300.0
    max_delegation_depth: int = DEFAULT_MAX_DELEGATION_DEPTH
    replay_cache: Optional[ReplayCache] = None
    leeway_s: float = 5.0

    def __post_init__(self) -> None:
        if not 0 < self.default_ttl_s <= MAX_TTL_S:
            raise ValueError("default_ttl_s must be within (0, MAX_TTL_S]")
        if not 0 <= int(self.max_delegation_depth) <= 8:
            raise ValueError("max_delegation_depth must be within 0..8")
        self._revoked: Set[str] = set()
        self._lock = threading.Lock()
        self.verifier = TokenVerifier(
            self.audience, self.keyring, clock=self.clock, replay_cache=self.replay_cache, leeway_s=self.leeway_s
        )

    # -- issuance ---------------------------------------------------------------
    def _signer(self, agent_id: str) -> TokenSigner:
        return TokenSigner(agent_id, self.keyring, clock=self.clock, default_ttl_s=self.default_ttl_s)

    def issue(self, agent_id: str, scopes: Iterable[str], *, ttl_s: Optional[float] = None) -> str:
        """Mint an identity token for ``agent_id`` bounded by its scope ceiling."""
        validate_agent_id(agent_id)
        wanted = frozenset(validate_scope(s) for s in scopes)
        ok, over = self.ceiling.allows(agent_id, wanted)
        if not ok:
            raise AgentAuthError(AuthFailure.CEILING_EXCEEDED, ",".join(over))
        if self.is_revoked(agent_id):
            raise AgentAuthError(AuthFailure.REVOKED_AGENT, agent_id)
        return self._signer(agent_id).mint(self.audience, sorted(wanted), ttl_s=ttl_s)

    def delegate(
        self,
        principal: AgentPrincipal,
        delegate_id: str,
        scopes: Iterable[str],
        *,
        ttl_s: Optional[float] = None,
    ) -> str:
        """Mint an attenuated token letting ``delegate_id`` act for ``principal``."""
        validate_agent_id(delegate_id)
        if not principal.can(SCOPE_DELEGATE):
            raise AgentAuthError(AuthFailure.NOT_DELEGABLE, "agent:delegate required")
        if delegate_id in principal.chain:
            raise AgentAuthError(AuthFailure.BAD_DELEGATION, "delegation cycle")
        chain = (principal.chain or (principal.agent_id,)) + (delegate_id,)
        depth = len(chain) - 1
        if depth > self.max_delegation_depth:
            raise AgentAuthError(AuthFailure.DELEGATION_TOO_DEEP, str(depth))
        wanted = frozenset(validate_scope(s) for s in scopes)
        escalated = tuple(sorted(s for s in wanted if not principal.can(s)))
        if escalated:
            raise AgentAuthError(AuthFailure.SCOPE_ESCALATION, ",".join(escalated))
        if SCOPE_DELEGATE in wanted and depth >= self.max_delegation_depth:
            wanted = wanted - {SCOPE_DELEGATE}
        if any(self.is_revoked(a) for a in chain):
            raise AgentAuthError(AuthFailure.REVOKED_AGENT, "chain contains a revoked agent")
        now = self.clock.now()
        remaining = principal.expires_at - now
        if remaining <= 1:
            raise AgentAuthError(AuthFailure.TOKEN_INVALID, "delegator token about to expire")
        ttl = min(self.default_ttl_s if ttl_s is None else float(ttl_s), remaining, MAX_TTL_S)
        extra = {"sub": delegate_id, "chain": _CHAIN_SEP.join(chain), "depth": str(depth)}
        return self._signer(principal.agent_id).mint(self.audience, sorted(wanted), ttl_s=ttl, extra=extra)

    # -- revocation ------------------------------------------------------------------
    def revoke_agent(self, agent_id: str) -> None:
        validate_agent_id(agent_id)
        with self._lock:
            self._revoked.add(agent_id)

    def restore_agent(self, agent_id: str) -> None:
        with self._lock:
            self._revoked.discard(agent_id)

    def is_revoked(self, agent_id: str) -> bool:
        with self._lock:
            return agent_id in self._revoked

    # -- verification ------------------------------------------------------------------
    def authenticate(self, token: str) -> AgentPrincipal:
        try:
            verified = self.verifier.verify(token)
        except TokenError as exc:
            raise AgentAuthError(AuthFailure.TOKEN_INVALID, exc.code.value, token_error=exc.code) from exc
        return self.principal_from(verified)

    def principal_from(self, verified: VerifiedToken) -> AgentPrincipal:
        claims = verified.claims
        ext = dict(claims.extra)
        issuer = claims.iss
        if "sub" not in ext:
            if set(ext) & {"chain", "depth"}:
                raise AgentAuthError(AuthFailure.BAD_DELEGATION, "chain without subject")
            chain: Tuple[str, ...] = (issuer,)
            acting = issuer
        else:
            acting = ext["sub"]
            raw_chain = ext.get("chain", "")
            raw_depth = ext.get("depth", "")
            try:
                validate_agent_id(acting)
                chain = tuple(raw_chain.split(_CHAIN_SEP))
                for a in chain:
                    validate_agent_id(a)
            except ValueError as exc:
                raise AgentAuthError(AuthFailure.BAD_DELEGATION, "malformed chain") from exc
            if not _DEPTH_RE.match(raw_depth) or int(raw_depth) != len(chain) - 1:
                raise AgentAuthError(AuthFailure.BAD_DELEGATION, "depth mismatch")
            if len(chain) < 2 or chain[-1] != acting or chain[-2] != issuer:
                raise AgentAuthError(AuthFailure.BAD_DELEGATION, "chain does not end issuer>subject")
            if len(set(chain)) != len(chain):
                raise AgentAuthError(AuthFailure.BAD_DELEGATION, "delegation cycle")
            if len(chain) - 1 > self.max_delegation_depth:
                raise AgentAuthError(AuthFailure.DELEGATION_TOO_DEEP, str(len(chain) - 1))
        for a in chain:
            if self.is_revoked(a):
                raise AgentAuthError(AuthFailure.REVOKED_AGENT, a)
        # Ceiling still applies to the chain root: a delegated token can never
        # carry more than the root agent may be issued directly.
        ok, over = self.ceiling.allows(chain[0], claims.scopes)
        if not ok:
            raise AgentAuthError(AuthFailure.CEILING_EXCEEDED, ",".join(over))
        return AgentPrincipal(
            agent_id=acting,
            scopes=frozenset(claims.scopes),
            expires_at=claims.exp,
            kid=verified.kid,
            chain=chain,
            jti=claims.jti,
        )

    # -- authorization ------------------------------------------------------------------
    @staticmethod
    def require(principal: AgentPrincipal, scope: str) -> None:
        if not principal.can(scope):
            raise AgentAuthError(AuthFailure.MISSING_SCOPE, scope)

    def authorize_send(self, principal: AgentPrincipal, envelope: Envelope) -> None:
        if envelope.sender != principal.agent_id:
            raise AgentAuthError(AuthFailure.SENDER_MISMATCH, f"{envelope.sender}!={principal.agent_id}")
        self.require(principal, send_scope(envelope.topic))

    def authorize_mailbox(self, principal: AgentPrincipal, agent_id: str) -> None:
        if principal.agent_id != agent_id:
            raise AgentAuthError(AuthFailure.NOT_MAILBOX_OWNER, agent_id)
        self.require(principal, SCOPE_RECV)

    @staticmethod
    def provenance_headers(principal: AgentPrincipal) -> Dict[str, str]:
        if not principal.delegated:
            return {}
        return {
            HEADER_ON_BEHALF_OF: principal.chain[0],
            HEADER_DELEGATION_CHAIN: _CHAIN_SEP.join(principal.chain)[:512],
        }


__all__ = [
    "AgentAuthError",
    "AgentAuthority",
    "AgentPrincipal",
    "AuthFailure",
    "DEFAULT_MAX_DELEGATION_DEPTH",
    "EDGE_AUDIENCE",
    "HEADER_DELEGATION_CHAIN",
    "HEADER_ON_BEHALF_OF",
    "SCOPE_DELEGATE",
    "SCOPE_DLQ_ADMIN",
    "SCOPE_DLQ_READ",
    "SCOPE_RECV",
    "SCOPE_RESOLVE",
    "SCOPE_SEND_PREFIX",
    "ScopeCeiling",
    "cap_granted",
    "send_scope",
]
