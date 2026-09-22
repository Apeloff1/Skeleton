"""Vault sealed store — encrypted-at-rest secrets with integrity checks.

AccessPolicy gates who may read; SealedStore is what the storage layer
actually does: values are wrapped under a KMS data key before they ever
touch the dict, and every read re-verifies an integrity hash.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Dict, Optional, Tuple

from skeleton.kernel.errors import VaultError
from skeleton.vault.kms import EnvelopeKMS


class IntegrityError(VaultError):
    code = "VLT.INTEGRITY"


class SealedStore:
    """In-memory encrypted store wired through the vault EnvelopeKMS."""

    def __init__(self, kms: EnvelopeKMS, *, on_access: Optional[Callable[[str, str], None]] = None) -> None:
        self._kms = kms
        self._data_key = kms.generate_data_key()
        self._slots: Dict[str, Tuple[bytes, str]] = {}  # ciphertext, integrity hash
        self._on_access = on_access

    def put(self, secret_id: str, plaintext: bytes) -> None:
        ciphertext = self._wrap(plaintext)
        digest = hashlib.sha256(plaintext).hexdigest()
        self._slots[secret_id] = (ciphertext, digest)

    def get(self, secret_id: str) -> bytes:
        entry = self._slots.get(secret_id)
        if entry is None:
            raise IntegrityError("unknown secret", context={"secret": secret_id})
        ciphertext, digest = entry
        plaintext = self._wrap(ciphertext)
        if hashlib.sha256(plaintext).hexdigest() != digest:
            raise IntegrityError("integrity check failed", context={"secret": secret_id})
        if self._on_access is not None:
            self._on_access(secret_id, "read")
        return plaintext

    def delete(self, secret_id: str) -> bool:
        return self._slots.pop(secret_id, None) is not None

    def names(self) -> Tuple[str, ...]:
        return tuple(sorted(self._slots))

    # XOR keystream via the KMS data key; swap for AES-GCM behind the same API.
    def _wrap(self, data: bytes) -> bytes:
        key = self._kms.unwrap(self._data_key.key_id)
        stream = (key * (len(data) // len(key) + 1))[: len(data)]
        return bytes(a ^ b for a, b in zip(data, stream))
