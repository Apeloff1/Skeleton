"""Versioned key metadata contracts for the AI runtime.

This module models identifiers, lifecycle metadata, and rotation evidence only.
It never stores, derives, unwraps, encrypts with, decrypts with, or otherwise
handles cryptographic key material.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


_STATES = frozenset({"active", "retired", "revoked"})


class KeyManagementError(ValueError):
    """A key metadata or rotation-evidence invariant failed."""


def _token(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise KeyManagementError(f"{name} must be non-empty normalized text")
    if len(value) > 256:
        raise KeyManagementError(f"{name} exceeds maximum length")
    return value


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise KeyManagementError(f"{name} must be a positive integer")
    return value


def _non_negative_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise KeyManagementError(f"{name} must be a non-negative integer")
    return value


def _sha256(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise KeyManagementError(f"{name} must be a lowercase sha256 digest")
    return value


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
        raise KeyManagementError("key metadata must be canonical JSON") from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class KeyId:
    """Stable identifier for externally managed key material."""

    key_id: str
    provider_id: str
    purpose: str
    key_material_present: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_id", _token("key_id", self.key_id))
        object.__setattr__(self, "provider_id", _token("provider_id", self.provider_id))
        object.__setattr__(self, "purpose", _token("purpose", self.purpose))
        if self.key_material_present is not False:
            raise KeyManagementError("KeyId cannot carry key material")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "key_id": self.key_id,
                "provider_id": self.provider_id,
                "purpose": self.purpose,
                "key_material_present": False,
            }
        )


@dataclass(frozen=True, slots=True)
class KeyVersion:
    """Metadata for one immutable external key version."""

    key_id: str
    version: int
    state: str
    created_at_ns: int
    predecessor_digest: str | None = None
    key_material_present: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_id", _token("key_id", self.key_id))
        object.__setattr__(self, "version", _positive_int("version", self.version))
        state = _token("state", self.state)
        if state not in _STATES:
            raise KeyManagementError("state must be active, retired, or revoked")
        object.__setattr__(self, "state", state)
        object.__setattr__(
            self,
            "created_at_ns",
            _non_negative_int("created_at_ns", self.created_at_ns),
        )
        if self.version == 1:
            if self.predecessor_digest is not None:
                raise KeyManagementError("first key version cannot have predecessor")
        else:
            object.__setattr__(
                self,
                "predecessor_digest",
                _sha256("predecessor_digest", self.predecessor_digest),
            )
        if self.key_material_present is not False:
            raise KeyManagementError("KeyVersion cannot carry key material")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "key_id": self.key_id,
                "version": self.version,
                "state": self.state,
                "created_at_ns": self.created_at_ns,
                "predecessor_digest": self.predecessor_digest,
                "key_material_present": False,
            }
        )


__all__ = [
    "KeyId",
    "KeyManagementError",
    "KeyVersion",
]
