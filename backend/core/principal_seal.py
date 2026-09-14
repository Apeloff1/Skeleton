"""Verified edge identity and fail-closed route admission primitives.

This module selectively promotes the strongest identity/policy ideas from the
GameForge middleware gate without importing ASP.NET, YARP, or a second HTTP
stack.  It is deliberately framework-free so FastAPI middleware, workers, the
Jeeves control plane, and future gateways can share one verification contract.

Design goals
------------
* Identity is cryptographically verified, never trusted from request JSON.
* Credentials are versioned, bounded, expiring, key-id addressed, and signed
  with HMAC-SHA256 using constant-time comparison.
* A verifier may carry several live keys so key rotation does not require a
  flag day; issuance selects one explicit current key.
* Route policy is fail-closed: only explicit open routes or explicit domain
  mappings are written policy. Unknown routes remain sealed.
* Route matching is segment-aware so ``/api/studioevil`` cannot inherit the
  policy for ``/api/studio``.
* The module does not enable authentication globally by itself. Wiring remains
  an explicit deployment/product decision and can therefore be rolled out
  without accidentally sealing legacy endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re
import time
from typing import Mapping, Sequence

SEAL_VERSION = "v1"
SEAL_ALGORITHM = "hmac-sha256"
MIN_KEY_BYTES = 32
MAX_ID_LENGTH = 96
MAX_SEAL_LENGTH = 1024
DEFAULT_MAX_TTL_SECONDS = 3600
DEFAULT_CLOCK_SKEW_SECONDS = 30

_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PrincipalSealError(ValueError):
    """Base class for malformed or unverifiable principal credentials."""


class SealConfigurationError(PrincipalSealError):
    """Raised when a verifier/issuer is configured unsafely."""


class SealMalformed(PrincipalSealError):
    """Raised when a credential cannot be parsed canonically."""


class SealUnknownKey(PrincipalSealError):
    """Raised when the credential references a key not in the live keyring."""


class SealExpired(PrincipalSealError):
    """Raised when the credential is outside its accepted validity window."""


class SealSignatureInvalid(PrincipalSealError):
    """Raised when the credential signature does not verify."""


@dataclass(frozen=True, slots=True)
class VerifiedPrincipal:
    """Identity produced only after successful credential verification."""

    principal_id: str
    attester_id: str
    key_id: str
    issued_at: int
    expires_at: int
    algorithm: str = SEAL_ALGORITHM
    version: str = SEAL_VERSION

    @property
    def ttl_seconds(self) -> int:
        return self.expires_at - self.issued_at


@dataclass(frozen=True, slots=True)
class RouteRule:
    """One explicit route prefix mapped to a governance domain."""

    prefix: str
    domain: str


@dataclass(frozen=True, slots=True)
class RouteAdmission:
    """Framework-neutral result of route + identity admission."""

    allowed: bool
    status_code: int
    reason: str
    domain: str | None = None
    principal_id: str | None = None
    attester_id: str | None = None
    open_route: bool = False


def _bounded_id(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SealMalformed(f"{field} is required")
    if len(normalized) > MAX_ID_LENGTH:
        raise SealMalformed(f"{field} exceeds {MAX_ID_LENGTH} characters")
    if not _ID_RE.fullmatch(normalized):
        raise SealMalformed(f"{field} contains unsupported characters")
    return normalized


def _coerce_keyring(keys: Mapping[str, bytes | bytearray | memoryview]) -> dict[str, bytes]:
    if not keys:
        raise SealConfigurationError("principal seal keyring cannot be empty")
    normalized: dict[str, bytes] = {}
    for raw_id, raw_key in keys.items():
        key_id = _bounded_id(str(raw_id), field="key_id")
        try:
            key = bytes(raw_key)
        except (TypeError, ValueError) as exc:
            raise SealConfigurationError(f"key '{key_id}' is not byte-like") from exc
        if len(key) < MIN_KEY_BYTES:
            raise SealConfigurationError(
                f"key '{key_id}' must contain at least {MIN_KEY_BYTES} bytes"
            )
        normalized[key_id] = key
    return normalized


def _now_seconds(now: int | float | None) -> int:
    stamp = int(time.time() if now is None else now)
    if stamp < 0:
        raise ValueError("time cannot be negative")
    return stamp


def _validate_ttl(max_ttl_seconds: int, clock_skew_seconds: int) -> None:
    if max_ttl_seconds <= 0:
        raise SealConfigurationError("max_ttl_seconds must be positive")
    if clock_skew_seconds < 0:
        raise SealConfigurationError("clock_skew_seconds cannot be negative")
    if clock_skew_seconds > max_ttl_seconds:
        raise SealConfigurationError("clock skew cannot exceed maximum TTL")


def _payload(
    *,
    key_id: str,
    principal_id: str,
    attester_id: str,
    issued_at: int,
    expires_at: int,
) -> str:
    return ".".join(
        (
            SEAL_VERSION,
            key_id,
            principal_id,
            attester_id,
            str(issued_at),
            str(expires_at),
        )
    )


class PrincipalSealCodec:
    """Issue and verify short-lived, rotatable principal credentials.

    The wire format is::

        v1.key_id.principal_id.attester_id.issued_at.expires_at.signature_hex

    ``key_id`` is signed as part of the payload.  Verification therefore does
    one explicit key lookup instead of accepting a credential after trialing
    every configured secret.  Existing keys can remain verification-only by
    keeping them in ``keys`` while issuing with a newer ``signing_key_id``.
    """

    def __init__(
        self,
        keys: Mapping[str, bytes | bytearray | memoryview],
        *,
        signing_key_id: str | None = None,
        max_ttl_seconds: int = DEFAULT_MAX_TTL_SECONDS,
        clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
    ) -> None:
        _validate_ttl(max_ttl_seconds, clock_skew_seconds)
        self._keys = _coerce_keyring(keys)
        self.max_ttl_seconds = int(max_ttl_seconds)
        self.clock_skew_seconds = int(clock_skew_seconds)
        if signing_key_id is None:
            self.signing_key_id = None
        else:
            candidate = _bounded_id(signing_key_id, field="signing_key_id")
            if candidate not in self._keys:
                raise SealConfigurationError("signing_key_id is not present in keyring")
            self.signing_key_id = candidate

    @property
    def key_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._keys))

    def issue(
        self,
        principal_id: str,
        attester_id: str,
        *,
        ttl_seconds: int = 300,
        now: int | float | None = None,
    ) -> str:
        """Create a short-lived credential using the configured signing key."""

        if self.signing_key_id is None:
            raise SealConfigurationError("codec is verification-only; no signing key configured")
        if ttl_seconds <= 0 or ttl_seconds > self.max_ttl_seconds:
            raise SealConfigurationError(
                f"ttl_seconds must be between 1 and {self.max_ttl_seconds}"
            )
        principal = _bounded_id(principal_id, field="principal_id")
        attester = _bounded_id(attester_id, field="attester_id")
        issued_at = _now_seconds(now)
        expires_at = issued_at + int(ttl_seconds)
        payload = _payload(
            key_id=self.signing_key_id,
            principal_id=principal,
            attester_id=attester,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        signature = hmac.new(
            self._keys[self.signing_key_id], payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"{payload}.{signature}"

    def verify(self, seal: str, *, now: int | float | None = None) -> VerifiedPrincipal:
        """Verify one credential and return identity only after all checks pass."""

        if not isinstance(seal, str):
            raise SealMalformed("principal seal must be text")
        if not seal or len(seal) > MAX_SEAL_LENGTH:
            raise SealMalformed("principal seal length is invalid")
        parts = seal.split(".")
        if len(parts) != 7:
            raise SealMalformed("principal seal must contain exactly seven fields")
        version, key_raw, principal_raw, attester_raw, issued_raw, expiry_raw, signature = parts
        if version != SEAL_VERSION:
            raise SealMalformed(f"unsupported principal seal version '{version}'")
        key_id = _bounded_id(key_raw, field="key_id")
        principal = _bounded_id(principal_raw, field="principal_id")
        attester = _bounded_id(attester_raw, field="attester_id")
        if key_id not in self._keys:
            raise SealUnknownKey("principal seal references an unknown key")
        if not issued_raw.isdigit() or not expiry_raw.isdigit():
            raise SealMalformed("principal seal timestamps must be unsigned integers")
        issued_at = int(issued_raw)
        expires_at = int(expiry_raw)
        if issued_at < 0 or expires_at <= issued_at:
            raise SealMalformed("principal seal validity interval is invalid")
        if expires_at - issued_at > self.max_ttl_seconds:
            raise SealExpired("principal seal TTL exceeds configured maximum")
        if not _HEX_SHA256_RE.fullmatch(signature):
            raise SealMalformed("principal seal signature encoding is invalid")

        current = _now_seconds(now)
        if issued_at > current + self.clock_skew_seconds:
            raise SealExpired("principal seal is not yet valid")
        if expires_at < current - self.clock_skew_seconds:
            raise SealExpired("principal seal has expired")

        payload = _payload(
            key_id=key_id,
            principal_id=principal,
            attester_id=attester,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        expected = hmac.new(self._keys[key_id], payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise SealSignatureInvalid("principal seal signature is invalid")
        return VerifiedPrincipal(
            principal_id=principal,
            attester_id=attester,
            key_id=key_id,
            issued_at=issued_at,
            expires_at=expires_at,
        )


class RouteDomainPolicy:
    """Explicit route/domain map with fail-closed admission semantics."""

    def __init__(
        self,
        *,
        open_prefixes: Sequence[str] = ("/api/health",),
        domain_rules: Sequence[RouteRule],
    ) -> None:
        self._open_prefixes = tuple(
            sorted({self._validate_prefix(prefix) for prefix in open_prefixes}, key=len, reverse=True)
        )
        domains: list[RouteRule] = []
        seen: set[str] = set()
        for rule in domain_rules:
            prefix = self._validate_prefix(rule.prefix)
            domain = _bounded_id(rule.domain, field="domain")
            if prefix in seen:
                raise ValueError(f"duplicate route policy prefix '{prefix}'")
            seen.add(prefix)
            domains.append(RouteRule(prefix=prefix, domain=domain))
        self._domain_rules = tuple(sorted(domains, key=lambda rule: len(rule.prefix), reverse=True))

    @staticmethod
    def _validate_prefix(prefix: str) -> str:
        normalized = prefix.strip()
        if not normalized.startswith("/") or "?" in normalized or "#" in normalized:
            raise ValueError("route policy prefixes must be absolute URL paths")
        if normalized != "/":
            normalized = normalized.rstrip("/")
        if not normalized:
            raise ValueError("route policy prefix cannot be empty")
        return normalized

    @staticmethod
    def _matches(path: str, prefix: str) -> bool:
        if prefix == "/":
            return path.startswith("/")
        return path == prefix or path.startswith(prefix + "/")

    @staticmethod
    def _normalize_path(path: str) -> str:
        if not isinstance(path, str):
            raise TypeError("path must be text")
        normalized = path.strip()
        if not normalized.startswith("/") or "?" in normalized or "#" in normalized:
            raise ValueError("path must be an absolute URL path without query or fragment")
        return normalized.rstrip("/") or "/"

    @property
    def open_prefixes(self) -> tuple[str, ...]:
        return self._open_prefixes

    @property
    def domain_rules(self) -> tuple[RouteRule, ...]:
        return self._domain_rules

    def required_domain(self, path: str) -> str | None:
        normalized = self._normalize_path(path)
        for rule in self._domain_rules:
            if self._matches(normalized, rule.prefix):
                return rule.domain
        return None

    def is_open(self, path: str) -> bool:
        normalized = self._normalize_path(path)
        return any(self._matches(normalized, prefix) for prefix in self._open_prefixes)

    def admit(self, path: str, principal: VerifiedPrincipal | None) -> RouteAdmission:
        """Classify and admit one path using already-verified identity.

        Unknown routes intentionally return 404 rather than revealing an
        authentication boundary. Written protected routes require a verified
        principal. Domain-specific authorization remains the responsibility of
        ``CharterPolicy``/capability policy downstream.
        """

        normalized = self._normalize_path(path)
        if any(self._matches(normalized, prefix) for prefix in self._open_prefixes):
            return RouteAdmission(True, 200, "open route", open_route=True)
        domain = self.required_domain(normalized)
        if domain is None:
            return RouteAdmission(False, 404, "unwritten route is sealed")
        if principal is None:
            return RouteAdmission(False, 401, "verified principal required", domain=domain)
        return RouteAdmission(
            True,
            200,
            "verified principal admitted to written route",
            domain=domain,
            principal_id=principal.principal_id,
            attester_id=principal.attester_id,
        )
