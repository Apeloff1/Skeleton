"""API middleware — auth, rate limiting, request ID, and Gate gauntlet.

FastAPI doesn't ship with these; they live here so routes stay thin.

Gate stack (outer → inner), sibling of Zaibatsu.Gate Program.cs::

    HeaderBound → RequestSeal → WriteAdmit → BodyBound → WORM → Auth → PolicyGate

Install with :func:`install_gate` (Starlette LIFO: last added = outermost).
"""

from __future__ import annotations

import math
import os
import re
import threading
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


def _positive_finite(value: object, name: str) -> float:
    """Reject bools; ``float(True)`` must not become a 1.0 capacity/refill."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive finite number")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return number


class RateLimiter:
    """Thread-safe token bucket keyed by arbitrary string (IP, user-id, API key)."""

    _MIN_SWEEP_INTERVAL_S = 1.0

    def __init__(self, *, capacity: float = 100.0, refill_per_sec: float = 10.0) -> None:
        self.capacity = _positive_finite(capacity, "capacity")
        self.refill_per_sec = _positive_finite(refill_per_sec, "refill_per_sec")
        self._buckets: Dict[str, Tuple[float, float]] = {}
        self._lock = threading.Lock()
        self._last_sweep: Optional[float] = None
        self._sweep_interval_s = max(
            self._MIN_SWEEP_INTERVAL_S,
            self.capacity / self.refill_per_sec,
        )

    def _sweep(self, now: float) -> None:
        """Drop keys whose buckets have fully refilled back to capacity."""
        last_sweep = self._last_sweep
        if last_sweep is not None and now - last_sweep < self._sweep_interval_s:
            return
        stale = [
            key
            for key, (current, last) in self._buckets.items()
            if current
            + max(0.0, now - last) * self.refill_per_sec
            >= self.capacity
        ]
        for key in stale:
            self._buckets.pop(key, None)
        self._last_sweep = now

    def check(self, key: str, tokens: float = 1.0) -> None:
        if isinstance(tokens, bool) or not isinstance(tokens, (int, float)):
            raise ValueError("tokens must be finite, positive, and no greater than capacity")
        amount = float(tokens)
        if not math.isfinite(amount) or not 0 < amount <= self.capacity:
            raise ValueError("tokens must be finite, positive, and no greater than capacity")
        tokens = amount
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            current, last = self._buckets.get(key, (self.capacity, now))
            elapsed = max(0.0, now - last)
            current = min(self.capacity, current + elapsed * self.refill_per_sec)
            if current < tokens:
                self._buckets[key] = (current, now)
                raise RateLimitError(
                    "rate limit exceeded",
                    context={
                        "retry_after_s": round(
                            (tokens - current) / self.refill_per_sec,
                            2,
                        )
                    },
                )
            self._buckets[key] = (current - tokens, now)


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def get_request_id(header_value: Optional[str] = None) -> str:
    """Provide one normalized request correlation ID or mint a safe one."""
    if isinstance(header_value, str) and _REQUEST_ID_RE.fullmatch(header_value):
        return header_value
    return uuid.uuid4().hex[:16]


# ---------------------------------------------------------------------------
# Gate policy map (thin) — fail-closed; unwritten → sealed
# ---------------------------------------------------------------------------

DEFAULT_OPEN_PREFIXES: Tuple[str, ...] = (
    "/health",
    "/ready",
    "/api/v1/health/live",
    "/api/v1/health/ready",
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
    ("/api/v1/engine", "engine"),
    ("/api/v1/resilience", "resilience"),
    ("/api/v1/context", "context"),
    ("/api/v1/ledger", "ledger"),
    ("/api/v1/scheduler", "scheduler"),
    ("/api/v1/genesis", "genesis"),
    ("/api/v1/application", "application"),
    ("/api/v1/capabilities", "capabilities"),
    ("/api/v1/interface", "interface"),
    ("/api/v1/auth", "auth"),
    ("/api/v1/cortex", "cognition"),
    ("/api/v1/health", "observability"),
    ("/api/v1/metrics", "observability"),
    ("/api/fabric", "fabric"),
    ("/api/legions", "legions"),
    ("/api/swarm", "swarm"),
    ("/api/governance", "governance"),
    ("/api/cognition", "cognition"),
    ("/api/lafs", "lafs"),
    ("/api/studio", "studio"),
    ("/api/sagas", "fabric"),
    ("/api/court", "court"),
    ("/cortex", "cognition"),
    ("/cockpit", "interface"),
    ("/docs", "interface"),
    ("/openapi.json", "interface"),
    ("/redoc", "interface"),
)


def _matches_path_prefix(path: str, prefix: str) -> bool:
    """Match an exact route or a true child route, never a lookalike prefix.

    Security decisions must respect URL path-segment boundaries: ``/health``
    may match ``/health/live`` but must not match ``/healthcare``.  The root
    path is exact-only so configuring ``/`` cannot accidentally unseal the
    entire application.
    """

    p = path or "/"
    pref = (prefix or "").rstrip("/") or "/"
    if pref == "/":
        return p == "/"
    return p == pref or p.startswith(pref + "/")


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
        return any(pref and _matches_path_prefix(path, pref) for pref in self._open)

    def required_domain(self, path: str) -> Optional[str]:
        for prefix, domain in self._domains:
            if prefix and _matches_path_prefix(path, prefix):
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
        request_ids = request.headers.getlist("x-request-id")
        header_val = request_ids[0] if len(request_ids) == 1 else None
        seal = get_request_id(header_val)
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


class _BodyLimitExceeded(Exception):
    pass


class BodyBoundMiddleware:
    """Reject bodies that exceed the configured limit, including streamed bodies."""

    def __init__(self, app, *, max_body_bytes: Optional[int] = None) -> None:
        self.app = app
        from skeleton.api.request_bounds import _positive_limit

        self.max_body = _positive_limit(
            "SKELETON_GATE_MAX_BODY_BYTES",
            max_body_bytes,
            _DEFAULT_MAX_BODY,
        )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # ASGI already gives us byte headers. Scan only for the one value we
        # need instead of allocating and decoding a complete header mapping on
        # every request.
        cl = None
        for key, value in scope.get("headers") or ():
            if key == b"content-length" or key.lower() == b"content-length":
                cl = value
                break
        if cl is not None:
            try:
                declared = int(cl)
            except ValueError:
                resp = _json_response(400, {"error": "invalid_content_length"})
                await resp(scope, receive, send)
                return
            if declared < 0:
                resp = _json_response(400, {"error": "invalid_content_length"})
                await resp(scope, receive, send)
                return
            if declared > self.max_body:
                resp = _json_response(
                    413, {"error": "scroll_too_large", "limit": self.max_body}
                )
                await resp(scope, receive, send)
                return

        seen = 0

        async def bounded_receive():
            nonlocal seen
            message = await receive()
            if message.get("type") == "http.request":
                seen += len(message.get("body") or b"")
                if seen > self.max_body:
                    raise _BodyLimitExceeded
            return message

        try:
            await self.app(scope, bounded_receive, send)
        except _BodyLimitExceeded:
            resp = _json_response(
                413, {"error": "scroll_too_large", "limit": self.max_body}
            )
            await resp(scope, receive, send)


class WormAuditMiddleware:
    """WORM-before-service: append a hash-linked event; audit-fail → 503.

    ``AuditLog`` verifies durable history when it is restored/opened, and
    ``append`` computes the new hash link before publishing the new head. A
    second full-chain scan after every request made total request-path hashing
    quadratic in the number of audit entries, so full verification remains an
    explicit boot/diagnostic operation rather than per-request work.
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
    write_gate: Any = None,
    write_governor: Any = None,
) -> Any:
    """Wire Gate stack outer→inner onto a Starlette/FastAPI app.

    Starlette ``add_middleware`` is LIFO: the last registered runs first.

    Order (outer → inner), sibling of Zaibatsu.Gate + gf-server admit_write::

        HeaderBound → RequestSeal → WriteAdmit → BodyBound → WORM → Auth → PolicyGate
    """
    from skeleton.api.admit_write import WriteAdmitMiddleware
    from skeleton.api.request_bounds import HeaderBoundMiddleware

    policy = policy or GatePolicy()
    # Innermost first:
    app.add_middleware(PolicyGateMiddleware, policy=policy, audit_log=audit_log)
    app.add_middleware(AuthMiddleware, policy=policy)
    app.add_middleware(WormAuditMiddleware, audit_log=audit_log)
    app.add_middleware(BodyBoundMiddleware, max_body_bytes=max_body_bytes)
    app.add_middleware(
        WriteAdmitMiddleware,
        policy=policy,
        gate=write_gate,
        governor=write_governor,
    )
    app.add_middleware(RequestSealMiddleware, policy=policy)
    app.add_middleware(HeaderBoundMiddleware)
    return app