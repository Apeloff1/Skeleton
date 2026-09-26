"""kid-based HMAC key ring with rotation overlap windows and revocation.

Key lifecycle::

    PENDING --activate--> ACTIVE --rotate--> RETIRING --overlap elapses--> EXPIRED
       \\                    \\                   \\
        `------------------- revoke() -----------------> REVOKED

* Exactly one key is ACTIVE at a time; it is the only key used for signing.
* RETIRING keys still *verify* tokens until ``retire_at`` so in-flight tokens
  minted just before a rotation stay valid (the overlap window).
* REVOKED keys never verify again, regardless of overlap.
* PENDING keys can be pre-distributed to verifiers before they start signing
  (``accept_pending=True`` lets verifiers honour them early).

Secrets are never exposed by :meth:`KeyRing.snapshot`; only a short SHA-256
fingerprint is published so evidence and logs stay secret-free.
"""

from __future__ import annotations

import hashlib
import re
import threading
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Dict, Iterable, List, Optional

from skeleton.gate_plane.s2s.clock import Clock, system_clock

MIN_SECRET_BYTES = 32
MAX_KEYS = 16
_KID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")


class KeyState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    RETIRING = "retiring"
    EXPIRED = "expired"
    REVOKED = "revoked"


class KeyRingError(ValueError):
    """Invalid key ring operation (bad kid, duplicate, weak secret, ...)."""


class UnknownKeyError(KeyRingError):
    """No key with the requested kid."""


class NoActiveKeyError(KeyRingError):
    """Signing requested but no key is ACTIVE."""


def fingerprint(secret: bytes) -> str:
    """Short, non-reversible fingerprint used in snapshots and evidence."""
    return hashlib.sha256(b"s2s-kid-fp\x00" + secret).hexdigest()[:16]


def validate_kid(kid: str) -> str:
    if not isinstance(kid, str) or not _KID_RE.match(kid):
        raise KeyRingError(f"invalid kid {kid!r}: 1-64 chars of [A-Za-z0-9._:-], alnum first")
    return kid


@dataclass(frozen=True)
class ServiceKey:
    kid: str
    secret: bytes = field(repr=False)
    state: KeyState
    created_at: float
    activated_at: Optional[float] = None
    retire_at: Optional[float] = None
    revoked_at: Optional[float] = None
    revoked_reason: str = ""

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.secret)

    def can_sign(self) -> bool:
        return self.state is KeyState.ACTIVE

    def can_verify(self, now: float, *, accept_pending: bool = False) -> bool:
        if self.state is KeyState.ACTIVE:
            return True
        if self.state is KeyState.RETIRING:
            return self.retire_at is not None and now < self.retire_at
        if self.state is KeyState.PENDING:
            return accept_pending
        return False

    def public_view(self) -> Dict[str, object]:
        return {
            "kid": self.kid,
            "state": self.state.value,
            "fingerprint": self.fingerprint,
            "created_at": self.created_at,
            "activated_at": self.activated_at,
            "retire_at": self.retire_at,
            "revoked_at": self.revoked_at,
            "revoked_reason": self.revoked_reason,
        }


@dataclass(frozen=True)
class KeyRingEvent:
    at: float
    action: str
    kid: str
    detail: str = ""

    def as_dict(self) -> Dict[str, object]:
        return {"at": self.at, "action": self.action, "kid": self.kid, "detail": self.detail}


