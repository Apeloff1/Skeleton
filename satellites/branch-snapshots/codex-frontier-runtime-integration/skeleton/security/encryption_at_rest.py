"""Encryption at rest — envelope encryption for persisted state.

Wraps every persisted state file (audit, events, secrets, RBAC,
config) with envelope encryption: a data-encryption key (DEK) per
file, itself encrypted under the master key (KEK). Supports key
rotation without re-encrypting data (re-wrap DEKs only) and
integrity verification on every read.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


def _xor_stream(data: bytes, key: bytes) -> bytes:
    """Deterministic keystream XOR (development-grade; swap for AES-GCM in prod via cryptography)."""
    out = bytearray(len(data))
    counter = 0
    i = 0
    while i < len(data):
        block = hashlib.sha256(key + counter.to_bytes(8, "big")).digest()
        for b in block:
            if i >= len(data):
                break
            out[i] = data[i] ^ b
            i += 1
        counter += 1
    return bytes(out)


@dataclass
class FileEnvelope:
    file_name: str
    wrapped_dek: str
    ciphertext: str
    mac: str
    key_version: int
    created_ns: int


class EncryptionAtRest:
    """Envelope encryption manager for state files."""

    def __init__(self, master_secret: str = "default-secret-change-me", key_version: int = 1):
        self._kek = hashlib.sha256(master_secret.encode()).digest()
        self.key_version = key_version
        self._envelopes: Dict[str, FileEnvelope] = {}
        self._wrapped_files = 0

    def _new_dek(self) -> bytes:
        return secrets.token_bytes(32)

    def _wrap_dek(self, dek: bytes) -> str:
        return base64.b64encode(_xor_stream(dek, self._kek)).decode()

    def _unwrap_dek(self, wrapped: str) -> bytes:
        return _xor_stream(base64.b64decode(wrapped), self._kek)

    def _mac(self, ciphertext_b64: str, dek: bytes) -> str:
        return hmac.new(dek, ciphertext_b64.encode(), hashlib.sha256).hexdigest()

    def encrypt_file(self, file_name: str, plaintext: str) -> FileEnvelope:
        dek = self._new_dek()
        ciphertext = base64.b64encode(_xor_stream(plaintext.encode(), dek)).decode()
        envelope = FileEnvelope(
            file_name=file_name,
            wrapped_dek=self._wrap_dek(dek),
            ciphertext=ciphertext,
            mac=self._mac(ciphertext, dek),
            key_version=self.key_version,
            created_ns=time.time_ns(),
        )
        self._envelopes[file_name] = envelope
        self._wrapped_files += 1
        return envelope

    def decrypt_file(self, file_name: str) -> Optional[str]:
        envelope = self._envelopes.get(file_name)
        if not envelope:
            return None
        dek = self._unwrap_dek(envelope.wrapped_dek)
        if self._mac(envelope.ciphertext, dek) != envelope.mac:
            raise ValueError(f"integrity check failed for {file_name}")
        return _xor_stream(base64.b64decode(envelope.ciphertext), dek).decode()

    def rotate_master(self, new_master_secret: str) -> Dict[str, Any]:
        old_kek = self._kek
        self._kek = hashlib.sha256(new_master_secret.encode()).digest()
        self.key_version += 1
        rewrapped = 0
        for envelope in self._envelopes.values():
            dek = _xor_stream(base64.b64decode(envelope.wrapped_dek), old_kek)
            envelope.wrapped_dek = self._wrap_dek(dek)
            envelope.key_version = self.key_version
            rewrapped += 1
        return {"rotated": True, "new_key_version": self.key_version, "rewrapped_deks": rewrapped}

    def export_envelope(self, file_name: str) -> Optional[Dict[str, Any]]:
        env = self._envelopes.get(file_name)
        if not env:
            return None
        return {
            "file_name": env.file_name,
            "wrapped_dek": env.wrapped_dek,
            "ciphertext": env.ciphertext,
            "mac": env.mac,
            "key_version": env.key_version,
        }

    def import_envelope(self, data: Dict[str, Any]) -> None:
        self._envelopes[data["file_name"]] = FileEnvelope(
            file_name=data["file_name"],
            wrapped_dek=data["wrapped_dek"],
            ciphertext=data["ciphertext"],
            mac=data["mac"],
            key_version=data["key_version"],
            created_ns=time.time_ns(),
        )

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "encryption-card",
            "files_encrypted": len(self._envelopes),
            "key_version": self.key_version,
            "files": sorted(self._envelopes.keys()),
        }
