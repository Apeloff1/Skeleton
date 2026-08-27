"""Vault envelope encryption — master KMS → data keys → secrets.

The vault stores ciphertext; the encryption boundary lives at the vault.
EnvelopeKMS generates/maintains data keys and unwraps them with a
master key held at boot. This is structural — swapping the cryptography
backend later touches one module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from skeleton.kernel.errors import VaultError


class EnvelopeError(VaultError):
    code = "VLT.ENVELOPE"


@dataclass(frozen=True)
class DataKey:
    key_id: str
    wrapped: bytes  # encrypted with master key
    plain: bytes  # plaintext data key (local RAM only)


class EnvelopeKMS:
    """Request/keep data keys; wrap/unwrap with master key."""

    def __init__(self, master_key: bytes) -> None:
        if not master_key:
            raise EnvelopeError("master key must be non-empty")
        self._master = master_key
        self._keys: Dict[str, DataKey] = {}
        self._next_id = 0

    def generate_data_key(self) -> DataKey:
        """Generate + wrap a fresh 32-byte data key."""
        self._next_id += 1
        plain = os.urandom(32)
        wrapped = self._xor_wrap(plain)
        key = DataKey(key_id=f"dk-{self._next_id}", wrapped=wrapped, plain=plain)
        self._keys[key.key_id] = key
        return key

    def rotate_master(self, new_master: bytes) -> int:
        """Rewrap all data keys under the new master. Returns count rotated."""
        if not new_master:
            raise EnvelopeError("new master must be non-empty")
        count = 0
        for key_id, key in self._keys.items():
            # unwrap with old master using a deterministic XOR keystream
            plain = self._xor_unwrap(key.wrapped)
            self._master = new_master
            self._keys[key_id] = DataKey(
                key_id=key.key_id,
                wrapped=self._xor_wrap(plain),
                plain=plain,
            )
            count += 1
        return count

    def unwrap(self, key_id: str) -> bytes:
        key = self._keys.get(key_id)
        if key is None:
            raise EnvelopeError("unknown data key", context={"key_id": key_id})
        return key.plain

    # intentionally straightforward; real deployments wire AES-GCM via the
    # cryptography library behind the same interface.
    def _xor_wrap(self, data: bytes) -> bytes:
        master = (self._master * (len(data) // len(self._master) + 1))[: len(data)]
        return bytes(a ^ b for a, b in zip(data, master))

    def _xor_unwrap(self, data: bytes) -> bytes:
        return self._xor_wrap(data)
