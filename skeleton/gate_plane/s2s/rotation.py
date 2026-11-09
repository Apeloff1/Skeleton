"""Scheduled key rotation and revocation lists for the s2s key ring.

:class:`RotationScheduler` rotates the ACTIVE key every ``rotate_every_s``
with an overlap window, pre-publishing the next key as PENDING
``prepublish_s`` ahead of time so verifiers that sync key material can load
it before it starts signing. It is driven by :meth:`RotationScheduler.tick`
(call from a periodic task or a request hook) and never sleeps itself.

:class:`RevocationList` tracks revoked token ids (``jti``) until their
natural expiry, and fans kid revocations into the key ring.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from skeleton.gate_plane.s2s.clock import Clock, system_clock
from skeleton.gate_plane.s2s.keyring import KeyRing, KeyRingError, KeyState

SecretFactory = Callable[[str], bytes]


def random_secret_factory(nbytes: int = 32) -> SecretFactory:
    """Production secret source (OS CSPRNG)."""

    def _factory(kid: str) -> bytes:
        return os.urandom(nbytes)

    return _factory


def derived_secret_factory(master: bytes, *, nbytes: int = 32) -> SecretFactory:
    """Deterministic HKDF-like derivation from a master secret.

    Useful when several verifier replicas must independently arrive at the
    same key material for a kid (and for seeded tests). ``master`` must be
    at least 32 bytes.
    """
    if len(master) < 32:
        raise KeyRingError("master secret must be >= 32 bytes")

    def _factory(kid: str) -> bytes:
        out = b""
        block = b""
        counter = 1
        while len(out) < nbytes:
            block = hmac.new(master, block + kid.encode("utf-8") + bytes([counter]), hashlib.sha256).digest()
            out += block
            counter += 1
        return out[:nbytes]

    return _factory


@dataclass(frozen=True)
class RotationPolicy:
    rotate_every_s: float = 3600.0
    overlap_s: float = 600.0
    prepublish_s: float = 120.0
    kid_prefix: str = "k"

    def __post_init__(self) -> None:
        if self.rotate_every_s <= 0:
            raise KeyRingError("rotate_every_s must be > 0")
        if self.overlap_s < 0:
            raise KeyRingError("overlap_s must be >= 0")
        if not (0 <= self.prepublish_s < self.rotate_every_s):
            raise KeyRingError("prepublish_s must be in [0, rotate_every_s)")
        if self.overlap_s > self.rotate_every_s * 4:
            raise KeyRingError("overlap_s longer than 4 rotation periods keeps too many keys live")

    def as_dict(self) -> Dict[str, object]:
        return {
            "rotate_every_s": self.rotate_every_s,
            "overlap_s": self.overlap_s,
            "prepublish_s": self.prepublish_s,
            "kid_prefix": self.kid_prefix,
        }


@dataclass(frozen=True)
class RotationEvent:
    at: float
    action: str  # bootstrap | prepublish | rotate | prune
    kid: str


class RotationScheduler:
    """Time-driven rotation over a :class:`KeyRing`."""

    def __init__(
        self,
        keyring: KeyRing,
        *,
        policy: Optional[RotationPolicy] = None,
        secret_factory: Optional[SecretFactory] = None,
        clock: Optional[Clock] = None,
    ) -> None:
        self.keyring = keyring
        self.policy = policy or RotationPolicy()
        self.secret_factory = secret_factory or random_secret_factory()
        self.clock: Clock = clock if clock is not None else system_clock()
        self._generation = 0
        self._last_rotation: Optional[float] = None
        self._pending_kid: Optional[str] = None
        self._lock = threading.Lock()
        self.history: List[RotationEvent] = []

    def _kid_for(self, generation: int) -> str:
        return f"{self.policy.kid_prefix}{generation:06d}"

    def _record(self, action: str, kid: str) -> None:
        self.history.append(RotationEvent(self.clock.now(), action, kid))

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def next_rotation_at(self) -> Optional[float]:
        if self._last_rotation is None:
            return None
        return self._last_rotation + self.policy.rotate_every_s

    def bootstrap(self) -> str:
        """Create and activate the first key (idempotent)."""
        with self._lock:
            if self._last_rotation is not None:
                return self.keyring.signing_key().kid
            self._generation += 1
            kid = self._kid_for(self._generation)
            while kid in self.keyring:
                self._generation += 1
                kid = self._kid_for(self._generation)
            self.keyring.add_key(kid, self.secret_factory(kid), activate=True)
            self._last_rotation = self.clock.now()
            self._record("bootstrap", kid)
            return kid

    def _prepublish_unlocked(self) -> str:
        if self._pending_kid is not None:
            return self._pending_kid
        gen = self._generation + 1
        kid = self._kid_for(gen)
        while kid in self.keyring:
            gen += 1
            kid = self._kid_for(gen)
        self.keyring.add_key(kid, self.secret_factory(kid))
        self._pending_kid = kid
        self._generation = gen
        self._record("prepublish", kid)
        return kid

    def rotate_now(self) -> str:
        """Force a rotation (e.g. after a suspected compromise)."""
        with self._lock:
            if self._last_rotation is None:
                raise KeyRingError("bootstrap() before rotating")
            return self._rotate_unlocked()

    def _rotate_unlocked(self) -> str:
        kid = self._prepublish_unlocked()
        self.keyring.activate(kid, overlap_s=self.policy.overlap_s)
        self._pending_kid = None
        self._last_rotation = self.clock.now()
        self._record("rotate", kid)
        return kid

    def tick(self) -> List[RotationEvent]:
        """Advance: prepublish, rotate, expire and prune as the clock dictates."""
        with self._lock:
            start = len(self.history)
            if self._last_rotation is None:
                raise KeyRingError("bootstrap() before tick()")
            now = self.clock.now()
            due = self._last_rotation + self.policy.rotate_every_s
            if now >= due - self.policy.prepublish_s and self._pending_kid is None:
                self._prepublish_unlocked()
            # Catch up across several missed periods without minting a key per period.
            if now >= due:
                self._rotate_unlocked()
            self.keyring.tick()
            for kid in self.keyring.prune():
                self._record("prune", kid)
            return self.history[start:]

    def status(self) -> Dict[str, object]:
        return {
            "generation": self._generation,
            "pending_kid": self._pending_kid,
            "next_rotation_at": self.next_rotation_at,
            "policy": self.policy.as_dict(),
            "live_kids": self.keyring.kids(states=[KeyState.ACTIVE, KeyState.RETIRING, KeyState.PENDING]),
        }


class RevocationList:
    """Revoked jti set (auto-expiring) plus kid revocation fan-out."""

    def __init__(self, keyring: Optional[KeyRing] = None, *, capacity: int = 100_000) -> None:
        self.keyring = keyring
        self.capacity = int(capacity)
        self._jtis: Dict[str, float] = {}
        self._kids: Dict[str, str] = {}
        self._lock = threading.Lock()

    def revoke_token(self, jti: str, *, until: float) -> None:
        with self._lock:
            self._jtis[jti] = float(until)
            if len(self._jtis) > self.capacity:
                # Drop the entries that expire soonest; they are least useful.
                for victim, _ in sorted(self._jtis.items(), key=lambda kv: kv[1])[: len(self._jtis) - self.capacity]:
                    del self._jtis[victim]

    def revoke_kid(self, kid: str, *, reason: str = "") -> None:
        with self._lock:
            self._kids[kid] = reason
        if self.keyring is not None and kid in self.keyring:
            self.keyring.revoke(kid, reason=reason)

    def is_revoked(self, jti: str, now: float) -> bool:
        with self._lock:
            until = self._jtis.get(jti)
            if until is None:
                return False
            if now >= until:
                del self._jtis[jti]
                return False
            return True

    def kid_revoked(self, kid: str) -> bool:
        with self._lock:
            return kid in self._kids

    def purge(self, now: float) -> int:
        with self._lock:
            stale = [j for j, until in self._jtis.items() if now >= until]
            for j in stale:
                del self._jtis[j]
            return len(stale)

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {"revoked_jtis": len(self._jtis), "revoked_kids": sorted(self._kids)}


__all__ = [
    "RevocationList",
    "RotationEvent",
    "RotationPolicy",
    "RotationScheduler",
    "SecretFactory",
    "derived_secret_factory",
    "random_secret_factory",
]
