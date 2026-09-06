"""API middleware — auth, rate limiting, request ID, and Gate gauntlet.

FastAPI doesn't ship with these; they live here so routes stay thin.

Gate stack (outer → inner), sibling of Zaibatsu.Gate Program.cs::

    RequestSeal → BodyBound → WORM → Auth → PolicyGate

Install with :func:`install_gate` (Starlette LIFO: last added = outermost).
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from skeleton.kernel.errors import KernelError

# ---------------------------------------------------------------------------
# Existing auth / rate-limit primitives (kept for Depends + callers)
# ---------------------------------------------------------------------------


class MiddlewareError(KernelError):
    code = "API.MIDDLEWARE"


class AuthError(MiddlewareError):
    code = "API.AUTH"
    http_status = 401


class RateLimitError(MiddlewareError):
    code = "API.RATE_LIMIT"
    http_status = 429


class BearerAuth:
    """Validates Bearer tokens against a verifier callable."""

    def __init__(self, verifier: Callable[[str], Optional[Dict[str, Any]]]) -> None:
        self.verifier = verifier

    def __call__(self, authorization: Optional[str] = None) -> Dict[str, Any]:
        if not authorization or not authorization.startswith("Bearer "):
            raise AuthError("missing or malformed Bearer token")
        payload = self.verifier(authorization[7:])
        if payload is None:
            raise AuthError("invalid token")
        return payload


class RateLimiter:
    """Token-bucket keyed by arbitrary string (IP, user-id, API key)."""

    def __init__(self, *, capacity: float = 100.0, refill_per_sec: float = 10.0) -> None:
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self._buckets: Dict[str, tuple] = {}

    def check(self, key: str, tokens: float = 1.0) -> None:
        now = time.monotonic()
        current, last = self._buckets.get(key, (self.capacity, now))
        current = min(self.capacity, current + (now - last) * self.refill_per_sec)
        if current < tokens:
            self._buckets[key] = (current, now)
            raise RateLimitError(
                "rate limit exceeded",
                context={"retry_after_s": round((tokens - current) / self.refill_per_sec, 2)},
            )
        self._buckets[key] = (current - tokens, now)


def get_request_id(header_value: Optional[str] = None) -> str:
    """Provide or generate a request correlation id."""
    return header_value or uuid.uuid4().hex[:16]


# ---------------------------------------------------------------------------
# Gate policy map (thin) — fail-closed; unwritten → sealed
# ---------------------------------------------------------------------------

DEFAULT_OPEN_PREFIXES: Tuple[str, ...] = (
    "/health",
    "/ready",
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/metrics",
    "/api/v1/metrics",
)

# Route prefix → governance domain (longest-prefix match).
DEFAULT_DOMAIN_MAP: Tuple[Tuple[str, str], ...] = (
    ("/api/v1/forge", "forge"),
    ("/api/v1/gameforge", "forge"),
    ("/api/v1/swarm", "swarm"),
    ("/api/v1/jeeves", "jeeves"),
    ("/api/v1/memory", "memory"),
    ("/api/v1/retrieval", "retrieval"),
    ("/api/v1/pipeline", "pipeline"),
    ("/api/v1/intelligence", "intelligence"),
    ("/api/v1/resilience", "resilience"),
    ("/api/v1/context", "context"),
    ("/api/v1/ledger", "ledger"),
    ("/api/v1/scheduler", "scheduler"),
    ("/api/v1/genesis", "genesis"),
    ("/api/v1/capabilities", "capabilities"),
    ("/api/v1/interface", "interface"),
    ("/api/v1/auth", "auth"),
    ("/api/v1/cortex", "cognition"),
    ("/api/fabric", "fabric"),
    ("/api/legions", "legions"),
    ("/api/swarm", "swarm"),
    ("/api/governance", "governance"),
    ("/api/cognition", "cognition"),
    ("/api/lafs", "lafs"),
    ("/api/studio", "studio"),
    ("/api/sagas", "fabric"),
    ("/api/court", "court"),
)


class GatePolicy:
    """Charters at the middleware layer — open probes vs written domains.

    Sibling of ``Zaibatsu.Gate.Auth.GatePolicy``: anything not written here
    is sealed (null domain → 404).
    """

    def __init__(
        self,
        *,
        open_prefixes: Sequence[str] = DEFAULT_OPEN_PREFIXES,
        domains: Sequence[Tuple[str, str]] = DEFAULT_DOMAIN_MAP,
    ) -> None:
        self._open = tuple(open_prefixes)
        # Longest prefix first for stable RequiredDomain.
        self._domains = tuple(sorted(domains, key=lambda pd: len(pd[0]), reverse=True))

    def is_open_route(self, path: str) -> bool:
        p = path or "/"
        return any(p == pref or p.startswith(pref.rstrip("/") + "/") or p.startswith(pref)
                   for pref in self._open if pref)

    def required_domain(self, path: str) -> Optional[str]:
        p = path or "/"
        for prefix, domain in self._domains:
            if p == prefix or p.startswith(prefix + "/") or p.startswith(prefix):
                return domain
        return None


# ---------------------------------------------------------------------------
# Gate ASGI middleware layers (outer → inner)
# ---------------------------------------------------------------------------

_DEFAULT_MAX_BODY = 1_048_576  # 1 MiB — Gate:MaxBodyBytes sibling


def _json_response(status: int, body: Dict[str, Any]):
    from starlette.responses import JSONResponse

    return JSONResponse(body, status_code=status)


class RequestSealMiddleware:
    """Outer seal: mint/propagate X-Request-Id; HMAC fail-closed on protected paths.

    Correlation seal always threads. Credential seal (``x-gf-seal`` / #16 HMAC)
    is enforced here for non-open routes: missing/bad → 401; secret unset → 503.
    Open probes skip credential check (health/ready).
    """

    def __init__(self, app, *, policy: Optional[GatePolicy] = None) -> None:
        self.app = app
        self.policy = policy or GatePolicy()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from starlette.requests import Request

        request = Request(scope, receive=receive)
        path = request.url.path
        header_val = request.headers.get("x-request-id")
        seal = get_request_id(header_val if header_val and len(header_val) <= 128 else None)
        scope.setdefault("state", {})
        # Starlette request.state is a State object once bound; stash on scope.
        if "state" not in scope or not hasattr(scope.get("state", None), "seal"):
            pass
        request.state.seal = seal
        request.state.attester = None

        async def send_with_seal(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", seal.encode("utf-8")))
                message = {**message, "headers": headers}
            await send(message)

        if self.policy.is_open_route(path):
            await self.app(scope, receive, send_with_seal)
            return

        # Fail-closed credential seal (#16 HMAC) on non-open routes.
        from skeleton.api.hmac_seal import _resolve_secret, verify_seal

        if not _resolve_secret():
            resp = _json_response(503, {"error": "seal_unavailable"})
            await resp(scope, receive, send_with_seal)
            return
        try:
            attester = verify_seal(request.headers.get("x-gf-seal"))
        except AuthError:
            resp = _json_response(401, {"error": "invalid_seal"})
            await resp(scope, receive, send_with_seal)
            return
        request.state.attester = attester
        await self.app(scope, receive, send_with_seal)


class BodyBoundMiddleware:
    """Reject oversized bodies with 413 — empire does not read unbounded scrolls."""

    def __init__(self, app, *, max_body_bytes: Optional[int] = None) -> None:
        self.app = app
        env = os.environ.get("SKELETON_GATE_MAX_BODY_BYTES")
        self.max_body = (
            int(env) if env else (max_body_bytes if max_body_bytes is not None else _DEFAULT_MAX_BODY)
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        cl = headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > self.max_body:
                    resp = _json_response(
                        413, {"error": "scroll_too_large", "limit": self.max_body}
                    )
                    await resp(scope, receive, send)
                    return
            except ValueError:
                pass
        await self.app(scope, receive, send)


class WormAuditMiddleware:
    """WORM-before-service: append + verify_chain_or_refuse; audit-fail → 503.

    Reuses #22 ``skeleton.vault.audit.AuditLog`` — does not fork the chain.
    """

    def __init__(self, app, *, audit_log: Any = None) -> None:
        self.app = app
        self._audit = audit_log  # injected for tests; else open_default lazy

    def _log(self):
        if self._audit is not None:
            return self._audit
        from skeleton.vault.audit import AuditLog

        self._audit = AuditLog()  # in-memory when no path; tests inject durable
        return self._audit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from starlette.requests import Request
        from skeleton.vault.audit import AuditChainBroken

        request = Request(scope, receive=receive)
        seal = getattr(request.state, "seal", None) or "unsealed"
        attester = getattr(request.state, "attester", None) or "anonymous"
        try:
            log = self._log()
            log.append(
                entry_id=seal,
                actor=attester,
                action="request",
                subject_key=seal,
                outcome="admit",
                metadata={
                    "route": f"{request.method} {request.url.path}",
                    "seal": seal,
                },
            )
            log.verify_chain_or_refuse()
        except AuditChainBroken:
            resp = _json_response(503, {"error": "audit_unavailable"})
            await resp(scope, receive, send)
            return
        except Exception:
            resp = _json_response(503, {"error": "audit_unavailable"})
            await resp(scope, receive, send)
            return
        await self.app(scope, receive, send)


class AuthMiddleware:
    """Principal identity from verified seal — never self-declared JSON.

    Attester already verified by RequestSeal (#16 HMAC). Stamps
    ``X-Zaibatsu-Attester`` for downstream; anonymous open routes pass.
    """

    def __init__(self, app, *, policy: Optional[GatePolicy] = None) -> None:
        self.app = app
        self.policy = policy or GatePolicy()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from starlette.requests import Request

        request = Request(scope, receive=receive)
        if self.policy.is_open_route(request.url.path):
            await self.app(scope, receive, send)
            return
        attester = getattr(request.state, "attester", None)
        if not attester:
            resp = _json_response(401, {"error": "seal_required"})
            await resp(scope, receive, send)
            return
        # Propagate verified identity into scope headers for handlers.
        raw = list(scope.get("headers") or [])
        raw = [(k, v) for k, v in raw if k.lower() != b"x-zaibatsu-attester"]
        raw.append((b"x-zaibatsu-attester", attester.encode("utf-8")))
        scope["headers"] = raw
        await self.app(scope, receive, send)


class PolicyGateMiddleware:
    """Innermost policy: open → pass; null domain → 404 sealed; else admit."""

    def __init__(
        self,
        app,
        *,
        policy: Optional[GatePolicy] = None,
        audit_log: Any = None,
    ) -> None:
        self.app = app
        self.policy = policy or GatePolicy()
        self._audit = audit_log

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from starlette.requests import Request

        request = Request(scope, receive=receive)
        path = request.url.path
        if self.policy.is_open_route(path):
            await self.app(scope, receive, send)
            return

        domain = self.policy.required_domain(path)
        seal = getattr(request.state, "seal", None) or "unsealed"
        if domain is None:
            if self._audit is not None:
                try:
                    self._audit.append(
                        entry_id=f"deny-{seal}",
                        actor="gate",
                        action="deny",
                        subject_key=seal,
                        outcome="denied",
                        metadata={"route": path, "reason": "unwritten"},
                    )
                except Exception:
                    pass
            resp = _json_response(404, {"error": "unwritten_route"})
            await resp(scope, receive, send)
            return
        request.state.gate_domain = domain
        await self.app(scope, receive, send)


def install_gate(
    app,
    *,
    policy: Optional[GatePolicy] = None,
    audit_log: Any = None,
    max_body_bytes: Optional[int] = None,
) -> Any:
    """Wire Gate stack outer→inner onto a Starlette/FastAPI app.

    Starlette ``add_middleware`` is LIFO: the last registered runs first.
    """
    policy = policy or GatePolicy()
    # Innermost first:
    app.add_middleware(PolicyGateMiddleware, policy=policy, audit_log=audit_log)
    app.add_middleware(AuthMiddleware, policy=policy)
    app.add_middleware(WormAuditMiddleware, audit_log=audit_log)
    app.add_middleware(BodyBoundMiddleware, max_body_bytes=max_body_bytes)
    app.add_middleware(RequestSealMiddleware, policy=policy)
    return app
