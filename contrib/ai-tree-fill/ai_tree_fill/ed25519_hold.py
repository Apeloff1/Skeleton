"""Ed25519 process identity. The sha256 keyholder envelope stays a compatibility receipt."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat


@dataclass(frozen=True)
class Ed25519Envelope:
    key_id: str
    signature: str
    alg: str = "Ed25519"

    def __post_init__(self) -> None:
        if len(self.key_id) != 64:
            raise ValueError("ed25519 key id is 32 raw bytes hex")
        if len(self.signature) != 128:
            raise ValueError("ed25519 signature is 64 raw bytes hex")


class Ed25519Hold:
    def __init__(self, seed: bytes) -> None:
        if len(seed) != 32:
            raise ValueError("seed must be 32 bytes")
        self._seed = seed
        self._private = Ed25519PrivateKey.from_private_bytes(seed)
        self._public = self._private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    @classmethod
    def mint(cls) -> "Ed25519Hold":
        return cls(os.urandom(32))

    @classmethod
    def from_seed_hex(cls, raw: str) -> "Ed25519Hold":
        seed = bytes.fromhex(raw.strip())
        return cls(seed)

    @property
    def public_hex(self) -> str:
        return self._public.hex()

    def sign(self, msg: bytes) -> Ed25519Envelope:
        signature = self._private.sign(msg)
        return Ed25519Envelope(self.public_hex, signature.hex())

    def verify(self, msg: bytes, envelope: Ed25519Envelope) -> bool:
        if envelope.key_id != self.public_hex:
            return False
        public = Ed25519PublicKey.from_public_bytes(self._public)
        public.verify(bytes.fromhex(envelope.signature), msg)
        return True

    def export_private_hex(self) -> str:
        raw = self._private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        return raw.hex()

    def fingerprint(self) -> str:
        return hashlib.sha256(self._public).hexdigest()
