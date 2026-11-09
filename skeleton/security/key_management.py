"""Versioned key metadata contracts for the AI runtime.

This module models identifiers, lifecycle metadata, and rotation evidence only.
It never stores, derives, unwraps, encrypts with, decrypts with, or otherwise
handles cryptographic key material.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable


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


@dataclass(frozen=True, slots=True)
class KeyRotation:
    """Evidence that one key version was superseded by another."""

    rotation_id: str
    key_id: str
    from_version: int
    to_version: int
    from_version_digest: str
    to_version_digest: str
    reason_code: str
    rotated_at_ns: int
    key_material_present: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "rotation_id", _token("rotation_id", self.rotation_id))
        object.__setattr__(self, "key_id", _token("key_id", self.key_id))
        object.__setattr__(
            self,
            "from_version",
            _positive_int("from_version", self.from_version),
        )
        object.__setattr__(
            self,
            "to_version",
            _positive_int("to_version", self.to_version),
        )
        if self.to_version <= self.from_version:
            raise KeyManagementError("rotation must advance key version")
        object.__setattr__(
            self,
            "from_version_digest",
            _sha256("from_version_digest", self.from_version_digest),
        )
        object.__setattr__(
            self,
            "to_version_digest",
            _sha256("to_version_digest", self.to_version_digest),
        )
        object.__setattr__(self, "reason_code", _token("reason_code", self.reason_code))
        object.__setattr__(
            self,
            "rotated_at_ns",
            _non_negative_int("rotated_at_ns", self.rotated_at_ns),
        )
        if self.key_material_present is not False:
            raise KeyManagementError("KeyRotation cannot carry key material")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "rotation_id": self.rotation_id,
                "key_id": self.key_id,
                "from_version": self.from_version,
                "to_version": self.to_version,
                "from_version_digest": self.from_version_digest,
                "to_version_digest": self.to_version_digest,
                "reason_code": self.reason_code,
                "rotated_at_ns": self.rotated_at_ns,
                "key_material_present": False,
            }
        )


def record_key_rotation(
    *,
    rotation_id: str,
    previous: KeyVersion,
    current: KeyVersion,
    reason_code: str,
    rotated_at_ns: int,
) -> KeyRotation:
    """Bind a rotation receipt to exact immutable version metadata."""

    if not isinstance(previous, KeyVersion):
        raise TypeError("previous must be KeyVersion")
    if not isinstance(current, KeyVersion):
        raise TypeError("current must be KeyVersion")
    if previous.key_id != current.key_id:
        raise KeyManagementError("rotation cannot change key identity")
    if current.version <= previous.version:
        raise KeyManagementError("rotation must advance key version")
    if current.predecessor_digest != previous.digest:
        raise KeyManagementError("new key version must bind predecessor digest")
    if current.created_at_ns < previous.created_at_ns:
        raise KeyManagementError("new key version cannot predate previous version")
    if rotated_at_ns < current.created_at_ns:
        raise KeyManagementError("rotation receipt cannot predate new key version")

    return KeyRotation(
        rotation_id=rotation_id,
        key_id=previous.key_id,
        from_version=previous.version,
        to_version=current.version,
        from_version_digest=previous.digest,
        to_version_digest=current.digest,
        reason_code=reason_code,
        rotated_at_ns=rotated_at_ns,
    )


def validate_key_history(
    versions: Iterable[KeyVersion],
    rotations: Iterable[KeyRotation],
) -> str:
    """Validate an immutable version/rotation chain and return its digest."""

    version_rows = tuple(versions)
    rotation_rows = tuple(rotations)
    if not version_rows:
        raise KeyManagementError("key history must contain at least one version")
    if any(not isinstance(item, KeyVersion) for item in version_rows):
        raise KeyManagementError("key history must contain KeyVersion values")
    if any(not isinstance(item, KeyRotation) for item in rotation_rows):
        raise KeyManagementError("key history must contain KeyRotation values")

    ordered = tuple(sorted(version_rows, key=lambda item: item.version))
    if len({item.version for item in ordered}) != len(ordered):
        raise KeyManagementError("key history version numbers must be unique")
    key_ids = {item.key_id for item in ordered}
    if len(key_ids) != 1:
        raise KeyManagementError("key history cannot mix key identities")
    if ordered[0].version != 1 or ordered[0].predecessor_digest is not None:
        raise KeyManagementError("key history must start at version 1")

    for previous, current in zip(ordered, ordered[1:]):
        if current.version != previous.version + 1:
            raise KeyManagementError("key history versions must be contiguous")
        if current.predecessor_digest != previous.digest:
            raise KeyManagementError("key history predecessor digest mismatch")
        if current.created_at_ns < previous.created_at_ns:
            raise KeyManagementError("key history creation times must be monotonic")

    if len(rotation_rows) != max(0, len(ordered) - 1):
        raise KeyManagementError("key history requires one rotation per transition")
    if len({item.rotation_id for item in rotation_rows}) != len(rotation_rows):
        raise KeyManagementError("key rotation IDs must be unique")

    by_transition = {
        (item.from_version, item.to_version): item
        for item in rotation_rows
    }
    if len(by_transition) != len(rotation_rows):
        raise KeyManagementError("key history rotation transitions must be unique")

    for previous, current in zip(ordered, ordered[1:]):
        rotation = by_transition.get((previous.version, current.version))
        if rotation is None:
            raise KeyManagementError("key history is missing rotation evidence")
        if rotation.key_id != previous.key_id:
            raise KeyManagementError("rotation evidence key identity mismatch")
        if rotation.from_version_digest != previous.digest:
            raise KeyManagementError("rotation source digest mismatch")
        if rotation.to_version_digest != current.digest:
            raise KeyManagementError("rotation destination digest mismatch")
        if rotation.rotated_at_ns < current.created_at_ns:
            raise KeyManagementError("rotation receipt predates destination version")

    return _digest(
        {
            "key_id": ordered[0].key_id,
            "versions": [item.digest for item in ordered],
            "rotations": [
                by_transition[(previous.version, current.version)].digest
                for previous, current in zip(ordered, ordered[1:])
            ],
        }
    )


__all__ = [
    "KeyId",
    "KeyManagementError",
    "KeyRotation",
    "KeyVersion",
    "record_key_rotation",
    "validate_key_history",
]
