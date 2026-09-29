"""Vault key versioning — manage master key generations safely.

EnvelopeKMS validates all keys before an atomic rotation. KeyRegistry advances
its generation only after that rotation succeeds and tracks registered keys
against the committed generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from skeleton.kernel.errors import VaultError
from skeleton.vault.kms import DataKey, EnvelopeKMS


class KeyVersionError(VaultError):
    code = "VLT.KEY_VERSION"


@dataclass
class KeyVersion:
    generation: int
    data_keys: Dict[str, DataKey]


class KeyRegistry:
    """Track which master generation produced each data key."""

    def __init__(self, kms: EnvelopeKMS) -> None:
        self._kms = kms
        self._generation = 0
        self._versions: Dict[str, int] = {}  # key_id -> generation

    def register(self, key: DataKey) -> None:
        self._versions[key.key_id] = self._generation

    def rotate(self, new_master: bytes) -> int:
        rotated = self._kms.rotate_master(new_master)
        self._generation += 1
        for key_id in list(self._versions):
            self._versions[key_id] = self._generation
        return rotated

    def generation_of(self, key_id: str) -> int:
        gen = self._versions.get(key_id)
        if gen is None:
            raise KeyVersionError("unknown data key", context={"key": key_id})
        return gen

    def pending_rotation(self) -> Tuple[str, ...]:
        """Keys still on an older generation."""
        return tuple(
            key_id
            for key_id, gen in self._versions.items()
            if gen != self._generation
        )

    def current_generation(self) -> int:
        return self._generation
