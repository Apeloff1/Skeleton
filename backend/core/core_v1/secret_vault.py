"""Encryption at rest for webhook signing secrets.

``EncryptedSecretRepository`` decorates a raw blob store (SQLite or memory)
and implements the service's ``SecretRepository`` port:

* ``put`` always stores an envelope sealed under the active KEK, with the
  row's ``tenant_id|secret_id`` as associated data.
* ``get`` opens envelopes; legacy plaintext rows (``whsec_...``) are
  returned as-is only while ``allow_plaintext_read`` is on, which is the
  migration window. After ``SecretMigrator.encrypt_plaintext`` reports
  ``remaining == 0`` operators can switch it off (fail closed).

Plaintext and envelopes cannot be confused: plaintext secrets always start
with ``whsec_`` and envelopes with ``CSE``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from . import envelope
from .envelope import EnvelopeError
from .keys import KeyProvider

log = logging.getLogger("skeleton.backend_core.secrets")
PLAINTEXT_PREFIX = b"whsec_"


@dataclass(frozen=True)
class SecretRow:
    secret_id: str
    tenant_id: str
    blob: bytes
    created_at: float


class SecretBlobStore(Protocol):
    """Raw storage for secret blobs (no crypto). Implemented by both adapters."""
    def put(self, secret_id: str, tenant_id: str, secret: bytes, created_at: float) -> None: ...
    def get(self, tenant_id: str, secret_id: str) -> bytes | None: ...
    def scan(self, after_id: str, limit: int) -> list[SecretRow]:
        """Rows with ``secret_id > after_id`` ordered by ``secret_id``."""
    def compare_and_set(self, secret_id: str, expected: bytes, new: bytes, key_id: str) -> bool: ...
    def count_by_key(self) -> dict[str, int]:
        """``{"<key_id>": n, "": plaintext_rows}``."""


class SecretDecryptError(RuntimeError):
    """A stored secret could not be opened. Dispatch treats it as 'no secret'."""


def classify_blob(blob: bytes) -> str:
    """``'plaintext'`` | ``'envelope'`` | ``'unknown'``."""
    b = bytes(blob)
    if b.startswith(PLAINTEXT_PREFIX):
        return "plaintext"
    if envelope.is_envelope(b):
        return "envelope"
    return "unknown"


class EncryptedSecretRepository:
    def __init__(self, store: SecretBlobStore, provider: KeyProvider, *,
                 allow_plaintext_read: bool = True) -> None:
        self.store, self.provider = store, provider
        self.allow_plaintext_read = allow_plaintext_read

    def put(self, secret_id: str, tenant_id: str, secret: bytes, created_at: float) -> None:
        blob = envelope.seal(self.provider, secret, envelope.secret_aad(tenant_id, secret_id))
        self.store.put(secret_id, tenant_id, blob, created_at)

    def get(self, tenant_id: str, secret_id: str) -> bytes | None:
        blob = self.store.get(tenant_id, secret_id)
        if blob is None:
            return None
        kind = classify_blob(blob)
        if kind == "plaintext":
            if not self.allow_plaintext_read:
                log.error("plaintext webhook secret refused (secret_id=%s)", secret_id)
                raise SecretDecryptError("plaintext secret refused; run the secret migration")
            return bytes(blob)
        try:
            return envelope.open_(self.provider, blob, envelope.secret_aad(tenant_id, secret_id))
        except EnvelopeError as exc:
            log.error("webhook secret could not be opened (secret_id=%s): %s", secret_id, exc)
            raise SecretDecryptError(str(exc)) from None


class PlaintextSecretRepository:
    """Explicit pass-through used only when no keyring is configured (dev)."""

    def __init__(self, store: SecretBlobStore) -> None:
        self.store = store

    def put(self, secret_id: str, tenant_id: str, secret: bytes, created_at: float) -> None:
        self.store.put(secret_id, tenant_id, secret, created_at)

    def get(self, tenant_id: str, secret_id: str) -> bytes | None:
        blob = self.store.get(tenant_id, secret_id)
        if blob is not None and classify_blob(blob) != "plaintext":
            # Encrypted row but no keyring: never sign with ciphertext.
            raise SecretDecryptError("secret is encrypted but no keyring is configured")
        return blob


__all__ = ["EncryptedSecretRepository", "PlaintextSecretRepository", "SecretBlobStore", "SecretRow",
           "SecretDecryptError", "classify_blob", "PLAINTEXT_PREFIX"]
