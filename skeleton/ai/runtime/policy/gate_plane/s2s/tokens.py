"""Signed service tokens (HMAC-SHA256, kid header) for service-to-service calls.

Wire format (compact, JWS-like but deliberately narrower)::

    base64url(header_json) "." base64url(claims_json) "." base64url(hmac)

* ``header`` = ``{"alg": "HS256", "kid": <kid>, "typ": "s2s+v1"}``; any other
  ``alg``/``typ`` is rejected (no ``none``, no algorithm confusion).
* The MAC covers ``header_b64 + "." + claims_b64`` with the key named by
  ``kid`` in the :class:`~skeleton.gate_plane.s2s.keyring.KeyRing`.
* JSON is canonical (sorted keys, compact separators) so the same claims
  always produce the same token for a given key.

Verification is fail-closed and returns a typed :class:`TokenError` code
so the gate can map failures to stable HTTP responses and metrics labels.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, Iterable, Mapping, Optional, Tuple

from skeleton.gate_plane.s2s.clock import Clock, system_clock
from skeleton.gate_plane.s2s.keyring import KeyRing, KeyState, NoActiveKeyError

ALG = "HS256"
TYP = "s2s+v1"
MAX_TOKEN_BYTES = 4096
DEFAULT_TTL_S = 300.0
MAX_TTL_S = 3600.0
DEFAULT_LEEWAY_S = 5.0
_SERVICE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,62}$")
_SCOPE_RE = re.compile(r"^[a-z][a-z0-9_.:*-]{0,95}$")


class TokenErrorCode(str, Enum):
    MALFORMED = "malformed"
    TOO_LARGE = "too_large"
    BAD_HEADER = "bad_header"
    UNKNOWN_KID = "unknown_kid"
    REVOKED_KID = "revoked_kid"
    EXPIRED_KID = "expired_kid"
    BAD_SIGNATURE = "bad_signature"
    EXPIRED = "expired"
    NOT_YET_VALID = "not_yet_valid"
    BAD_AUDIENCE = "bad_audience"
    BAD_ISSUER = "bad_issuer"
    LIFETIME_EXCEEDED = "lifetime_exceeded"
    REPLAYED = "replayed"
    REVOKED_TOKEN = "revoked_token"
    BAD_CLAIMS = "bad_claims"


class TokenError(Exception):
    def __init__(self, code: TokenErrorCode, detail: str = "") -> None:
        super().__init__(f"{code.value}: {detail}" if detail else code.value)
        self.code = code
        self.detail = detail


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    if not isinstance(text, str) or not text or not re.fullmatch(r"[A-Za-z0-9_-]+", text):
        raise TokenError(TokenErrorCode.MALFORMED, "segment is not base64url")
    pad = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + pad)
    except (binascii.Error, ValueError) as exc:
        raise TokenError(TokenErrorCode.MALFORMED, "segment decode failed") from exc


def canonical_json(obj: Mapping[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def validate_service_name(name: str) -> str:
    if not isinstance(name, str) or not _SERVICE_RE.match(name):
        raise ValueError(f"invalid service name {name!r}")
    return name


def validate_scope(scope: str) -> str:
    if not isinstance(scope, str) or not _SCOPE_RE.match(scope):
        raise ValueError(f"invalid scope {scope!r}")
    return scope


@dataclass(frozen=True)
class ServiceClaims:
    """Claims carried by a service token."""

    iss: str  # calling service
    aud: str  # target service
    scopes: FrozenSet[str]
    iat: float
    nbf: float
    exp: float
    jti: str
    extra: Mapping[str, str] = field(default_factory=dict)

    def to_wire(self) -> Dict[str, Any]:
        wire: Dict[str, Any] = {
            "iss": self.iss,
            "aud": self.aud,
            "scp": sorted(self.scopes),
            "iat": int(self.iat),
            "nbf": int(self.nbf),
            "exp": int(self.exp),
            "jti": self.jti,
        }
        if self.extra:
            wire["ext"] = dict(sorted(self.extra.items()))
        return wire

    @classmethod
    def from_wire(cls, data: Mapping[str, Any]) -> "ServiceClaims":
        try:
            iss = validate_service_name(data["iss"])
            aud = validate_service_name(data["aud"])
            raw_scopes = data.get("scp", [])
            if not isinstance(raw_scopes, list):
                raise ValueError("scp must be a list")
            scopes = frozenset(validate_scope(s) for s in raw_scopes)
            iat, nbf, exp = (data["iat"], data["nbf"], data["exp"])
            for v in (iat, nbf, exp):
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    raise ValueError("time claims must be numeric")
            jti = data["jti"]
            if not isinstance(jti, str) or not (8 <= len(jti) <= 128):
                raise ValueError("jti must be an 8-128 char string")
            ext = data.get("ext", {})
            if not isinstance(ext, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in ext.items()
            ):
                raise ValueError("ext must map str->str")
        except (KeyError, TypeError, ValueError) as exc:
            raise TokenError(TokenErrorCode.BAD_CLAIMS, str(exc)) from exc
        if exp <= nbf or nbf < iat - 1:
            raise TokenError(TokenErrorCode.BAD_CLAIMS, "inconsistent iat/nbf/exp")
        return cls(iss=iss, aud=aud, scopes=scopes, iat=float(iat), nbf=float(nbf), exp=float(exp), jti=jti, extra=ext)

    def has_scope(self, scope: str) -> bool:
        return scope_granted(self.scopes, scope)


def scope_granted(granted: Iterable[str], required: str) -> bool:
    """``required`` is satisfied by an exact scope or a ``prefix:*`` wildcard."""
    for g in granted:
        if g == required:
            return True
        if g.endswith(":*") and required.startswith(g[:-1]):
            return True
    return False


@dataclass(frozen=True)
class VerifiedToken:
    kid: str
    claims: ServiceClaims
    key_state: KeyState

    @property
    def service(self) -> str:
        return self.claims.iss

    @property
    def in_overlap(self) -> bool:
        return self.key_state is KeyState.RETIRING


class ReplayCache:
    """Bounded jti cache; entries expire with their token."""

    def __init__(self, capacity: int = 65_536) -> None:
        self.capacity = int(capacity)
        self._seen: "OrderedDict[str, float]" = OrderedDict()
        self._lock = threading.Lock()

    def check_and_add(self, jti: str, exp: float, now: float) -> bool:
        """Return True when first seen; False on replay."""
        with self._lock:
            self._evict(now)
            if jti in self._seen:
                return False
            self._seen[jti] = exp
            while len(self._seen) > self.capacity:
                self._seen.popitem(last=False)
            return True

    def _evict(self, now: float) -> None:
        stale = [j for j, exp in self._seen.items() if exp <= now]
        for j in stale:
            del self._seen[j]

    def __len__(self) -> int:
        with self._lock:
            return len(self._seen)


class TokenSigner:
    """Mints tokens for ``service`` with the key ring's ACTIVE key."""

    def __init__(
        self,
        service: str,
        keyring: KeyRing,
        *,
        clock: Optional[Clock] = None,
        default_ttl_s: float = DEFAULT_TTL_S,
        jti_factory: Optional[Any] = None,
    ) -> None:
        self.service = validate_service_name(service)
        self.keyring = keyring
        self.clock: Clock = clock if clock is not None else system_clock()
        if not (0 < default_ttl_s <= MAX_TTL_S):
            raise ValueError("default_ttl_s must be in (0, MAX_TTL_S]")
        self.default_ttl_s = float(default_ttl_s)
        self._counter = 0
        self._lock = threading.Lock()
        self._jti_factory = jti_factory

    def _next_jti(self, now: float) -> str:
        if self._jti_factory is not None:
            return str(self._jti_factory())
        with self._lock:
            self._counter += 1
            n = self._counter
        return f"{self.service[:16]}-{int(now)}-{n}-{secrets.token_hex(6)}"

    def mint(
        self,
        audience: str,
        scopes: Iterable[str] = (),
        *,
        ttl_s: Optional[float] = None,
        not_before_s: float = 0.0,
        extra: Optional[Mapping[str, str]] = None,
        kid: Optional[str] = None,
    ) -> str:
        ttl = self.default_ttl_s if ttl_s is None else float(ttl_s)
        if not (0 < ttl <= MAX_TTL_S):
            raise ValueError("ttl_s must be in (0, MAX_TTL_S]")
        now = self.clock.now()
        claims = ServiceClaims(
            iss=self.service,
            aud=validate_service_name(audience),
            scopes=frozenset(validate_scope(s) for s in scopes),
            iat=float(int(now)),
            nbf=float(int(now + max(0.0, not_before_s))),
            exp=float(int(now + max(0.0, not_before_s) + ttl)),
            jti=self._next_jti(now),
            extra=dict(extra or {}),
        )
        if kid is None:
            key = self.keyring.signing_key()
        else:
            key = self.keyring.get(kid)
            if not key.can_sign():
                raise NoActiveKeyError(f"kid {kid!r} is {key.state.value}, not active")
        return encode_token(claims, key.kid, key.secret)


