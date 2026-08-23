"""Kernel capability tokens — unforgeable, scoped, revocable authority.

Skeleton agents ask subsystems to do sensitive things: read a vault
secret, publish to the bus, fork a swarm member. The kernel needs to
know not just *who* is asking but *what they were authorised to do*.
This module implements capability tokens:

- A :class:`Capability` is a scoped grant — ``scope`` (resource class),
  ``action``, optional ``constraints``, and an expiry.
- :class:`CapabilityToken` binds capabilities to a subject and is
  HMAC-signed with a kernel-held key; forging one without the key is
  computationally infeasible, and every check is constant-time.
- :class:`TokenIssuer` mints, verifies, attenuates (narrow-only), and
  revokes tokens. Attenuation is monotonic — a derived token can never
  exceed its parent's authority, expiry, or scope.

Stdlib only (``hmac``/``hashlib``/``secrets``). Tokens serialise to a
compact dot-joined string safe for event envelopes and headers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, Iterable, Optional, Set, Tuple

from .errors import IdentityError


class CapabilityError(IdentityError):
    code = "KRN.CAPABILITY"


class TokenExpired(CapabilityError):
    code = "KRN.CAP_EXPIRED"
    http_status = 401


class TokenRevoked(CapabilityError):
    code = "KRN.CAP_REVOKED"
    http_status = 401


class ForgeryError(CapabilityError):
    code = "KRN.CAP_FORGERY"
    http_status = 401


class AttenuationError(CapabilityError):
    code = "KRN.CAP_ATTENUATION"


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


@dataclass(frozen=True)
class Capability:
    """A single scoped grant."""

    scope: str          # e.g. "vault.secrets", "bus.publish", "swarm.fork"
    action: str         # e.g. "read", "write", "*"
    constraints: FrozenSet[Tuple[str, str]] = field(default_factory=frozenset)
    expires_at: Optional[float] = None  # unix epoch; None = never

    def covers(self, other: "Capability") -> bool:
        """True iff this capability is at least as broad as ``other``."""
        if self.scope != other.scope and self.scope != "*":
            return False
        if self.action != other.action and self.action != "*":
            return False
        if self.constraints and self.constraints != other.constraints:
            # constrained parent only covers identically-constrained child
            return False
        if self.expires_at is None:
            return True
        return other.expires_at is not None and other.expires_at <= self.expires_at

    def is_live(self, now: Optional[float] = None) -> bool:
        if self.expires_at is None:
            return True
        return (time.time() if now is None else now) < self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scope": self.scope,
            "action": self.action,
            "constraints": sorted(list(self.constraints)),
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Capability":
        return cls(
            scope=str(data["scope"]),
            action=str(data["action"]),
            constraints=frozenset(tuple(c) for c in data.get("constraints", [])),
            expires_at=data.get("expires_at"),
        )


@dataclass(frozen=True)
class CapabilityToken:
    subject: str
    capabilities: Tuple[Capability, ...]
    token_id: str
    issued_at: float
    parent_id: Optional[str] = None

    def to_payload(self) -> bytes:
        return json.dumps({
            "sub": self.subject,
            "caps": [c.to_dict() for c in self.capabilities],
            "tid": self.token_id,
            "iat": self.issued_at,
            "parent": self.parent_id,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_payload(cls, payload: bytes) -> "CapabilityToken":
        data = json.loads(payload.decode("utf-8"))
        return cls(
            subject=data["sub"],
            capabilities=tuple(Capability.from_dict(c) for c in data["caps"]),
            token_id=data["tid"],
            issued_at=float(data["iat"]),
            parent_id=data.get("parent"),
        )


class TokenIssuer:
    """Mints, verifies, attenuates, and revokes capability tokens."""

    def __init__(self, secret: Optional[bytes] = None) -> None:
        self._key = secret or secrets.token_bytes(32)
        self._revoked: Set[str] = set()

    # ------------------------------------------------------------------
    # Minting
    # ------------------------------------------------------------------

    def mint(self, subject: str,
             capabilities: Iterable[Capability],
             *, parent_id: Optional[str] = None) -> str:
        caps = tuple(capabilities)
        if not subject or not caps:
            raise CapabilityError(
                "token needs a subject and at least one capability",
                context={"subject": subject!r},
            )
        token = CapabilityToken(
            subject=subject,
            capabilities=caps,
            token_id=secrets.token_hex(8),
            issued_at=time.time(),
            parent_id=parent_id,
        )
        payload = token.to_payload()
        sig = hmac.new(self._key, payload, hashlib.sha256).digest()
        return f"{_b64e(payload)}.{_b64e(sig)}"

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, serialised: str, *, now: Optional[float] = None) -> CapabilityToken:
        try:
            payload_b64, sig_b64 = serialised.split(".")
            payload, sig = _b64d(payload_b64), _b64d(sig_b64)
        except Exception as exc:  # noqa: BLE001 — any parse failure is forgery-shaped
            raise ForgeryError("malformed token", cause=exc) from exc

        expected = hmac.new(self._key, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            raise ForgeryError("token signature mismatch")

        token = CapabilityToken.from_payload(payload)
        if token.token_id in self._revoked:
            raise TokenRevoked(
                "token has been revoked",
                context={"token_id": token.token_id, "subject": token.subject},
            )
        now = time.time() if now is None else now
        for cap in token.capabilities:
            if not cap.is_live(now):
                raise TokenExpired(
                    "one or more capabilities have expired",
                    context={"token_id": token.token_id, "scope": cap.scope},
                )
        return token

    def check(self, serialised: str, scope: str, action: str,
              *, now: Optional[float] = None) -> bool:
        """True iff the token holds a live capability covering scope/action."""
        token = self.verify(serialised, now=now)
        probe = Capability(scope=scope, action=action)
        return any(c.covers(probe) for c in token.capabilities)

    # ------------------------------------------------------------------
    # Attenuation & revocation
    # ------------------------------------------------------------------

    def attenuate(self, serialised: str,
                  narrower: Iterable[Capability]) -> str:
        """Derive a strictly narrower token. Each requested capability
        must be covered by some capability on the parent."""
        parent = self.verify(serialised)
        requested = tuple(narrower)
        for cap in requested:
            if not any(p.covers(cap) for p in parent.capabilities):
                raise AttenuationError(
                    "derived capability exceeds parent authority",
                    context={"scope": cap.scope, "action": cap.action},
                )
        return self.mint(parent.subject, requested, parent_id=parent.token_id)

    def revoke(self, token_id: str) -> None:
        self._revoked.add(token_id)

    def is_revoked(self, token_id: str) -> bool:
        return token_id in self._revoked
