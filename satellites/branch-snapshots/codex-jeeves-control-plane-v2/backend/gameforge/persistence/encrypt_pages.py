from __future__ import annotations
"""
Encrypt pages for MarathonStore / Chronoback payloads.
Uses AES-GCM when cryptography available; falls back to XOR+HMAC envelope (dev only).
"""

import base64
import hashlib
import hmac
import os
from typing import Optional


def _derive(key: bytes, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", key, salt, 120000, dklen=32)


class PageCipher:
    def __init__(self, passphrase: Optional[str] = None):
        raw = (passphrase or os.getenv("GAMEFORGE_MASTER_KEY") or "zaibatsu-dev-key").encode()
        self.salt = hashlib.sha256(b"gameforge-chronoback").digest()[:16]
        self.key = _derive(raw, self.salt)
        self._aes = None
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            self._aes = AESGCM
        except Exception:
            self._aes = None

    def encrypt(self, plaintext: bytes) -> bytes:
        if self._aes:
            nonce = os.urandom(12)
            ct = self._aes(self.key).encrypt(nonce, plaintext, None)
            return b"AGCM" + nonce + ct
        # fallback envelope (not for production secrets)
        nonce = os.urandom(16)
        stream = hashlib.sha256(self.key + nonce).digest()
        out = bytes(b ^ stream[i % len(stream)] for i, b in enumerate(plaintext))
        tag = hmac.new(self.key, nonce + out, hashlib.sha256).digest()[:16]
        return b"XOR1" + nonce + tag + out

    def decrypt(self, blob: bytes) -> bytes:
        if blob.startswith(b"AGCM") and self._aes:
            nonce, ct = blob[4:16], blob[16:]
            return self._aes(self.key).decrypt(nonce, ct, None)
        if blob.startswith(b"XOR1"):
            nonce, tag, out = blob[4:20], blob[20:36], blob[36:]
            expect = hmac.new(self.key, nonce + out, hashlib.sha256).digest()[:16]
            if not hmac.compare_digest(tag, expect):
                raise ValueError("integrity_fail")
            stream = hashlib.sha256(self.key + nonce).digest()
            return bytes(b ^ stream[i % len(stream)] for i, b in enumerate(out))
        raise ValueError("unknown_envelope")

    def encrypt_b64(self, text: str) -> str:
        return base64.b64encode(self.encrypt(text.encode())).decode()

    def decrypt_b64(self, token: str) -> str:
        return self.decrypt(base64.b64decode(token.encode())).decode()