def _mac(secret: bytes, signing_input: bytes) -> bytes:
    return hmac.new(secret, signing_input, hashlib.sha256).digest()


def encode_token(claims: ServiceClaims, kid: str, secret: bytes) -> str:
    header = {"alg": ALG, "kid": kid, "typ": TYP}
    h = b64url_encode(canonical_json(header))
    c = b64url_encode(canonical_json(claims.to_wire()))
    sig = b64url_encode(_mac(secret, f"{h}.{c}".encode("ascii")))
    return f"{h}.{c}.{sig}"


def split_token(token: str) -> Tuple[Dict[str, Any], Dict[str, Any], bytes, bytes]:
    """Parse without verifying. Returns (header, claims, signing_input, sig)."""
    if not isinstance(token, str):
        raise TokenError(TokenErrorCode.MALFORMED, "token must be str")
    if len(token) > MAX_TOKEN_BYTES:
        raise TokenError(TokenErrorCode.TOO_LARGE, f"{len(token)} > {MAX_TOKEN_BYTES}")
    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError(TokenErrorCode.MALFORMED, "expected 3 segments")
    h_raw, c_raw, s_raw = (b64url_decode(p) for p in parts)
    try:
        header = json.loads(h_raw.decode("ascii"))
        claims = json.loads(c_raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TokenError(TokenErrorCode.MALFORMED, "segment is not JSON") from exc
    if not isinstance(header, dict) or not isinstance(claims, dict):
        raise TokenError(TokenErrorCode.MALFORMED, "segments must be JSON objects")
    return header, claims, f"{parts[0]}.{parts[1]}".encode("ascii"), s_raw


class TokenVerifier:
    """Verifies tokens addressed to ``audience`` against a key ring."""

    def __init__(
        self,
        audience: str,
        keyring: KeyRing,
        *,
        clock: Optional[Clock] = None,
        leeway_s: float = DEFAULT_LEEWAY_S,
        max_lifetime_s: float = MAX_TTL_S,
        trusted_issuers: Optional[Iterable[str]] = None,
        replay_cache: Optional[ReplayCache] = None,
        revoked_jtis: Optional[Any] = None,
        accept_pending: bool = False,
    ) -> None:
        self.audience = validate_service_name(audience)
        self.keyring = keyring
        self.clock: Clock = clock if clock is not None else system_clock()
        if leeway_s < 0 or leeway_s > 300:
            raise ValueError("leeway_s must be within [0, 300]")
        self.leeway_s = float(leeway_s)
        self.max_lifetime_s = float(max_lifetime_s)
        self.trusted_issuers = None if trusted_issuers is None else frozenset(trusted_issuers)
        self.replay_cache = replay_cache
        self.revoked_jtis = revoked_jtis
        self.accept_pending = bool(accept_pending)

    def verify(self, token: str) -> VerifiedToken:
        header, raw_claims, signing_input, sig = split_token(token)
        if header.get("alg") != ALG or header.get("typ") != TYP or set(header) != {"alg", "kid", "typ"}:
            raise TokenError(TokenErrorCode.BAD_HEADER, "unsupported alg/typ or extra header fields")
        kid = header.get("kid")
        if not isinstance(kid, str):
            raise TokenError(TokenErrorCode.BAD_HEADER, "kid must be a string")
        key = self.keyring.verification_key(kid, accept_pending=self.accept_pending)
        if key is None:
            state = self.keyring.state_of(kid)
            if state is KeyState.REVOKED:
                raise TokenError(TokenErrorCode.REVOKED_KID, kid)
            if state is KeyState.EXPIRED or state is KeyState.RETIRING:
                raise TokenError(TokenErrorCode.EXPIRED_KID, kid)
            raise TokenError(TokenErrorCode.UNKNOWN_KID, kid)
        if not hmac.compare_digest(_mac(key.secret, signing_input), sig):
            raise TokenError(TokenErrorCode.BAD_SIGNATURE, kid)
        claims = ServiceClaims.from_wire(raw_claims)
        now = self.clock.now()
        if claims.aud != self.audience:
            raise TokenError(TokenErrorCode.BAD_AUDIENCE, claims.aud)
        if self.trusted_issuers is not None and claims.iss not in self.trusted_issuers:
            raise TokenError(TokenErrorCode.BAD_ISSUER, claims.iss)
        if claims.exp - claims.iat > self.max_lifetime_s:
            raise TokenError(TokenErrorCode.LIFETIME_EXCEEDED, f"{claims.exp - claims.iat}s")
        if now >= claims.exp + self.leeway_s:
            raise TokenError(TokenErrorCode.EXPIRED, f"exp={claims.exp}")
        if now + self.leeway_s < claims.nbf:
            raise TokenError(TokenErrorCode.NOT_YET_VALID, f"nbf={claims.nbf}")
        if self.revoked_jtis is not None and self.revoked_jtis.is_revoked(claims.jti, now):
            raise TokenError(TokenErrorCode.REVOKED_TOKEN, claims.jti)
        if self.replay_cache is not None and not self.replay_cache.check_and_add(
            claims.jti, claims.exp + self.leeway_s, now
        ):
            raise TokenError(TokenErrorCode.REPLAYED, claims.jti)
        return VerifiedToken(kid=kid, claims=claims, key_state=key.state)


__all__ = [
    "ALG",
    "DEFAULT_LEEWAY_S",
    "DEFAULT_TTL_S",
    "MAX_TOKEN_BYTES",
    "MAX_TTL_S",
    "ReplayCache",
    "ServiceClaims",
    "TYP",
    "TokenError",
    "TokenErrorCode",
    "TokenSigner",
    "TokenVerifier",
    "VerifiedToken",
    "b64url_decode",
    "b64url_encode",
    "canonical_json",
    "encode_token",
    "scope_granted",
    "split_token",
    "validate_scope",
    "validate_service_name",
]
