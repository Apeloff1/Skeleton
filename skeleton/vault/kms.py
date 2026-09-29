"""Authenticated envelope encryption and in-process key rotation.

Historical masters are retained in memory for envelopes issued before rotation.
Callers must store master keys securely; this class is not a durable KMS.
Unauthenticated demonstration envelopes are deliberately rejected.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import secrets
from threading import RLock


@dataclass(frozen=True)
class DataKey:
    key_id: str
    context: str
    version: int
    nonce: bytes = field(repr=False)
    wrapped_key: bytes = field(repr=False)


class EnvelopeKMS:
    ALGORITHM = "envelope-aes-256-gcm-v1"

    def __init__(self, master_key: bytes | None = None):
        master = secrets.token_bytes(32) if master_key is None else master_key
        self._validate_master(master)
        self._masters = {0: master}
        self._generation = 0
        self._keys: dict[str, DataKey] = {}
        self._lock = RLock()

    @staticmethod
    def _validate_master(master):
        if not isinstance(master, bytes) or len(master) != 32:
            raise ValueError("master_key must contain exactly 32 bytes")

    @staticmethod
    def _context(context):
        if not isinstance(context, str) or not context:
            raise ValueError("context must be a nonempty string")
        return context.encode("utf-8")

    def derive_key(self, context: str) -> bytes:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        with self._lock:
            return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                        info=b"skeleton-vault-v1:" + self._context(context)).derive(
                            self._masters[self._generation])

    @staticmethod
    def _cipher(key: bytes):
        # Inspection and packaging can import Skeleton without loading native
        # cryptography. Actual encryption still requires the declared library;
        # there is deliberately no unauthenticated fallback.
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(key)

    def _wrap(self, key_id, context, raw, generation):
        nonce = secrets.token_bytes(12)
        aad = json.dumps([key_id, context, generation], separators=(",", ":")).encode()
        wrapped = self._cipher(self._masters[generation]).encrypt(nonce, raw, aad)
        return DataKey(key_id, context, generation, nonce, wrapped)

    def unwrap_key(self, key: DataKey) -> bytes:
        if not isinstance(key, DataKey):
            raise TypeError("key must be DataKey")
        with self._lock:
            aad = json.dumps([key.key_id, key.context, key.version], separators=(",", ":")).encode()
            return self._cipher(self._masters[key.version]).decrypt(key.nonce, key.wrapped_key, aad)

    def generate_data_key(self, context: str) -> DataKey:
        self._context(context)
        with self._lock:
            key = self._wrap(secrets.token_hex(16), context, secrets.token_bytes(32), self._generation)
            self._keys[key.key_id] = key
            return key

    def encrypt(self, plaintext: bytes, context: str) -> dict:
        if not isinstance(plaintext, bytes):
            raise TypeError("plaintext must be bytes")
        aad = self._context(context)
        with self._lock:
            key = self.generate_data_key(context)
            nonce = secrets.token_bytes(12)
            ciphertext = self._cipher(self.unwrap_key(key)).encrypt(nonce, plaintext, aad)
            return {"algorithm": self.ALGORITHM, "context": context,
                    "key_id": key.key_id, "version": key.version,
                    "wrapped_key": key.wrapped_key.hex(), "key_nonce": key.nonce.hex(),
                    "nonce": nonce.hex(), "ciphertext": ciphertext.hex()}

    def decrypt(self, envelope: dict) -> bytes:
        if not isinstance(envelope, dict) or envelope.get("algorithm") != self.ALGORITHM:
            raise ValueError("unsupported or unauthenticated envelope")
        version = envelope["version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise ValueError("invalid envelope key version")
        aad = self._context(envelope["context"])
        key = DataKey(envelope["key_id"], envelope["context"], version,
                      bytes.fromhex(envelope["key_nonce"]), bytes.fromhex(envelope["wrapped_key"]))
        with self._lock:
            return self._cipher(self.unwrap_key(key)).decrypt(
                bytes.fromhex(envelope["nonce"]), bytes.fromhex(envelope["ciphertext"]), aad)

    def rotate_master(self, new_master: bytes) -> int:
        self._validate_master(new_master)
        with self._lock:
            raw = {key_id: self.unwrap_key(key) for key_id, key in self._keys.items()}
            generation = self._generation + 1
            self._masters[generation] = new_master
            try:
                keys = {key_id: self._wrap(key_id, self._keys[key_id].context, value, generation)
                        for key_id, value in raw.items()}
            except Exception:
                del self._masters[generation]
                raise
            self._keys = keys
            self._generation = generation
            return len(keys)

    def rotate(self) -> None:
        self.rotate_master(secrets.token_bytes(32))

    def stats(self) -> dict:
        with self._lock:
            return {"algorithm": self.ALGORITHM, "key_rotations": self._generation,
                    "data_keys": len(self._keys)}


__all__ = ["DataKey", "EnvelopeKMS"]
