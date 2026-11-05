"""Lease-based per-environment deploy locks (pure state machine)."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from skeleton.build.delivery._util import DeliveryError, require_env_name, require_id

MAX_TTL = 6 * 3600


@dataclass(frozen=True)
class Lease:
    environment: str
    holder: str
    token: int
    expires_at: int


class DeployLockTable:
    """Fencing-token locks. Every successful acquire increments the token so a
    stale holder can be detected by downstream writers."""

    def __init__(self) -> None:
        self._leases: dict[str, Lease] = {}
        self._tokens: dict[str, int] = {}
        self._mutex = RLock()

    def holder(self, environment: str, *, now: int) -> Lease | None:
        with self._mutex:
            if type(now) is not int or now < 0:
                raise DeliveryError("deploy lock clock must be a nonnegative integer")
            lease = self._leases.get(environment)
            if lease is None or lease.expires_at <= now:
                return None
            return lease

    def acquire(self, environment: str, holder: str, *, now: int, ttl: int) -> Lease:
        with self._mutex:
            require_env_name(environment)
            require_id(holder, field="holder")
            if type(ttl) is not int or not 1 <= ttl <= MAX_TTL:
                raise DeliveryError(f"ttl must be 1..{MAX_TTL}")
            current = self.holder(environment, now=now)
            if current is not None and current.holder != holder:
                raise DeliveryError(f"{environment} locked by {current.holder} until {current.expires_at}")
            token = self._tokens.get(environment, 0) + 1
            self._tokens[environment] = token
            lease = Lease(environment, holder, token, now + ttl)
            self._leases[environment] = lease
            return lease

    def renew(self, lease: Lease, *, now: int, ttl: int) -> Lease:
        with self._mutex:
            self.check_fence(lease, now=now)
            if type(ttl) is not int or not 1 <= ttl <= MAX_TTL:
                raise DeliveryError(f"ttl must be 1..{MAX_TTL}")
            renewed = Lease(lease.environment, lease.holder, lease.token, now + ttl)
            self._leases[lease.environment] = renewed
            return renewed

    def release(self, lease: Lease, *, now: int) -> None:
        with self._mutex:
            self.check_fence(lease, now=now)
            del self._leases[lease.environment]

    def check_fence(self, lease: Lease, *, now: int) -> None:
        with self._mutex:
            current = self.holder(lease.environment, now=now)
            if (current is None or current.token != lease.token
                    or current.holder != lease.holder
                    or current.expires_at != lease.expires_at):
                raise DeliveryError("stale or expired lease")
