"""Stricter service-token claim policy layered on :class:`TokenVerifier`.

:class:`TokenVerifier` already enforces signature, ``aud`` == this service,
an optional trusted-issuer set, lifetime, expiry, revocation and replay.
:class:`ClaimsPolicy` adds the checks a hardened mesh wants on top:

* **kid pinning** — with per-service keys (``kid`` = ``<issuer>:<n>``) a key
  may only mint tokens for its own issuer, so one leaked service key cannot
  impersonate another service.
* **scope ceilings** — the maximum scopes an issuer may ever carry; a token
  claiming more is rejected outright (not silently trimmed).
* **freshness** — ``now - iat`` bounded independently of ``exp`` so a long
  TTL token cannot be parked and used much later.
* **required / constrained ``ext`` claims** — e.g. ``tenant`` must be present
  and drawn from an allowed set.
* **holder binding** — ``ext.cnf`` carries the caller's certificate
  thumbprint (RFC 8705 ``x5t#S256`` semantics); when present, or required,
  it must match the mutually-authenticated peer for this request.
* **request binding** — ``ext.rid`` (optional) must equal the inbound
  ``x-request-id``, pinning a token to a single logical request.

:class:`HardenedVerifier` is a drop-in ``verifier`` for
:class:`~skeleton.gate_plane.s2s.gate.S2SAuthGate`; per-request peer and
request-id facts reach it through :func:`verification_scope` (a context
variable), so the existing gate code is reused unchanged.
"""

from __future__ import annotations

import base64
import binascii
import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Iterable, Iterator, Mapping, Optional

from skeleton.gate_plane.s2s.tokens import (
    TokenError,
    TokenErrorCode,
    TokenVerifier,
    VerifiedToken,
    scope_granted,
    validate_service_name,
)

CNF_CLAIM = "cnf"
RID_CLAIM = "rid"


class HardeningCode(str, Enum):
    KID_NOT_PINNED = "kid_not_pinned"
    SCOPE_CEILING = "scope_ceiling"
    STALE_TOKEN = "stale_token"
    MISSING_CLAIM = "missing_claim"
    BAD_CLAIM_VALUE = "bad_claim_value"
    BINDING_REQUIRED = "binding_required"
    BINDING_MISMATCH = "binding_mismatch"
    REQUEST_ID_MISMATCH = "request_id_mismatch"
    PEER_IDENTITY_MISMATCH = "peer_identity_mismatch"
    PEER_REQUIRED = "peer_required"


class HardeningError(TokenError):
    """A token that verified cryptographically but failed hardening policy.

    ``code`` stays a :class:`TokenErrorCode` (``BAD_CLAIMS``) so existing gate
    and metrics mapping keep working; ``hardening_code`` carries the detail.
    """

    def __init__(self, code: HardeningCode, detail: str = "") -> None:
        super().__init__(TokenErrorCode.BAD_CLAIMS, f"{code.value}: {detail}" if detail else code.value)
        self.hardening_code = code


