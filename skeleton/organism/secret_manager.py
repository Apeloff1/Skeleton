"""Secret manager — encrypted credential storage with rotation.

Provides a simple secret manager for API keys, tokens, and passwords.
Uses Fernet symmetric encryption with key derivation from a master
secret. Supports versioning and rotation tracking.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


try:
    from cryptography.fernet import Fernet
except Exception:
    Fernet = None


class SecretManager:
    """Encrypted secret storage with versioning."""

    def __init__(self, root: Optional[Path] = None, master_secret: Optional[str] = None):
        self.root = root or Path(".skeleton")
        self._master = master_secret or os.environ.get("SKELETON_MASTER_SECRET", "default-secret-change-me")
        self._key = self._derive_key(self._master)
        self._fernet = Fernet(self._key) if Fernet else None
        self._secrets: Dict[str, Dict[str, Any]] = {}
        self._file = self.root / "secrets.json"
        self._load()

    def _derive_key(self, secret: str) -> bytes:
        digest = hashlib.sha256(secret.encode()).digest()
        return base64.urlsafe_b64encode(digest)

    def _load(self) -> None:
        if self._file.exists():
            data = json.loads(self._file.read_text(encoding="utf-8"))
            self._secrets = data.get("secrets", {})

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps({"secrets": self._secrets}, indent=2), encoding="utf-8")

    def _encrypt(self, plaintext: str) -> str:
        if not self._fernet:
            return base64.b64encode(plaintext.encode()).decode()
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        if not self._fernet:
            return base64.b64decode(ciphertext.encode()).decode()
        return self._fernet.decrypt(ciphertext.encode()).decode()

    def set(self, name: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        version = (self._secrets.get(name, {}).get("version", 0) + 1)
        self._secrets[name] = {
            "encrypted": self._encrypt(value),
            "version": version,
            "updated_at": __import__("time").time(),
            "metadata": metadata or {},
        }
        self._save()

    def get(self, name: str) -> Optional[str]:
        entry = self._secrets.get(name)
        if not entry:
            return None
        return self._decrypt(entry["encrypted"])

    def rotate(self, name: str, new_value: str) -> None:
        self.set(name, new_value, metadata={"rotated": True})

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "secret-manager-card",
            "secrets": len(self._secrets),
            "encrypted": self._fernet is not None,
        }
