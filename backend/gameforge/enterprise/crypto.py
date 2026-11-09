from __future__ import annotations
import os
import base64
import hashlib
from typing import Any, Dict

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None


class LocalDevKeyProvider:
    def __init__(self):
        seed = os.getenv("GAMEFORGE_LOCAL_KMS_SEED", "gameforge-dev-seed").encode()
        self._root = hashlib.sha256(seed).digest()

    def current_key_id(self, tenant_id: str) -> str:
        return f"local:{tenant_id}:v1"

    def get_dek(self, tenant_id: str, key_id: str | None = None) -> bytes:
        material = hashlib.sha256(self._root + tenant_id.encode()).digest()
        return material


class EnvelopeEncryptor:
    def __init__(self, provider=None):
        self.provider = provider or LocalDevKeyProvider()
        self.enabled = os.getenv("GAMEFORGE_ENCRYPTION", "0") == "1"

    def encrypt(self, tenant_id: str, plaintext: bytes) -> Dict[str, Any]:
        if not self.enabled or AESGCM is None:
            return {
                "alg": "plain",
                "key_id": "none",
                "nonce": "",
                "ciphertext": base64.b64encode(plaintext).decode("ascii"),
            }
        key = self.provider.get_dek(tenant_id)
        nonce = os.urandom(12)
        ct = AESGCM(key).encrypt(nonce, plaintext, tenant_id.encode())
        return {
            "alg": "AESGCM",
            "key_id": self.provider.current_key_id(tenant_id),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ct).decode("ascii"),
        }

    def decrypt(self, tenant_id: str, envelope: Dict[str, Any]) -> bytes:
        if envelope.get("alg") == "plain" or not self.enabled or AESGCM is None:
            return base64.b64decode(envelope["ciphertext"])
        key = self.provider.get_dek(tenant_id, envelope.get("key_id"))
        nonce = base64.b64decode(envelope["nonce"])
        ct = base64.b64decode(envelope["ciphertext"])
        return AESGCM(key).decrypt(nonce, ct, tenant_id.encode())
