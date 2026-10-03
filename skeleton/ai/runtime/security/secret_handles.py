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


def evaluate_secret_use(
    *,
    receipt_id: str,
    secret_ref: SecretRef,
    grant: SecretGrant,
    consumer_id: str,
    scope: str,
    operation_id: str,
    now_ns: int,
) -> SecretUseReceipt:
    """Evaluate a handle use without resolving or exposing secret material."""

    if not isinstance(secret_ref, SecretRef):
        raise TypeError("secret_ref must be SecretRef")
    if not isinstance(grant, SecretGrant):
        raise TypeError("grant must be SecretGrant")
    consumer = _token("consumer_id", consumer_id)
    requested_scope = _token("scope", scope)
    operation = _token("operation_id", operation_id)
    if isinstance(now_ns, bool) or not isinstance(now_ns, int) or now_ns < 0:
        raise SecretSecurityError("now_ns must be a non-negative integer")

    allowed = False
    if grant.handle_id != secret_ref.handle_id:
        reason = "handle-mismatch"
    elif grant.consumer_id != consumer:
        reason = "consumer-mismatch"
    elif now_ns >= grant.expires_at_ns:
        reason = "grant-expired"
    elif requested_scope not in grant.scopes:
        reason = "scope-denied"
    else:
        allowed = True
        reason = "allowed"

    return SecretUseReceipt(
        receipt_id=receipt_id,
        grant_id=grant.grant_id,
        handle_id=secret_ref.handle_id,
        consumer_id=consumer,
        scope=requested_scope,
        operation_id=operation,
        allowed=allowed,
        reason_code=reason,
        used_at_ns=now_ns,
    )


_REDACTED = "[REDACTED]"
_SENSITIVE_KEYS = frozenset({
    "authorization",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
    "api_key",
    "private_key",
})
_SENSITIVE_SUFFIXES = (
    "_credential",
    "_credentials",
    "_password",
    "_secret",
    "_token",
    "_api_key",
    "_private_key",
)
_MAX_SANITIZE_DEPTH = 32


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)


def sanitize_secret_metadata(
    value: object,
) -> tuple[object, tuple[str, ...]]:
    """Return a JSON-like copy with secret-shaped fields redacted.

    Findings contain paths only; the suspected secret values are never copied
    into the evidence list.
    """

    findings: list[str] = []
    active: set[int] = set()

    def walk(item: object, path: str, depth: int) -> object:
        if depth > _MAX_SANITIZE_DEPTH:
            raise SecretSecurityError("secret metadata exceeds maximum depth")
        if item is None or isinstance(item, (bool, int, float, str)):
            return item
        if isinstance(item, bytes):
            raise SecretSecurityError("secret metadata cannot contain bytes")
        if isinstance(item, dict):
            identity = id(item)
            if identity in active:
                raise SecretSecurityError("secret metadata cannot contain cycles")
            active.add(identity)
            try:
                sanitized: dict[str, object] = {}
                for key, child in item.items():
                    if not isinstance(key, str) or not key:
                        raise SecretSecurityError(
                            "secret metadata keys must be non-empty strings"
                        )
                    child_path = f"{path}.{key}"
                    if _is_sensitive_key(key):
                        sanitized[key] = _REDACTED
                        findings.append(child_path)
                    else:
                        sanitized[key] = walk(child, child_path, depth + 1)
                return sanitized
            finally:
                active.remove(identity)
        if isinstance(item, (list, tuple)):
            identity = id(item)
            if identity in active:
                raise SecretSecurityError("secret metadata cannot contain cycles")
            active.add(identity)
            try:
                return [
                    walk(child, f"{path}[{index}]", depth + 1)
                    for index, child in enumerate(item)
                ]
            finally:
                active.remove(identity)
        raise SecretSecurityError(
            "secret metadata must contain only JSON-like values"
        )

    return walk(value, "$", 0), tuple(sorted(findings))


__all__ = [
    "SecretGrant",
    "SecretRef",
    "SecretSecurityError",
    "SecretUseReceipt",
    "evaluate_secret_use",
    "sanitize_secret_metadata",
]
