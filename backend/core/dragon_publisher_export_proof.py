"""Offline verification of an independently supplied publisher export manifest.

No token, account password, session cookie, network transport, remote key
discovery, or new source permission. Trust the public key fingerprint only
when an operator obtains it independently from an authorized publisher.
A valid signature proves possession of the pinned key, not license or
permission to acquire a restricted resource.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass

_HEX = re.compile(r"[0-9a-f]+\Z")
MAX_SIGNED_BYTES = 64 * 1024
SCHEMA = "skeleton.dragon.publisher-export-proof.v1"


def _hex(value, size):
    if not isinstance(value, str) or len(value) != 2 * size or not _HEX.fullmatch(value):
        raise ValueError("noncanonical publisher proof encoding")
    return bytes.fromhex(value)


@dataclass(frozen=True, slots=True)
class PublisherExportProof:
    """Detached Ed25519 signature over the exact raw manifest bytes."""

    public_key_hex: str
    expected_key_sha256: str
    signature_hex: str

    def __post_init__(self):
        key = _hex(self.public_key_hex, 32)
        pin = _hex(self.expected_key_sha256, 32)
        _hex(self.signature_hex, 64)
        if not hmac.compare_digest(hashlib.sha256(key).digest(), pin):
            raise ValueError("publisher public key pin differs")

    def verify(self, raw: bytes) -> dict:
        if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_SIGNED_BYTES:
            raise ValueError("signed manifest byte bound")
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError as exc:
            raise RuntimeError("approved Ed25519 verification dependency unavailable") from exc
        key = Ed25519PublicKey.from_public_bytes(_hex(self.public_key_hex, 32))
        try:
            key.verify(_hex(self.signature_hex, 64), raw)
        except InvalidSignature as exc:
            raise ValueError("publisher manifest signature differs") from exc
        return {"schema": SCHEMA,
                "algorithm": "Ed25519",
                "manifest_sha256": hashlib.sha256(raw).hexdigest(),
                "public_key_sha256": self.expected_key_sha256,
                "signature_verified": True,
                "publisher_identity_independently_verified": False,
                "source_rights_verified": False,
                "network_authorized": False}
