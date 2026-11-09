"""S2S auth gate layered on the Pack B gate plane.

Evaluation order for one request (each layer fails closed)::

    1. open probe?          AdmissionMatrix.is_open(path)        -> OPEN_BYPASS
    2. token present/valid? TokenVerifier.verify(...)            -> 401 UNAUTHENTICATED
    3. route authorized?    PolicyTable.evaluate(...)            -> 403 / 405 FORBIDDEN
    4. admitted?            gate_plane.admit.evaluate_admission  -> 429 SHED / 503 EMERGENCY

Step 4 reuses the Pack B admission matrix with the verified service as the
attester and the matched policy's priority, so s2s callers obey the same
AdaptiveGate / ChaosGovernor ladder as sealed human traffic. When the gate
is installed *behind* ``WriteAdmitMiddleware`` (which already charges the
AdaptiveGate) pass ``admission=False`` to avoid double-charging tokens.

:class:`S2SAuthMiddleware` is a plain ASGI wrapper and is **opt-in**: nothing
here edits ``skeleton/api/server.py``; apps call :func:`install_s2s_gate`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Tuple

from skeleton.gate_plane.admit import AdmissionMatrix, AdmissionOutcome, evaluate_admission
from skeleton.gate_plane.s2s.authz import AuthzReason, PolicyDecision, PolicyTable, Principal
from skeleton.gate_plane.s2s.tokens import TokenError, TokenErrorCode, TokenVerifier, VerifiedToken
from skeleton.gate_plane.stack import GATE_LAYERS, GateLayer

AUTH_SCHEME = "Service"
TOKEN_HEADER = "x-service-token"
PRINCIPAL_SCOPE_KEY = "s2s_principal"

S2S_GATE_LAYER = GateLayer(
    "s2s_auth",
    "S2SAuthMiddleware",
    "inner",
    "Verify signed service token + per-route authZ policy",
)


class S2SOutcome(str, Enum):
    OPEN_BYPASS = "open_bypass"
    ALLOW = "allow"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    SHED = "shed"
    EMERGENCY_READ_ONLY = "emergency_read_only"


_STATUS = {
    S2SOutcome.OPEN_BYPASS: 200,
    S2SOutcome.ALLOW: 200,
    S2SOutcome.UNAUTHENTICATED: 401,
    S2SOutcome.FORBIDDEN: 403,
    S2SOutcome.METHOD_NOT_ALLOWED: 405,
    S2SOutcome.SHED: 429,
    S2SOutcome.EMERGENCY_READ_ONLY: 503,
}


class TokenExtractionError(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def extract_token(headers: Mapping[str, str]) -> Optional[str]:
    """Pull a service token from ``Authorization: Service <t>`` or ``X-Service-Token``.

    Header names are matched case-insensitively. Supplying both with
    different values is rejected (ambiguous credentials are fail-closed).
    """
    lowered = {str(k).lower(): str(v) for k, v in headers.items()}
    from_auth: Optional[str] = None
    auth = lowered.get("authorization")
    if auth is not None:
        scheme, _, value = auth.strip().partition(" ")
        if scheme.lower() == AUTH_SCHEME.lower():
            value = value.strip()
            if not value or " " in value:
                raise TokenExtractionError("malformed Service authorization header")
            from_auth = value
    from_header = lowered.get(TOKEN_HEADER)
    if from_header is not None:
        from_header = from_header.strip()
        if not from_header:
            raise TokenExtractionError("empty x-service-token header")
    if from_auth and from_header and from_auth != from_header:
        raise TokenExtractionError("conflicting service tokens")
    return from_auth or from_header


@dataclass(frozen=True)
class S2SDecision:
    outcome: S2SOutcome
    reason: str
    principal: Optional[Principal] = None
    policy: Optional[str] = None
    token_error: Optional[TokenErrorCode] = None
    authz: Optional[PolicyDecision] = None
    admission: Optional[str] = None
    headers: Tuple[Tuple[str, str], ...] = ()
    params: Mapping[str, str] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.outcome in (S2SOutcome.ALLOW, S2SOutcome.OPEN_BYPASS)

    @property
    def http_status(self) -> int:
        return _STATUS[self.outcome]

    def body(self) -> Dict[str, Any]:
        """Client-safe error body (no token material, no key ids)."""
        out: Dict[str, Any] = {"error": self.outcome.value, "reason": self.reason}
        if self.authz is not None and self.authz.missing_scopes:
            out["missing_scopes"] = list(self.authz.missing_scopes)
        return out

    def as_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "http_status": self.http_status,
            "service": None if self.principal is None else self.principal.service,
            "policy": self.policy,
            "token_error": None if self.token_error is None else self.token_error.value,
            "admission": self.admission,
            "params": dict(self.params),
        }


DecisionHook = Callable[[str, str, S2SDecision], None]


class S2SAuthGate:
    """Pure decision engine combining token verification, authz and admission."""

    def __init__(
        self,
        verifier: TokenVerifier,
        policies: PolicyTable,
        *,
        matrix: Optional[AdmissionMatrix] = None,
        admission: bool = True,
        hooks: Iterable[DecisionHook] = (),
    ) -> None:
        self.verifier = verifier
        self.policies = policies
        self.matrix = matrix if matrix is not None else AdmissionMatrix()
        self.admission = bool(admission)
        self._hooks: List[DecisionHook] = list(hooks)

    def add_hook(self, hook: DecisionHook) -> None:
        self._hooks.append(hook)

    def _emit(self, method: str, path: str, decision: S2SDecision) -> S2SDecision:
        for hook in self._hooks:
            try:
                hook(method, path, decision)
            except Exception:  # noqa: BLE001 - observers must never change the verdict
                pass
        return decision

    def evaluate(self, method: str, path: str, headers: Mapping[str, str]) -> S2SDecision:
        meth = (method or "GET").upper()
        p = path or "/"
        if self.matrix.is_open(p):
            return self._emit(meth, p, S2SDecision(S2SOutcome.OPEN_BYPASS, "open_probe"))

        try:
            raw = extract_token(headers)
        except TokenExtractionError as exc:
            return self._emit(meth, p, self._unauth("bad_credentials", TokenErrorCode.MALFORMED, exc.detail))

        verified: Optional[VerifiedToken] = None
        principal = Principal.anonymous_principal()
        if raw is not None:
            try:
                verified = self.verifier.verify(raw)
            except TokenError as exc:
                return self._emit(meth, p, self._unauth(exc.code.value, exc.code))
            principal = Principal.from_verified(verified)

        authz = self.policies.evaluate(meth, p, principal)
        if not authz.allowed:
            if authz.reason is AuthzReason.ANONYMOUS_FORBIDDEN:
                return self._emit(meth, p, self._unauth("missing_token", None, authz=authz))
            outcome = S2SOutcome.METHOD_NOT_ALLOWED if authz.reason is AuthzReason.METHOD_NOT_ALLOWED else S2SOutcome.FORBIDDEN
            return self._emit(
                meth, p,
                S2SDecision(outcome, authz.reason.value, principal, authz.policy, authz=authz, params=authz.params),
            )

        admission_note: Optional[str] = None
        if self.admission and not principal.anonymous:
            adm = evaluate_admission(
                path=p, method=meth, attester=principal.attester(), priority=authz.priority, matrix=self.matrix
            )
            admission_note = adm.outcome.value
            if adm.outcome is AdmissionOutcome.SHED:
                return self._emit(
                    meth, p,
                    S2SDecision(
                        S2SOutcome.SHED, adm.reason, principal, authz.policy, authz=authz,
                        admission=admission_note, headers=(("retry-after", "1"),), params=authz.params,
                    ),
                )
            if adm.outcome is AdmissionOutcome.EMERGENCY_READ_ONLY:
                return self._emit(
                    meth, p,
                    S2SDecision(
                        S2SOutcome.EMERGENCY_READ_ONLY, adm.reason, principal, authz.policy, authz=authz,
                        admission=admission_note, headers=(("retry-after", "30"),), params=authz.params,
                    ),
                )
        return self._emit(
            meth, p,
            S2SDecision(S2SOutcome.ALLOW, "ok", principal, authz.policy, authz=authz, admission=admission_note, params=authz.params),
        )

    @staticmethod
    def _unauth(
        reason: str,
        code: Optional[TokenErrorCode],
        detail: str = "",
        authz: Optional[PolicyDecision] = None,
    ) -> S2SDecision:
        challenge = f'{AUTH_SCHEME} realm="s2s", error="{"invalid_token" if code else "missing_token"}"'
        return S2SDecision(
            S2SOutcome.UNAUTHENTICATED,
            reason,
            token_error=code,
            authz=authz,
            headers=(("www-authenticate", challenge),),
        )


ASGIApp = Callable[[MutableMapping[str, Any], Callable[[], Awaitable[Any]], Callable[[Any], Awaitable[None]]], Awaitable[None]]


def _decode_headers(raw: Iterable[Tuple[bytes, bytes]]) -> Tuple[Dict[str, str], bool]:
    """Decode ASGI headers; report whether credential headers were repeated with different values."""
    out: Dict[str, str] = {}
    conflict = False
    for k, v in raw:
        key = k.decode("latin-1").lower()
        val = v.decode("latin-1")
        if key in out and key in ("authorization", TOKEN_HEADER) and out[key] != val:
            conflict = True
        out.setdefault(key, val)
    return out, conflict


class S2SAuthMiddleware:
    """ASGI wrapper applying :class:`S2SAuthGate` to HTTP requests."""

    def __init__(self, app: ASGIApp, *, gate: S2SAuthGate) -> None:
        self.app = app
        self.gate = gate

    async def __call__(self, scope: MutableMapping[str, Any], receive: Callable[[], Awaitable[Any]], send: Callable[[Any], Awaitable[None]]) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers, conflict = _decode_headers(scope.get("headers") or [])
        if conflict:
            decision = self.gate._emit(
                str(scope.get("method", "GET")).upper(),
                str(scope.get("path", "/")),
                S2SAuthGate._unauth("bad_credentials", TokenErrorCode.MALFORMED, "repeated credential header"),
            )
        else:
            decision = self.gate.evaluate(scope.get("method", "GET"), scope.get("path", "/"), headers)
        if not decision.allowed:
            body = json.dumps(decision.body(), sort_keys=True).encode("utf-8")
            out_headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
            out_headers += [(k.encode("latin-1"), v.encode("latin-1")) for k, v in decision.headers]
            await send({"type": "http.response.start", "status": decision.http_status, "headers": out_headers})
            await send({"type": "http.response.body", "body": body})
            return
        if decision.principal is not None:
            state = scope.setdefault("state", {})
            if isinstance(state, dict):
                state[PRINCIPAL_SCOPE_KEY] = decision.principal
            scope[PRINCIPAL_SCOPE_KEY] = decision.principal
        await self.app(scope, receive, send)


def install_s2s_gate(app: Any, gate: S2SAuthGate) -> None:
    """Registration hook: ``app.add_middleware(S2SAuthMiddleware, gate=gate)``.

    Starlette runs the last-added middleware outermost, so call this *before*
    ``install_gate`` if s2s auth must sit inside the Pack B seal/admit layers.
    """
    app.add_middleware(S2SAuthMiddleware, gate=gate)


def stack_with_s2s(layers: Tuple[GateLayer, ...] = GATE_LAYERS) -> List[GateLayer]:
    """Gate stack description with the s2s layer placed right after ``auth``."""
    out: List[GateLayer] = []
    inserted = False
    for layer in layers:
        out.append(layer)
        if layer.name == "auth":
            out.append(S2S_GATE_LAYER)
            inserted = True
    if not inserted:
        out.append(S2S_GATE_LAYER)
    return out


__all__ = [
    "AUTH_SCHEME",
    "PRINCIPAL_SCOPE_KEY",
    "S2SAuthGate",
    "S2SAuthMiddleware",
    "S2SDecision",
    "S2SOutcome",
    "S2S_GATE_LAYER",
    "TOKEN_HEADER",
    "TokenExtractionError",
    "extract_token",
    "install_s2s_gate",
    "stack_with_s2s",
]