class KeyRing:
    """Thread-safe kid → key map with rotation and revocation semantics."""

    def __init__(
        self,
        *,
        clock: Optional[Clock] = None,
        max_keys: int = MAX_KEYS,
        min_secret_bytes: int = MIN_SECRET_BYTES,
    ) -> None:
        if max_keys < 2:
            raise KeyRingError("max_keys must allow at least an active and a retiring key")
        self._clock: Clock = clock if clock is not None else system_clock()
        self._keys: Dict[str, ServiceKey] = {}
        self._order: List[str] = []
        self._lock = threading.RLock()
        self.max_keys = int(max_keys)
        self.min_secret_bytes = int(min_secret_bytes)
        self._events: List[KeyRingEvent] = []

    # -- internals -----------------------------------------------------

    def _now(self) -> float:
        return self._clock.now()

    def _log(self, action: str, kid: str, detail: str = "") -> None:
        self._events.append(KeyRingEvent(self._now(), action, kid, detail))
        if len(self._events) > 1024:
            del self._events[: len(self._events) - 1024]

    def _get(self, kid: str) -> ServiceKey:
        key = self._keys.get(kid)
        if key is None:
            raise UnknownKeyError(f"unknown kid {kid!r}")
        return key

    def _put(self, key: ServiceKey) -> None:
        if key.kid not in self._keys:
            self._order.append(key.kid)
        self._keys[key.kid] = key

    def _expire_unlocked(self, now: float) -> List[str]:
        expired: List[str] = []
        for kid in list(self._order):
            key = self._keys[kid]
            if key.state is KeyState.RETIRING and key.retire_at is not None and now >= key.retire_at:
                self._keys[kid] = replace(key, state=KeyState.EXPIRED)
                expired.append(kid)
                self._log("expire", kid)
        return expired

    # -- mutation --------------------------------------------------------

    def add_key(self, kid: str, secret: bytes, *, activate: bool = False) -> ServiceKey:
        validate_kid(kid)
        if not isinstance(secret, (bytes, bytearray)):
            raise KeyRingError("secret must be bytes")
        if len(secret) < self.min_secret_bytes:
            raise KeyRingError(f"secret for {kid!r} shorter than {self.min_secret_bytes} bytes")
        with self._lock:
            if kid in self._keys:
                raise KeyRingError(f"duplicate kid {kid!r}")
            live = [k for k in self._keys.values() if k.state not in (KeyState.EXPIRED, KeyState.REVOKED)]
            if len(live) >= self.max_keys:
                raise KeyRingError("key ring full; prune expired/revoked keys first")
            key = ServiceKey(kid=kid, secret=bytes(secret), state=KeyState.PENDING, created_at=self._now())
            self._put(key)
            self._log("add", kid)
            if activate:
                return self.activate(kid, overlap_s=0.0)
            return key

    def activate(self, kid: str, *, overlap_s: float = 300.0) -> ServiceKey:
        """Make ``kid`` the signing key; the previous ACTIVE key starts retiring."""
        if overlap_s < 0:
            raise KeyRingError("overlap_s must be >= 0")
        with self._lock:
            now = self._now()
            key = self._get(kid)
            if key.state is KeyState.REVOKED:
                raise KeyRingError(f"cannot activate revoked kid {kid!r}")
            if key.state is KeyState.EXPIRED:
                raise KeyRingError(f"cannot activate expired kid {kid!r}")
            if key.state is KeyState.ACTIVE:
                return key
            for other_kid in self._order:
                other = self._keys[other_kid]
                if other.state is KeyState.ACTIVE:
                    if overlap_s == 0:
                        self._keys[other_kid] = replace(other, state=KeyState.EXPIRED, retire_at=now)
                        self._log("expire", other_kid, "zero-overlap rotation")
                    else:
                        self._keys[other_kid] = replace(
                            other, state=KeyState.RETIRING, retire_at=now + overlap_s
                        )
                        self._log("retire", other_kid, f"overlap={overlap_s}")
            activated = replace(key, state=KeyState.ACTIVE, activated_at=now, retire_at=None)
            self._keys[kid] = activated
            self._log("activate", kid)
            return activated

    def rotate(self, new_kid: str, secret: bytes, *, overlap_s: float = 300.0) -> ServiceKey:
        """Add ``new_kid`` and activate it in one step."""
        with self._lock:
            self.add_key(new_kid, secret)
            return self.activate(new_kid, overlap_s=overlap_s)

    def revoke(self, kid: str, *, reason: str = "") -> ServiceKey:
        with self._lock:
            key = self._get(kid)
            if key.state is KeyState.REVOKED:
                return key
            revoked = replace(key, state=KeyState.REVOKED, revoked_at=self._now(), revoked_reason=reason)
            self._keys[kid] = revoked
            self._log("revoke", kid, reason)
            return revoked

    def shorten_overlap(self, kid: str, retire_at: float) -> ServiceKey:
        """Pull a RETIRING key's retire time earlier (never later)."""
        with self._lock:
            key = self._get(kid)
            if key.state is not KeyState.RETIRING:
                raise KeyRingError(f"kid {kid!r} is not retiring")
            assert key.retire_at is not None
            new_at = min(key.retire_at, float(retire_at))
            updated = replace(key, retire_at=new_at)
            self._keys[kid] = updated
            self._log("shorten", kid, f"retire_at={new_at}")
            self._expire_unlocked(self._now())
            return self._keys[kid]

    def prune(self) -> List[str]:
        """Drop EXPIRED and REVOKED keys. Revoked kids are remembered in events."""
        with self._lock:
            self._expire_unlocked(self._now())
            dropped = [
                kid for kid in self._order if self._keys[kid].state in (KeyState.EXPIRED, KeyState.REVOKED)
            ]
            for kid in dropped:
                del self._keys[kid]
                self._order.remove(kid)
                self._log("prune", kid)
            return dropped

    def tick(self) -> List[str]:
        """Advance lifecycle: RETIRING keys past their overlap become EXPIRED."""
        with self._lock:
            return self._expire_unlocked(self._now())

    # -- queries ---------------------------------------------------------

    def signing_key(self) -> ServiceKey:
        with self._lock:
            for kid in self._order:
                key = self._keys[kid]
                if key.state is KeyState.ACTIVE:
                    return key
        raise NoActiveKeyError("no ACTIVE signing key")

    def verification_key(self, kid: str, *, accept_pending: bool = False) -> Optional[ServiceKey]:
        """Key usable to verify ``kid`` right now, or ``None``."""
        with self._lock:
            now = self._now()
            self._expire_unlocked(now)
            key = self._keys.get(kid)
            if key is None or not key.can_verify(now, accept_pending=accept_pending):
                return None
            return key

    def get(self, kid: str) -> ServiceKey:
        with self._lock:
            return self._get(kid)

    def state_of(self, kid: str) -> Optional[KeyState]:
        with self._lock:
            key = self._keys.get(kid)
            return None if key is None else key.state

    def kids(self, *, states: Optional[Iterable[KeyState]] = None) -> List[str]:
        wanted = None if states is None else set(states)
        with self._lock:
            return [kid for kid in self._order if wanted is None or self._keys[kid].state in wanted]

    def events(self) -> List[KeyRingEvent]:
        with self._lock:
            return list(self._events)

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            self._expire_unlocked(self._now())
            active = [k for k in self._order if self._keys[k].state is KeyState.ACTIVE]
            return {
                "active_kid": active[0] if active else None,
                "keys": [self._keys[k].public_view() for k in self._order],
                "max_keys": self.max_keys,
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._keys)

    def __contains__(self, kid: object) -> bool:
        with self._lock:
            return kid in self._keys


__all__ = [
    "KeyRing",
    "KeyRingError",
    "KeyRingEvent",
    "KeyState",
    "MAX_KEYS",
    "MIN_SECRET_BYTES",
    "NoActiveKeyError",
    "ServiceKey",
    "UnknownKeyError",
    "fingerprint",
    "validate_kid",
]