def normalize_thumbprint(value: str) -> str:
    """Return a lowercase hex SHA-256 thumbprint from hex or base64url input."""
    if not isinstance(value, str) or not value:
        raise ValueError("thumbprint must be a non-empty string")
    v = value.strip()
    if ":" in v:
        v = v.replace(":", "")
    if len(v) == 64:
        try:
            int(v, 16)
            return v.lower()
        except ValueError:
            pass
    try:
        raw = base64.urlsafe_b64decode(v + "=" * (-len(v) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ValueError("thumbprint is neither hex nor base64url") from exc
    if len(raw) != 32:
        raise ValueError("thumbprint must be a SHA-256 digest")
    return raw.hex()


def thumbprint_b64url(hex_thumbprint: str) -> str:
    return base64.urlsafe_b64encode(bytes.fromhex(normalize_thumbprint(hex_thumbprint))).rstrip(b"=").decode()


@dataclass
class VerificationScope:
    """Per-request facts for :class:`HardenedVerifier` plus its outcome."""

    peer_thumbprint: Optional[str] = None
    peer_service: Optional[str] = None
    request_id: Optional[str] = None
    verified: Optional[VerifiedToken] = None
    failure: Optional[HardeningCode] = None
    failure_detail: str = ""

    def record_failure(self, code: HardeningCode, detail: str) -> None:
        self.failure = code
        self.failure_detail = detail


_SCOPE: contextvars.ContextVar[Optional[VerificationScope]] = contextvars.ContextVar(
    "gate_plane_verification_scope", default=None
)


def current_scope() -> Optional[VerificationScope]:
    return _SCOPE.get()


@contextmanager
def verification_scope(scope: Optional[VerificationScope] = None) -> Iterator[VerificationScope]:
    s = scope or VerificationScope()
    token = _SCOPE.set(s)
    try:
        yield s
    finally:
        _SCOPE.reset(token)


@dataclass(frozen=True)
class ClaimsPolicy:
    pin_kids_to_issuer: bool = False
    kid_owners: Mapping[str, str] = field(default_factory=dict)
    scope_ceilings: Mapping[str, FrozenSet[str]] = field(default_factory=dict)
    default_scope_ceiling: Optional[FrozenSet[str]] = None
    max_token_age_s: Optional[float] = None
    required_ext: FrozenSet[str] = frozenset()
    ext_allowed_values: Mapping[str, FrozenSet[str]] = field(default_factory=dict)
    require_binding: bool = False
    require_binding_for: FrozenSet[str] = frozenset()
    enforce_binding_when_present: bool = True
    bind_request_id: bool = True

    @classmethod
    def build(
        cls,
        *,
        pin_kids_to_issuer: bool = False,
        kid_owners: Optional[Mapping[str, str]] = None,
        scope_ceilings: Optional[Mapping[str, Iterable[str]]] = None,
        default_scope_ceiling: Optional[Iterable[str]] = None,
        max_token_age_s: Optional[float] = None,
        required_ext: Iterable[str] = (),
        ext_allowed_values: Optional[Mapping[str, Iterable[str]]] = None,
        require_binding: bool = False,
        require_binding_for: Iterable[str] = (),
        enforce_binding_when_present: bool = True,
        bind_request_id: bool = True,
    ) -> "ClaimsPolicy":
        if max_token_age_s is not None and max_token_age_s <= 0:
            raise ValueError("max_token_age_s must be > 0")
        owners = {str(k): validate_service_name(v) for k, v in (kid_owners or {}).items()}
        ceilings = {validate_service_name(k): frozenset(v) for k, v in (scope_ceilings or {}).items()}
        return cls(
            pin_kids_to_issuer=bool(pin_kids_to_issuer),
            kid_owners=owners,
            scope_ceilings=ceilings,
            default_scope_ceiling=None if default_scope_ceiling is None else frozenset(default_scope_ceiling),
            max_token_age_s=max_token_age_s,
            required_ext=frozenset(required_ext),
            ext_allowed_values={k: frozenset(v) for k, v in (ext_allowed_values or {}).items()},
            require_binding=bool(require_binding),
            require_binding_for=frozenset(validate_service_name(s) for s in require_binding_for),
            enforce_binding_when_present=bool(enforce_binding_when_present),
            bind_request_id=bool(bind_request_id),
        )

    def binding_required(self, issuer: str) -> bool:
        return self.require_binding or issuer in self.require_binding_for

    def ceiling_for(self, issuer: str) -> Optional[FrozenSet[str]]:
        return self.scope_ceilings.get(issuer, self.default_scope_ceiling)

    def kid_allowed(self, kid: str, issuer: str) -> bool:
        owner = self.kid_owners.get(kid)
        if owner is not None:
            return owner == issuer
        if not self.pin_kids_to_issuer:
            return True
        return kid.startswith(f"{issuer}:") or kid.startswith(f"{issuer}.")

    def check(self, verified: VerifiedToken, *, now: float, scope: Optional[VerificationScope]) -> None:
        """Raise :class:`HardeningError` when ``verified`` violates the policy."""
        claims = verified.claims
        iss = claims.iss
        if not self.kid_allowed(verified.kid, iss):
            raise HardeningError(HardeningCode.KID_NOT_PINNED, f"kid does not belong to {iss}")
        ceiling = self.ceiling_for(iss)
        if ceiling is not None:
            over = sorted(s for s in claims.scopes if not scope_granted(ceiling, s))
            if over:
                raise HardeningError(HardeningCode.SCOPE_CEILING, ",".join(over))
        if self.max_token_age_s is not None and now - claims.iat > self.max_token_age_s:
            raise HardeningError(HardeningCode.STALE_TOKEN, f"age {now - claims.iat:.0f}s")
        ext = dict(claims.extra)
        for key in sorted(self.required_ext):
            if not ext.get(key):
                raise HardeningError(HardeningCode.MISSING_CLAIM, key)
        for key, allowed in self.ext_allowed_values.items():
            if key in ext and ext[key] not in allowed:
                raise HardeningError(HardeningCode.BAD_CLAIM_VALUE, key)
        self._check_binding(iss, ext, scope)
        if self.bind_request_id and RID_CLAIM in ext:
            rid = None if scope is None else scope.request_id
            if rid is None or rid != ext[RID_CLAIM]:
                raise HardeningError(HardeningCode.REQUEST_ID_MISMATCH, "token bound to another request")

    def _check_binding(self, iss: str, ext: Mapping[str, str], scope: Optional[VerificationScope]) -> None:
        cnf = ext.get(CNF_CLAIM)
        peer = None if scope is None else scope.peer_thumbprint
        required = self.binding_required(iss)
        if cnf is None:
            if required:
                raise HardeningError(HardeningCode.BINDING_REQUIRED, "token has no cnf claim")
            return
        if not (required or self.enforce_binding_when_present):
            return
        if peer is None:
            raise HardeningError(HardeningCode.PEER_REQUIRED, "bound token presented without a peer certificate")
        try:
            want = normalize_thumbprint(cnf)
            have = normalize_thumbprint(peer)
        except ValueError as exc:
            raise HardeningError(HardeningCode.BAD_CLAIM_VALUE, f"cnf: {exc}") from None
        if want != have:
            raise HardeningError(HardeningCode.BINDING_MISMATCH, "peer certificate does not match cnf")
        if scope is not None and scope.peer_service is not None and scope.peer_service != iss:
            raise HardeningError(HardeningCode.PEER_IDENTITY_MISMATCH, f"peer {scope.peer_service} != iss {iss}")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "pin_kids_to_issuer": self.pin_kids_to_issuer,
            "kid_owners": dict(sorted(self.kid_owners.items())),
            "scope_ceilings": {k: sorted(v) for k, v in sorted(self.scope_ceilings.items())},
            "default_scope_ceiling": None if self.default_scope_ceiling is None else sorted(self.default_scope_ceiling),
            "max_token_age_s": self.max_token_age_s,
            "required_ext": sorted(self.required_ext),
            "ext_allowed_values": {k: sorted(v) for k, v in sorted(self.ext_allowed_values.items())},
            "require_binding": self.require_binding,
            "require_binding_for": sorted(self.require_binding_for),
            "enforce_binding_when_present": self.enforce_binding_when_present,
            "bind_request_id": self.bind_request_id,
        }


class HardenedVerifier:
    """``TokenVerifier`` decorator applying a :class:`ClaimsPolicy`.

    Exposes ``verify(token)`` so it can be handed to ``S2SAuthGate`` as its
    verifier. Successful verifications and hardening failures are written
    to the active :class:`VerificationScope` (if any) so the hardened gate
    can report precise reasons and rate-limit by verified identity.
    """

    def __init__(self, inner: TokenVerifier, policy: Optional[ClaimsPolicy] = None) -> None:
        self.inner = inner
        self.policy = policy or ClaimsPolicy()
        self.audience = inner.audience
        self.clock = inner.clock

    def verify(self, token: str) -> VerifiedToken:
        scope = current_scope()
        verified = self.inner.verify(token)
        try:
            self.policy.check(verified, now=self.clock.now(), scope=scope)
        except HardeningError as exc:
            if scope is not None:
                scope.record_failure(exc.hardening_code, exc.detail)
            raise
        if scope is not None:
            scope.verified = verified
        return verified


def bound_extra(
    *,
    thumbprint: Optional[str] = None,
    request_id: Optional[str] = None,
    extra: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    """``extra`` claims for :meth:`TokenSigner.mint` carrying cnf / rid bindings."""
    out = dict(extra or {})
    if thumbprint is not None:
        out[CNF_CLAIM] = thumbprint_b64url(thumbprint)
    if request_id is not None:
        out[RID_CLAIM] = request_id
    return out


__all__ = [
    "CNF_CLAIM",
    "ClaimsPolicy",
    "HardenedVerifier",
    "HardeningCode",
    "HardeningError",
    "RID_CLAIM",
    "VerificationScope",
    "bound_extra",
    "current_scope",
    "normalize_thumbprint",
    "thumbprint_b64url",
    "verification_scope",
]
