"""Recovered-systems edge: one fail-closed gate in front of Jeeves, GameForge,
local AI and Hive.

Evaluation order for a request whose path a catalog system owns (requests
outside every system pass through untouched)::

    1. framing      duplicate/invalid Content-Length, CL + TE      -> 400
    2. method       verb not served by the system                   -> 405
    3. identity     principal from S2SAuthMiddleware or own verifier -> 401
                    (anonymous only on the system's probe patterns)
    4. callers      allow/deny service lists                        -> 403
    5. scopes       read / write / admin scopes, admin refuses
                    overlap-window keys                             -> 403
    6. size         declared Content-Length over the system cap     -> 413
    7. readiness    ReadinessRegistry says not ready                -> 503
    8. bulkhead     system in-flight cap reached                    -> 503 + Retry-After

Allowed requests get identity headers scrubbed, one trusted
``x-skeleton-caller`` / ``x-skeleton-system`` pair, and a propagated
deadline (the tighter of the caller's ``x-skeleton-deadline-ms`` and the
system budget). Streaming bodies are counted and cut at the cap with 413.
Responses have identity headers stripped, so the principal never leaves the
platform. Every decision is emitted as an audit event; observers can never
change a verdict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from skeleton.gate_plane.s2s.audit import AuditEvent
from skeleton.gate_plane.s2s.authz import Principal
from skeleton.gate_plane.s2s.clock import Clock, system_clock
from skeleton.gate_plane.s2s.gate import PRINCIPAL_SCOPE_KEY, TokenExtractionError, extract_token
from skeleton.gate_plane.s2s.tokens import TokenError, TokenVerifier, scope_granted
from skeleton.gate_plane.systems.bulkhead import BulkheadRegistry, Permit
from skeleton.gate_plane.systems.catalog import SystemCatalog, SystemProfile, default_catalog
from skeleton.gate_plane.systems.headers import (
    DEADLINE_HEADER,
    header_value,
    header_values,
    scrub_request_headers,
    scrub_response_headers,
    trusted_headers,
)
from skeleton.gate_plane.systems.readiness import ReadinessRegistry

EDGE_SCOPE_KEY = "recovered_system"
AUDIT_KIND = "systems_edge"


class EdgeOutcome(str, Enum):
    PASS_THROUGH = "pass_through"
    ALLOW = "allow"
    BAD_REQUEST = "bad_request"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    NOT_READY = "not_ready"
    BUSY = "busy"


_STATUS = {
    EdgeOutcome.PASS_THROUGH: 200,
    EdgeOutcome.ALLOW: 200,
    EdgeOutcome.BAD_REQUEST: 400,
    EdgeOutcome.UNAUTHENTICATED: 401,
    EdgeOutcome.FORBIDDEN: 403,
    EdgeOutcome.METHOD_NOT_ALLOWED: 405,
    EdgeOutcome.PAYLOAD_TOO_LARGE: 413,
    EdgeOutcome.NOT_READY: 503,
    EdgeOutcome.BUSY: 503,
}


@dataclass(frozen=True)
class EdgeDecision:
    outcome: EdgeOutcome
    reason: str
    system: Optional[str] = None
    service: Optional[str] = None
    tier: Optional[str] = None
    missing_scopes: Tuple[str, ...] = ()
    deadline_ms: Optional[int] = None
    headers: Tuple[Tuple[str, str], ...] = ()
    permit: Optional[Permit] = field(default=None, compare=False)

    @property
    def allowed(self) -> bool:
        return self.outcome in (EdgeOutcome.ALLOW, EdgeOutcome.PASS_THROUGH)

    @property
    def http_status(self) -> int:
        return _STATUS[self.outcome]

    def body(self) -> Dict[str, Any]:
        """Client-safe body: no service name, scopes held, key ids or tokens."""
        out: Dict[str, Any] = {"error": self.outcome.value, "reason": self.reason}
        if self.system is not None:
            out["system"] = self.system
        if self.missing_scopes:
            out["missing_scopes"] = list(self.missing_scopes)
        return out

    def as_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value, "reason": self.reason, "system": self.system,
            "service": self.service, "tier": self.tier, "missing_scopes": list(self.missing_scopes),
            "deadline_ms": self.deadline_ms, "http_status": self.http_status,
        }


AuditHook = Callable[[AuditEvent], None]


@dataclass
class EdgeRequest:
    method: str
    path: str
    headers: List[Tuple[bytes, bytes]]
    principal: Optional[Principal] = None


class RecoveredSystemsEdge:
    """Pure decision engine (no ASGI); reusable from tests and other transports."""

    def __init__(
        self,
        catalog: Optional[SystemCatalog] = None,
        *,
        readiness: Optional[ReadinessRegistry] = None,
        bulkheads: Optional[BulkheadRegistry] = None,
        verifier: Optional[TokenVerifier] = None,
        clock: Optional[Clock] = None,
        audit: Iterable[AuditHook] = (),
    ) -> None:
        self.catalog = catalog if catalog is not None else default_catalog()
        self.clock: Clock = clock if clock is not None else system_clock()
        self.readiness = readiness if readiness is not None else ReadinessRegistry(clock=self.clock)
        for prof in self.catalog.profiles():
            if not prof.requires_ready:
                self.readiness.mark_optional(prof.name)
        if bulkheads is None:
            bulkheads = BulkheadRegistry({p.name: p.limits.max_concurrency for p in self.catalog.profiles()})
        self.bulkheads = bulkheads
        self.verifier = verifier
        self._audit: List[AuditHook] = list(audit)

    def add_audit_hook(self, hook: AuditHook) -> None:
        self._audit.append(hook)

    # -- audit -------------------------------------------------------------
    def _emit(self, req: EdgeRequest, decision: EdgeDecision) -> EdgeDecision:
        if decision.outcome is EdgeOutcome.PASS_THROUGH:
            return decision
        event = AuditEvent(
            kind=AUDIT_KIND,
            at=self.clock.now(),
            action="admit" if decision.allowed else "deny",
            outcome=decision.outcome.value,
            reason=decision.reason,
            service=decision.service,
            policy=None if decision.system is None else f"{decision.system}:{decision.tier or '-'}",
            method=req.method,
            path=req.path.split("?", 1)[0],
            http_status=decision.http_status,
            detail={"system": decision.system, "missing_scopes": list(decision.missing_scopes)},
        )
        for hook in list(self._audit):
            try:
                hook(event)
            except Exception:  # noqa: BLE001 - observers never change a verdict
                pass
        return decision

    # -- identity ----------------------------------------------------------
    def _principal(self, req: EdgeRequest) -> Tuple[Optional[Principal], Optional[str]]:
        """(principal, error_reason). Upstream S2S principal wins over own verification."""
        if req.principal is not None:
            return req.principal, None
        if self.verifier is None:
            return None, None
        hdrs = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in req.headers}
        for name in ("authorization", "x-service-token"):
            if len(set(header_values(req.headers, name))) > 1:
                return None, "conflicting_credentials"
        try:
            raw = extract_token(hdrs)
        except TokenExtractionError:
            return None, "bad_credentials"
        if raw is None:
            return None, None
        try:
            verified = self.verifier.verify(raw)
        except TokenError as exc:
            return None, exc.code.value
        return Principal.from_verified(verified), None

    # -- evaluation --------------------------------------------------------
    def evaluate(self, req: EdgeRequest) -> EdgeDecision:
        prof = self.catalog.resolve(req.path)
        if prof is None:
            return EdgeDecision(EdgeOutcome.PASS_THROUGH, "not_a_system_path")
        meth = (req.method or "GET").upper()
        sysname = prof.name

        framing = _framing_problem(req.headers)
        if framing:
            return self._emit(req, EdgeDecision(EdgeOutcome.BAD_REQUEST, framing, sysname))
        if meth not in prof.methods:
            return self._emit(req, EdgeDecision(EdgeOutcome.METHOD_NOT_ALLOWED, "method_not_allowed", sysname))

        principal, err = self._principal(req)
        if err is not None:
            return self._emit(
                req,
                EdgeDecision(
                    EdgeOutcome.UNAUTHENTICATED, err, sysname,
                    headers=(("www-authenticate", 'Service realm="systems", error="invalid_token"'),),
                ),
            )
        tier, scopes = prof.required_scopes(meth, req.path)
        if principal is None or principal.anonymous:
            if not prof.is_anonymous_read(meth, req.path):
                return self._emit(
                    req,
                    EdgeDecision(
                        EdgeOutcome.UNAUTHENTICATED, "missing_token", sysname, tier=tier,
                        headers=(("www-authenticate", 'Service realm="systems", error="missing_token"'),),
                    ),
                )
            service = None
            tier = "probe"
        else:
            service = principal.service
            assert service is not None
            if service in prof.deny_services:
                return self._emit(req, EdgeDecision(EdgeOutcome.FORBIDDEN, "service_denied", sysname, service, tier))
            if prof.allow_services is not None and service not in prof.allow_services:
                return self._emit(
                    req, EdgeDecision(EdgeOutcome.FORBIDDEN, "service_not_allowed", sysname, service, tier)
                )
            if tier == "admin" and principal.in_overlap:
                return self._emit(
                    req, EdgeDecision(EdgeOutcome.FORBIDDEN, "overlap_key_forbidden", sysname, service, tier)
                )
            if not any(scope_granted(principal.scopes, s) for s in scopes):
                return self._emit(
                    req,
                    EdgeDecision(
                        EdgeOutcome.FORBIDDEN, "missing_scope", sysname, service, tier,
                        missing_scopes=tuple(sorted(scopes)),
                    ),
                )

        declared = _content_length(req.headers)
        if declared is not None and declared > prof.limits.max_body_bytes:
            return self._emit(
                req, EdgeDecision(EdgeOutcome.PAYLOAD_TOO_LARGE, "body_over_limit", sysname, service, tier)
            )

        if prof.requires_ready:
            state = self.readiness.check(sysname)
            if not state.ready:
                return self._emit(
                    req,
                    EdgeDecision(
                        EdgeOutcome.NOT_READY, f"not_ready:{state.reason}", sysname, service, tier,
                        headers=(("retry-after", "5"),),
                    ),
                )

        permit = self.bulkheads.get(sysname).try_acquire()
        if permit is None:
            return self._emit(
                req,
                EdgeDecision(EdgeOutcome.BUSY, "bulkhead_full", sysname, service, tier, headers=(("retry-after", "1"),)),
            )
        deadline_ms = _deadline_ms(prof, meth, req.headers)
        return self._emit(
            req, EdgeDecision(EdgeOutcome.ALLOW, "ok", sysname, service, tier, deadline_ms=deadline_ms, permit=permit)
        )

    def release(self, decision: EdgeDecision) -> None:
        if decision.permit is not None and decision.system is not None:
            self.bulkheads.get(decision.system).release(decision.permit)

    def describe(self) -> Dict[str, Any]:
        return {
            "catalog_digest": self.catalog.digest(),
            "systems": self.catalog.to_dicts(),
            "readiness": self.readiness.snapshot(),
            "bulkheads": self.bulkheads.stats(),
            "own_verifier": self.verifier is not None,
        }


def _content_length(raw: List[Tuple[bytes, bytes]]) -> Optional[int]:
    vals = header_values(raw, "content-length")
    if not vals:
        return None
    try:
        return int(vals[0].strip())
    except ValueError:
        return None


def _framing_problem(raw: List[Tuple[bytes, bytes]]) -> Optional[str]:
    cls = [v.strip() for v in header_values(raw, "content-length")]
    if cls:
        if len(set(cls)) > 1:
            return "conflicting_content_length"
        if not cls[0].isdigit():
            return "invalid_content_length"
        if header_values(raw, "transfer-encoding"):
            return "content_length_with_transfer_encoding"
    return None


def _deadline_ms(prof: SystemProfile, method: str, raw: List[Tuple[bytes, bytes]]) -> int:
    budget = int(prof.limits.deadline_for(method) * 1000)
    asked = header_value(raw, DEADLINE_HEADER)
    if asked is not None:
        try:
            v = int(asked.strip())
        except ValueError:
            v = -1
        if 0 < v < budget:
            return v
    return budget


ASGIApp = Callable[[MutableMapping[str, Any], Callable[[], Awaitable[Any]], Callable[[Any], Awaitable[None]]], Awaitable[None]]


async def _send_decision(send: Callable[[Any], Awaitable[None]], decision: EdgeDecision) -> None:
    body = json.dumps(decision.body(), sort_keys=True).encode("utf-8")
    hdrs = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    hdrs += [(k.encode("latin-1"), v.encode("latin-1")) for k, v in decision.headers]
    await send({"type": "http.response.start", "status": decision.http_status, "headers": hdrs})
    await send({"type": "http.response.body", "body": body})


class RecoveredSystemsMiddleware:
    """ASGI wrapper for :class:`RecoveredSystemsEdge`.

    Install *inside* ``S2SAuthMiddleware`` (add this middleware first) so the
    verified principal is available on the scope; or give the edge its own
    ``verifier`` to run standalone.
    """

    def __init__(self, app: ASGIApp, *, edge: RecoveredSystemsEdge) -> None:
        self.app = app
        self.edge = edge

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[Any]],
        send: Callable[[Any], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        principal = scope.get(PRINCIPAL_SCOPE_KEY)
        if principal is None:
            state = scope.get("state")
            if isinstance(state, Mapping):
                principal = state.get(PRINCIPAL_SCOPE_KEY)
        raw = list(scope.get("headers") or [])
        req = EdgeRequest(
            method=str(scope.get("method", "GET")),
            path=str(scope.get("path", "/")),
            headers=raw,
            principal=principal if isinstance(principal, Principal) else None,
        )
        decision = self.edge.evaluate(req)
        if decision.outcome is EdgeOutcome.PASS_THROUGH:
            await self.app(scope, receive, send)
            return
        if not decision.allowed:
            await _send_decision(send, decision)
            return

        prof = self.edge.catalog.get(decision.system or "")
        limit = prof.limits.max_body_bytes
        kept, _dropped = scrub_request_headers(raw)
        kept += trusted_headers(system=prof.name, caller=decision.service, deadline_ms=decision.deadline_ms)
        inner_scope = dict(scope)
        inner_scope["headers"] = kept
        inner_scope[EDGE_SCOPE_KEY] = {"system": prof.name, "tier": decision.tier, "deadline_ms": decision.deadline_ms}

        seen = 0
        overflow = False
        started = False

        async def guarded_receive() -> Any:
            nonlocal seen, overflow
            msg = await receive()
            if msg.get("type") == "http.request":
                seen += len(msg.get("body") or b"")
                if seen > limit:
                    overflow = True
                    raise _BodyOverflow()
            return msg

        async def guarded_send(message: Any) -> None:
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
                hdrs, _ = scrub_response_headers(list(message.get("headers") or []))
                message = {**message, "headers": hdrs}
            await send(message)

        try:
            await self.app(inner_scope, guarded_receive, guarded_send)
        except _BodyOverflow:
            if not started:
                await _send_decision(
                    send,
                    EdgeDecision(EdgeOutcome.PAYLOAD_TOO_LARGE, "body_over_limit", prof.name, decision.service, decision.tier),
                )
        finally:
            self.edge.release(decision)
        if overflow:
            self.edge._emit(
                req,
                EdgeDecision(EdgeOutcome.PAYLOAD_TOO_LARGE, "body_stream_over_limit", prof.name, decision.service, decision.tier),
            )


class _BodyOverflow(Exception):
    pass


def install_recovered_systems_edge(app: Any, edge: RecoveredSystemsEdge) -> None:
    """``app.add_middleware(RecoveredSystemsMiddleware, edge=edge)``.

    Starlette runs the last-added middleware outermost: call this *before*
    ``install_s2s_gate`` so the S2S layer verifies tokens first.
    """
    app.add_middleware(RecoveredSystemsMiddleware, edge=edge)


__all__ = [
    "AUDIT_KIND",
    "EDGE_SCOPE_KEY",
    "EdgeDecision",
    "EdgeOutcome",
    "EdgeRequest",
    "RecoveredSystemsEdge",
    "RecoveredSystemsMiddleware",
    "install_recovered_systems_edge",
]
