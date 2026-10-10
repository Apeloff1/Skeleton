"""Hardened s2s gate: correlation, mutual auth, claims policy, per-identity limits.

Evaluation order for one request (each step fails closed)::

    1. correlation        extract_context (request id, trace, hop/via)  -> 508 LOOP_DETECTED
    2. open probe?        AdmissionMatrix.is_open(path)                 -> OPEN_BYPASS
    3. peer identity      PeerExtractor (ASGI TLS ext / trusted XFCC)
    4. token + authz      S2SAuthGate.evaluate with a HardenedVerifier  -> 401 / 403 / 405
                          (claims policy: kid pinning, scope ceilings,
                          freshness, ext claims, cnf / rid binding)
    5. mutual auth        MutualAuthPolicy.evaluate(peer, token issuer)  -> 401 MUTUAL_AUTH_FAILED
    6. signed request     RequestVerifier (optional / required)          -> 401 SIGNATURE_FAILED
    7. rate limit         ServiceRateLimiter by verified identity        -> 429 RATE_LIMITED
    8. admission          gate_plane.admit.evaluate_admission            -> 429 SHED / 503

Admission runs last so traffic rejected by steps 1-7 never spends
AdaptiveGate tokens (the inner ``S2SAuthGate`` is built with
``admission=False``). Everything is opt-in: :func:`install_hardened_gate`
registers the ASGI middleware; ``skeleton/api/server.py`` is not edited.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from skeleton.gate_plane.admit import AdmissionMatrix, AdmissionOutcome, evaluate_admission
from skeleton.gate_plane.hardening.claims import (
    ClaimsPolicy,
    HardenedVerifier,
    VerificationScope,
    verification_scope,
)
from skeleton.gate_plane.hardening.mutual import (
    SIGNATURE_HEADER,
    MutualAuthCode,
    MutualAuthMode,
    MutualAuthPolicy,
    PeerExtractor,
    PeerResult,
    RequestVerifier,
)
from skeleton.gate_plane.hardening.ratelimit import RateDecision, ServiceRateLimiter
from skeleton.gate_plane.hardening.request_id import (
    HopLimitExceeded,
    PropagationPolicy,
    RequestContext,
    bind_context,
    extract_context,
    new_request_id,
    response_headers,
    stamp_asgi_scope,
    TraceParent,
)
from skeleton.gate_plane.s2s.authz import PolicyTable, Principal
from skeleton.gate_plane.s2s.gate import (
    AUTH_SCHEME,
    PRINCIPAL_SCOPE_KEY,
    TOKEN_HEADER,
    S2SAuthGate,
    S2SDecision,
    S2SOutcome,
)
from skeleton.gate_plane.s2s.tokens import TokenVerifier
from skeleton.gate_plane.stack import GateLayer

DEFAULT_MAX_BODY_BYTES = 1_048_576

HARDENED_GATE_LAYER = GateLayer(
    "s2s_hardened",
    "HardenedS2SMiddleware",
    "inner",
    "Request-id/trace propagation, mutual auth, claims policy, per-identity rate limits",
)


class HardenedOutcome(str, Enum):
    OPEN_BYPASS = "open_bypass"
    ALLOW = "allow"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    SHED = "shed"
    EMERGENCY_READ_ONLY = "emergency_read_only"
    LOOP_DETECTED = "loop_detected"
    MUTUAL_AUTH_FAILED = "mutual_auth_failed"
    SIGNATURE_FAILED = "signature_failed"
    RATE_LIMITED = "rate_limited"
    PAYLOAD_TOO_LARGE = "payload_too_large"


_STATUS = {
    HardenedOutcome.OPEN_BYPASS: 200,
    HardenedOutcome.ALLOW: 200,
    HardenedOutcome.UNAUTHENTICATED: 401,
    HardenedOutcome.FORBIDDEN: 403,
    HardenedOutcome.METHOD_NOT_ALLOWED: 405,
    HardenedOutcome.SHED: 429,
    HardenedOutcome.EMERGENCY_READ_ONLY: 503,
    HardenedOutcome.LOOP_DETECTED: 508,
    HardenedOutcome.MUTUAL_AUTH_FAILED: 401,
    HardenedOutcome.SIGNATURE_FAILED: 401,
    HardenedOutcome.RATE_LIMITED: 429,
    HardenedOutcome.PAYLOAD_TOO_LARGE: 413,
}


class SignatureMode(str, Enum):
    OFF = "off"
    OPTIONAL = "optional"
    REQUIRED = "required"


@dataclass(frozen=True)
class HardenedDecision:
    outcome: HardenedOutcome
    reason: str
    context: RequestContext
    principal: Optional[Principal] = None
    policy: Optional[str] = None
    base: Optional[S2SDecision] = None
    peer: Optional[PeerResult] = None
    rate: Optional[RateDecision] = None
    admission: Optional[str] = None
    signature_kid: Optional[str] = None
    headers: Tuple[Tuple[str, str], ...] = ()
    params: Mapping[str, str] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.outcome in (HardenedOutcome.ALLOW, HardenedOutcome.OPEN_BYPASS)

    @property
    def http_status(self) -> int:
        return _STATUS[self.outcome]

    def body(self) -> Dict[str, Any]:
        """Client-safe body: no token material, thumbprints or key ids."""
        out: Dict[str, Any] = {
            "error": self.outcome.value,
            "reason": self.reason,
            "request_id": self.context.request_id,
        }
        if self.base is not None and self.base.authz is not None and self.base.authz.missing_scopes:
            out["missing_scopes"] = list(self.base.authz.missing_scopes)
        if self.rate is not None and self.rate.retry_after_s is not None and not self.rate.allowed:
            out["retry_after_s"] = self.rate.retry_after_s
        return out

    def response_headers(self) -> List[Tuple[str, str]]:
        return list(self.headers) + response_headers(self.context)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "http_status": self.http_status,
            "service": None if self.principal is None else self.principal.service,
            "policy": self.policy,
            "admission": self.admission,
            "peer": None if self.peer is None or self.peer.peer is None else self.peer.peer.source,
            "peer_service": None if self.peer is None else self.peer.service,
            "rate": None if self.rate is None else self.rate.as_dict(),
            "context": self.context.as_dict(),
        }


HardenedHook = Callable[[str, str, HardenedDecision], None]


def _challenge(error: str) -> Tuple[str, str]:
    return ("www-authenticate", f'{AUTH_SCHEME} realm="s2s", error="{error}"')


class HardenedS2SGate:
    """Pure decision engine for the hardened s2s path."""

    def __init__(
        self,
        base: S2SAuthGate,
        *,
        service: Optional[str] = None,
        propagation: Optional[PropagationPolicy] = None,
        extractor: Optional[PeerExtractor] = None,
        mutual: Optional[MutualAuthPolicy] = None,
        request_verifier: Optional[RequestVerifier] = None,
        signature_mode: SignatureMode | str = SignatureMode.OFF,
        limiter: Optional[ServiceRateLimiter] = None,
        admission: bool = True,
        hooks: Iterable[HardenedHook] = (),
    ) -> None:
        if base.admission:
            raise ValueError("pass an S2SAuthGate built with admission=False; the hardened gate admits last")
        self.base = base
        self.service = service
        self.propagation = propagation or PropagationPolicy()
        self.extractor = extractor
        self.mutual = mutual or MutualAuthPolicy()
        self.request_verifier = request_verifier
        self.signature_mode = SignatureMode(signature_mode)
        if self.signature_mode is not SignatureMode.OFF and request_verifier is None:
            raise ValueError("signature_mode requires a request_verifier")
        self.limiter = limiter
        self.admission = bool(admission)
        self._hooks: List[HardenedHook] = list(hooks)

    @property
    def matrix(self) -> AdmissionMatrix:
        return self.base.matrix

    @property
    def needs_body(self) -> bool:
        return self.request_verifier is not None and self.signature_mode is not SignatureMode.OFF

    def add_hook(self, hook: HardenedHook) -> None:
        self._hooks.append(hook)

    def _emit(self, method: str, path: str, decision: HardenedDecision) -> HardenedDecision:
        for hook in self._hooks:
            try:
                hook(method, path, decision)
            except Exception:  # noqa: BLE001 - observers never change verdicts
                pass
        return decision

    def _claims_policy(self) -> Optional[ClaimsPolicy]:
        verifier = self.base.verifier
        return verifier.policy if isinstance(verifier, HardenedVerifier) else None

    def evaluate(
        self,
        method: str,
        path: str,
        headers: Mapping[str, str],
        *,
        scope: Optional[Mapping[str, Any]] = None,
        body: bytes = b"",
        query: str = "",
    ) -> HardenedDecision:
        meth = (method or "GET").upper()
        p = path or "/"
        asgi_scope: Mapping[str, Any] = scope or {}

        try:
            ctx = extract_context(headers, service=self.service, policy=self.propagation)
        except HopLimitExceeded as exc:
            fallback = RequestContext(request_id=new_request_id(), trace=TraceParent.fresh())
            return self._emit(meth, p, HardenedDecision(HardenedOutcome.LOOP_DETECTED, exc.reason, fallback))

        if self.matrix.is_open(p):
            return self._emit(meth, p, HardenedDecision(HardenedOutcome.OPEN_BYPASS, "open_probe", ctx))

        peer = self.extractor.extract(asgi_scope, headers) if self.extractor is not None else PeerResult(
            MutualAuthCode.NO_PEER
        )
        vs = VerificationScope(
            peer_thumbprint=None if peer.peer is None else peer.peer.thumbprint,
            peer_service=peer.service,
            request_id=ctx.request_id,
        )
        with verification_scope(vs):
            base = self.base.evaluate(meth, p, headers)
        if not base.allowed:
            reason = base.reason
            if base.outcome is S2SOutcome.UNAUTHENTICATED and vs.failure is not None:
                reason = vs.failure.value
            return self._emit(
                meth, p,
                HardenedDecision(
                    HardenedOutcome(base.outcome.value), reason, ctx, principal=base.principal,
                    policy=base.policy, base=base, peer=peer, headers=base.headers, params=base.params,
                ),
            )
        principal = base.principal or Principal.anonymous_principal()

        if not principal.anonymous or self.mutual.mode is MutualAuthMode.REQUIRED:
            m_code = self.mutual.evaluate(peer, principal.service)
            if m_code is not MutualAuthCode.OK:
                return self._emit(
                    meth, p,
                    HardenedDecision(
                        HardenedOutcome.MUTUAL_AUTH_FAILED, f"mtls_{m_code.value}", ctx, principal=principal,
                        policy=base.policy, base=base, peer=peer, headers=(_challenge("invalid_client"),),
                    ),
                )

        sig_kid: Optional[str] = None
        if self.request_verifier is not None and self.signature_mode is not SignatureMode.OFF:
            low = {str(k).lower(): str(v) for k, v in headers.items()}
            res = self.request_verifier.verify(
                low.get(SIGNATURE_HEADER), method=meth, path=p, body=body, query=query, request_id=ctx.request_id,
            )
            failed: Optional[str] = None
            if res.code is MutualAuthCode.NO_PEER:
                if self.signature_mode is SignatureMode.REQUIRED:
                    failed = "signature_missing"
            elif not res.ok:
                failed = res.code.value
            else:
                sig_kid = res.kid
                policy = self._claims_policy()
                if (
                    sig_kid is not None
                    and principal.service is not None
                    and policy is not None
                    and not policy.kid_allowed(sig_kid, principal.service)
                ):
                    failed = "signature_kid_not_pinned"
            if failed is not None:
                return self._emit(
                    meth, p,
                    HardenedDecision(
                        HardenedOutcome.SIGNATURE_FAILED, failed, ctx, principal=principal, policy=base.policy,
                        base=base, peer=peer, headers=(_challenge("invalid_signature"),),
                    ),
                )

        rate: Optional[RateDecision] = None
        if self.limiter is not None:
            rate = self.limiter.check(principal.service, base.policy, method=meth)
            if not rate.allowed:
                return self._emit(
                    meth, p,
                    HardenedDecision(
                        HardenedOutcome.RATE_LIMITED, "service_rate_limited", ctx, principal=principal,
                        policy=base.policy, base=base, peer=peer, rate=rate, headers=tuple(rate.headers()),
                    ),
                )

        admission_note: Optional[str] = None
        if self.admission and not principal.anonymous:
            prio = base.authz.priority if base.authz is not None else 1
            adm = evaluate_admission(path=p, method=meth, attester=principal.attester(), priority=prio, matrix=self.matrix)
            admission_note = adm.outcome.value
            if adm.outcome is AdmissionOutcome.SHED:
                return self._emit(
                    meth, p,
                    HardenedDecision(
                        HardenedOutcome.SHED, adm.reason, ctx, principal=principal, policy=base.policy, base=base,
                        peer=peer, rate=rate, admission=admission_note, headers=(("retry-after", "1"),),
                    ),
                )
            if adm.outcome is AdmissionOutcome.EMERGENCY_READ_ONLY:
                return self._emit(
                    meth, p,
                    HardenedDecision(
                        HardenedOutcome.EMERGENCY_READ_ONLY, adm.reason, ctx, principal=principal,
                        policy=base.policy, base=base, peer=peer, rate=rate, admission=admission_note,
                        headers=(("retry-after", "30"),),
                    ),
                )
        rate_headers = tuple(rate.headers()) if rate is not None else ()
        return self._emit(
            meth, p,
            HardenedDecision(
                HardenedOutcome.ALLOW, "ok", ctx, principal=principal, policy=base.policy, base=base, peer=peer,
                rate=rate, admission=admission_note, signature_kid=sig_kid, headers=rate_headers,
                params=base.params,
            ),
        )


def build_hardened_gate(
    verifier: TokenVerifier,
    policies: PolicyTable,
    *,
    claims: Optional[ClaimsPolicy] = None,
    matrix: Optional[AdmissionMatrix] = None,
    **kwargs: Any,
) -> HardenedS2SGate:
    """Compose ``TokenVerifier`` + ``ClaimsPolicy`` + ``PolicyTable`` into a hardened gate."""
    hardened = HardenedVerifier(verifier, claims or ClaimsPolicy())
    base = S2SAuthGate(hardened, policies, matrix=matrix, admission=False)  # type: ignore[arg-type]
    return HardenedS2SGate(base, **kwargs)


ASGIApp = Callable[
    [MutableMapping[str, Any], Callable[[], Awaitable[Any]], Callable[[Any], Awaitable[None]]], Awaitable[None]
]


def _decode_headers(raw: Iterable[Tuple[bytes, bytes]]) -> Tuple[Dict[str, str], bool]:
    out: Dict[str, str] = {}
    conflict = False
    for k, v in raw:
        key = k.decode("latin-1").lower()
        val = v.decode("latin-1")
        if key in out and key in ("authorization", TOKEN_HEADER, SIGNATURE_HEADER) and out[key] != val:
            conflict = True
        out.setdefault(key, val)
    return out, conflict


class HardenedS2SMiddleware:
    """ASGI wrapper for :class:`HardenedS2SGate`.

    * Buffers the request body (bounded by ``max_body_bytes``) only when
      signed requests are enabled, then replays it to the app.
    * Binds the :class:`RequestContext` for the app call so outbound clients
      propagate correlation headers automatically, and echoes
      ``x-request-id`` / ``traceparent`` on every response.
    """

    def __init__(self, app: ASGIApp, *, gate: HardenedS2SGate, max_body_bytes: int = DEFAULT_MAX_BODY_BYTES) -> None:
        self.app = app
        self.gate = gate
        self.max_body_bytes = int(max_body_bytes)

    async def _reject(self, send: Callable[[Any], Awaitable[None]], decision: HardenedDecision) -> None:
        body = json.dumps(decision.body(), sort_keys=True).encode("utf-8")
        hdrs = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        hdrs += [(k.encode("latin-1"), v.encode("latin-1")) for k, v in decision.response_headers()]
        await send({"type": "http.response.start", "status": decision.http_status, "headers": hdrs})
        await send({"type": "http.response.body", "body": body})

    async def __call__(
        self,
        scope: MutableMapping[str, Any],
        receive: Callable[[], Awaitable[Any]],
        send: Callable[[Any], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", "/"))
        query = (scope.get("query_string") or b"").decode("latin-1")
        headers, conflict = _decode_headers(scope.get("headers") or [])

        body = b""
        downstream_receive = receive
        if self.gate.needs_body:
            chunks: List[bytes] = []
            size = 0
            more = True
            while more:
                message = await receive()
                if message.get("type") == "http.disconnect":
                    return
                chunk = message.get("body", b"") or b""
                size += len(chunk)
                if size > self.max_body_bytes:
                    ctx = RequestContext(request_id=new_request_id(), trace=TraceParent.fresh())
                    await self._reject(
                        send, HardenedDecision(HardenedOutcome.PAYLOAD_TOO_LARGE, "body_too_large", ctx)
                    )
                    return
                chunks.append(chunk)
                more = bool(message.get("more_body", False))
            body = b"".join(chunks)
            replayed = False

            async def replay() -> Any:
                nonlocal replayed
                if not replayed:
                    replayed = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            downstream_receive = replay

        if conflict:
            ctx = RequestContext(request_id=new_request_id(), trace=TraceParent.fresh())
            decision = self.gate._emit(
                method, path,
                HardenedDecision(
                    HardenedOutcome.UNAUTHENTICATED, "bad_credentials", ctx, headers=(_challenge("invalid_token"),)
                ),
            )
        else:
            decision = self.gate.evaluate(method, path, headers, scope=scope, body=body, query=query)
        if not decision.allowed:
            await self._reject(send, decision)
            return

        stamp_asgi_scope(scope, decision.context)
        if decision.principal is not None:
            state = scope.setdefault("state", {})
            if isinstance(state, dict):
                state[PRINCIPAL_SCOPE_KEY] = decision.principal
            scope[PRINCIPAL_SCOPE_KEY] = decision.principal
        extra = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in decision.response_headers()]

        async def send_wrapper(message: Any) -> None:
            if message.get("type") == "http.response.start":
                existing = list(message.get("headers") or [])
                names = {k.lower() for k, _ in existing}
                message = dict(message)
                message["headers"] = existing + [(k, v) for k, v in extra if k.lower() not in names]
            await send(message)

        with bind_context(decision.context):
            await self.app(scope, downstream_receive, send_wrapper)


def install_hardened_gate(app: Any, gate: HardenedS2SGate, **kwargs: Any) -> None:
    """Registration hook: ``app.add_middleware(HardenedS2SMiddleware, gate=gate)``."""
    app.add_middleware(HardenedS2SMiddleware, gate=gate, **kwargs)


__all__ = [
    "DEFAULT_MAX_BODY_BYTES",
    "HARDENED_GATE_LAYER",
    "HardenedDecision",
    "HardenedOutcome",
    "HardenedS2SGate",
    "HardenedS2SMiddleware",
    "SignatureMode",
    "build_hardened_gate",
    "install_hardened_gate",
]
