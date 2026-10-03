"""Opaque secret-handle contracts for the AI runtime.

The contracts in this module intentionally never carry secret material.
They describe references, scoped grants, and use receipts only. Secret
resolution remains outside this evidence surface.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable


class SecretSecurityError(ValueError):
    """A secret-handle or grant invariant failed."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SecretSecurityError(f"{name} must be non-empty normalized text")
    if len(value) > 256:
        raise SecretSecurityError(f"{name} exceeds maximum length")
    return value


def _scopes(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise SecretSecurityError("scopes must be a collection")
    result = tuple(sorted({_token("scope", value) for value in values}))
    if not result:
        raise SecretSecurityError("scopes must be non-empty")
    return result


def _digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SecretSecurityError("secret evidence must be canonical JSON") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SecretRef:
    """Opaque reference to secret material owned by an external resolver."""

    handle_id: str
    provider_id: str
    version_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "handle_id", _token("handle_id", self.handle_id))
        object.__setattr__(self, "provider_id", _token("provider_id", self.provider_id))
        object.__setattr__(self, "version_id", _token("version_id", self.version_id))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "handle_id": self.handle_id,
                "provider_id": self.provider_id,
                "version_id": self.version_id,
            }
        )


@dataclass(frozen=True, slots=True)
class SecretGrant:
    """Bounded permission to use one opaque secret handle."""

    grant_id: str
    handle_id: str
    consumer_id: str
    scopes: tuple[str, ...]
    expires_at_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "grant_id", _token("grant_id", self.grant_id))
        object.__setattr__(self, "handle_id", _token("handle_id", self.handle_id))
        object.__setattr__(self, "consumer_id", _token("consumer_id", self.consumer_id))
        object.__setattr__(self, "scopes", _scopes(self.scopes))
        if (
            isinstance(self.expires_at_ns, bool)
            or not isinstance(self.expires_at_ns, int)
            or self.expires_at_ns <= 0
        ):
            raise SecretSecurityError("expires_at_ns must be a positive integer")

    def permits(self, scope: str, *, now_ns: int) -> bool:
        requested = _token("scope", scope)
        if isinstance(now_ns, bool) or not isinstance(now_ns, int) or now_ns < 0:
            raise SecretSecurityError("now_ns must be a non-negative integer")
        return now_ns < self.expires_at_ns and requested in self.scopes

    @property
    def digest(self) -> str:
        return _digest(
            {
                "grant_id": self.grant_id,
                "handle_id": self.handle_id,
                "consumer_id": self.consumer_id,
                "scopes": list(self.scopes),
                "expires_at_ns": self.expires_at_ns,
            }
        )


@dataclass(frozen=True, slots=True)
class SecretUseReceipt:
    """Evidence of a handle use decision; never a carrier for secret material."""

    receipt_id: str
    grant_id: str
    handle_id: str
    consumer_id: str
    scope: str
    operation_id: str
    allowed: bool
    reason_code: str
    used_at_ns: int
    secret_material_present: bool = False

    def __post_init__(self) -> None:
        for name in (
            "receipt_id",
            "grant_id",
            "handle_id",
            "consumer_id",
            "scope",
            "operation_id",
            "reason_code",
        ):
            object.__setattr__(self, name, _token(name, getattr(self, name)))
        if not isinstance(self.allowed, bool):
            raise SecretSecurityError("allowed must be boolean")
        if (
            isinstance(self.used_at_ns, bool)
            or not isinstance(self.used_at_ns, int)
            or self.used_at_ns < 0
        ):
            raise SecretSecurityError("used_at_ns must be a non-negative integer")
        if self.secret_material_present is not False:
            raise SecretSecurityError("secret use receipts cannot carry secret material")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "receipt_id": self.receipt_id,
                "grant_id": self.grant_id,
                "handle_id": self.handle_id,
                "consumer_id": self.consumer_id,
                "scope": self.scope,
                "operation_id": self.operation_id,
                "allowed": self.allowed,
                "reason_code": self.reason_code,
                "used_at_ns": self.used_at_ns,
                "secret_material_present": False,
            }
        )


__all__ = [
    "SecretGrant",
    "SecretRef",
    "SecretSecurityError",
    "SecretUseReceipt",
]
