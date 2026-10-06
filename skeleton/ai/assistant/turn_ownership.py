"""Enterprise execution ownership for durable AI-chat turns.

A chat turn may be observed by many workers but only one active execution
attempt may own mutable model/tool progression at a time. Ownership is a
time-bounded lease plus a strictly monotonic fencing epoch. Persisted writes
must validate the exact lease token at the same atomic boundary as the write.

This module contains only canonical value objects and validation rules. Storage
adapters own compare-and-swap and takeover persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from typing import Any


TURN_OWNERSHIP_SCHEMA_VERSION = 1


class TurnOwnershipError(ValueError):
    """Canonical execution-ownership contract violation."""


class TurnLeaseBusy(TurnOwnershipError):
    """Another live execution attempt owns the turn."""


class TurnLeaseStale(TurnOwnershipError):
    """The supplied fencing epoch/holder is no longer current."""


class TurnLeaseExpired(TurnOwnershipError):
    """The supplied ownership lease has expired."""


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TurnOwnershipError(f"{field} must be canonical non-empty text")
    if len(value) > maximum or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise TurnOwnershipError(f"{field} is not canonical")
    return value


def _positive_int(value: object, field: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise TurnOwnershipError(f"{field} must be an integer >= {minimum}")
    return value


def _aware(value: datetime, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise TurnOwnershipError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _seconds(value: object, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise TurnOwnershipError(f"{field} must be a positive finite number")
    return float(value)


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class TurnLeasePolicy:
    default_ttl_seconds: float = 45.0
    max_ttl_seconds: float = 300.0
    minimum_renewal_seconds: float = 5.0

    def __post_init__(self) -> None:
        default = _seconds(self.default_ttl_seconds, "default_ttl_seconds")
        maximum = _seconds(self.max_ttl_seconds, "max_ttl_seconds")
        minimum = _seconds(self.minimum_renewal_seconds, "minimum_renewal_seconds")
        if default > maximum:
            raise TurnOwnershipError("default lease TTL exceeds maximum")
        if minimum > maximum:
            raise TurnOwnershipError("minimum renewal exceeds maximum")
        object.__setattr__(self, "default_ttl_seconds", default)
        object.__setattr__(self, "max_ttl_seconds", maximum)
        object.__setattr__(self, "minimum_renewal_seconds", minimum)

    def clamp_ttl(self, requested: float | None) -> float:
        ttl = self.default_ttl_seconds if requested is None else _seconds(
            requested,
            "requested_ttl_seconds",
        )
        if ttl > self.max_ttl_seconds:
            raise TurnOwnershipError("requested lease TTL exceeds maximum")
        if ttl < self.minimum_renewal_seconds:
            raise TurnOwnershipError("requested lease TTL is below minimum")
        return ttl


@dataclass(frozen=True, slots=True)
class TurnLeaseToken:
    operation_id: str
    tenant_id: str
    owner_id: str
    holder_id: str
    epoch: int
    heartbeat_sequence: int
    granted_at: datetime
    expires_at: datetime
    previous_lease_digest: str | None = None

    def __post_init__(self) -> None:
        for field in ("operation_id", "tenant_id", "owner_id", "holder_id"):
            object.__setattr__(
                self,
                field,
                _text(getattr(self, field), field, maximum=512),
            )
        object.__setattr__(self, "epoch", _positive_int(self.epoch, "epoch"))
        object.__setattr__(
            self,
            "heartbeat_sequence",
            _positive_int(
                self.heartbeat_sequence,
                "heartbeat_sequence",
                allow_zero=True,
            ),
        )
        granted = _aware(self.granted_at, "granted_at")
        expires = _aware(self.expires_at, "expires_at")
        if expires <= granted:
            raise TurnOwnershipError("lease expiry must follow grant time")
        object.__setattr__(self, "granted_at", granted)
        object.__setattr__(self, "expires_at", expires)
        if self.previous_lease_digest is not None:
            previous = _text(
                self.previous_lease_digest,
                "previous_lease_digest",
                maximum=64,
            )
            if len(previous) != 64 or any(
                char not in "0123456789abcdef" for char in previous
            ):
                raise TurnOwnershipError(
                    "previous_lease_digest must be lowercase sha256"
                )
            object.__setattr__(self, "previous_lease_digest", previous)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": TURN_OWNERSHIP_SCHEMA_VERSION,
                "operation_id": self.operation_id,
                "tenant_id": self.tenant_id,
                "owner_id": self.owner_id,
                "holder_id": self.holder_id,
                "epoch": self.epoch,
                "heartbeat_sequence": self.heartbeat_sequence,
                "granted_at": self.granted_at.isoformat(),
                "expires_at": self.expires_at.isoformat(),
                "previous_lease_digest": self.previous_lease_digest,
            }
        )

    def is_live(self, now: datetime) -> bool:
        return _aware(now, "now") < self.expires_at

    def require_live(self, now: datetime) -> None:
        if not self.is_live(now):
            raise TurnLeaseExpired(
                f"turn lease expired at {self.expires_at.isoformat()}"
            )

    def same_fence(self, other: "TurnLeaseToken") -> bool:
        if not isinstance(other, TurnLeaseToken):
            return False
        return (
            self.operation_id == other.operation_id
            and self.tenant_id == other.tenant_id
            and self.owner_id == other.owner_id
            and self.holder_id == other.holder_id
            and self.epoch == other.epoch
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TURN_OWNERSHIP_SCHEMA_VERSION,
            "operation_id": self.operation_id,
            "tenant_id": self.tenant_id,
            "owner_id": self.owner_id,
            "holder_id": self.holder_id,
            "epoch": self.epoch,
            "heartbeat_sequence": self.heartbeat_sequence,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "previous_lease_digest": self.previous_lease_digest,
            "digest": self.digest,
        }


@dataclass(frozen=True, slots=True)
class TurnOwnershipReceipt:
    operation_id: str
    action: str
    epoch: int
    holder_id: str
    observed_at: datetime
    lease_digest: str
    previous_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_id",
            _text(self.operation_id, "operation_id", maximum=512),
        )
        object.__setattr__(self, "action", _text(self.action, "action", maximum=64))
        if self.action not in {"acquire", "renew", "release", "takeover"}:
            raise TurnOwnershipError("unknown ownership receipt action")
        object.__setattr__(self, "epoch", _positive_int(self.epoch, "epoch"))
        object.__setattr__(
            self,
            "holder_id",
            _text(self.holder_id, "holder_id", maximum=512),
        )
        object.__setattr__(
            self,
            "observed_at",
            _aware(self.observed_at, "observed_at"),
        )
        lease_digest = _text(self.lease_digest, "lease_digest", maximum=64)
        if len(lease_digest) != 64 or any(
            char not in "0123456789abcdef" for char in lease_digest
        ):
            raise TurnOwnershipError("lease_digest must be lowercase sha256")
        object.__setattr__(self, "lease_digest", lease_digest)
        if self.previous_receipt_digest is not None:
            previous = _text(
                self.previous_receipt_digest,
                "previous_receipt_digest",
                maximum=64,
            )
            if len(previous) != 64 or any(
                char not in "0123456789abcdef" for char in previous
            ):
                raise TurnOwnershipError(
                    "previous_receipt_digest must be lowercase sha256"
                )
            object.__setattr__(self, "previous_receipt_digest", previous)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": TURN_OWNERSHIP_SCHEMA_VERSION,
                "operation_id": self.operation_id,
                "action": self.action,
                "epoch": self.epoch,
                "holder_id": self.holder_id,
                "observed_at": self.observed_at.isoformat(),
                "lease_digest": self.lease_digest,
                "previous_receipt_digest": self.previous_receipt_digest,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TURN_OWNERSHIP_SCHEMA_VERSION,
            "operation_id": self.operation_id,
            "action": self.action,
            "epoch": self.epoch,
            "holder_id": self.holder_id,
            "observed_at": self.observed_at.isoformat(),
            "lease_digest": self.lease_digest,
            "previous_receipt_digest": self.previous_receipt_digest,
            "digest": self.digest,
        }


__all__ = [
    "TURN_OWNERSHIP_SCHEMA_VERSION",
    "TurnLeaseBusy",
    "TurnLeaseExpired",
    "TurnLeasePolicy",
    "TurnLeaseStale",
    "TurnLeaseToken",
    "TurnOwnershipError",
    "TurnOwnershipReceipt",
]
