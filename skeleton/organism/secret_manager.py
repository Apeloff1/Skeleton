"""Secret manager — encrypted credential storage with rotation.

Provides a simple secret manager for API keys, tokens, and passwords.
Persistent storage is enabled only when an explicit master secret is
provided (constructor or ``SKELETON_MASTER_SECRET``). There is no shared
fallback key: an unconfigured manager may boot safely, but it cannot read
or write persistent secrets.
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
    """Encrypted secret storage with versioning and explicit key ownership."""

    def __init__(self, root: Optional[Path] = None, master_secret: Optional[str] = None):
        self.root = root or Path(".skeleton")
        configured_secret = master_secret or os.environ.get("SKELETON_MASTER_SECRET")
        self._master_configured = bool(configured_secret)
        self._fernet = None
        if configured_secret and Fernet is not None:
            self._fernet = Fernet(self._derive_key(configured_secret))

        self._secrets: Dict[str, Dict[str, Any]] = {}
        self._file = self.root / "secrets.json"
        self._storage_state = self._initial_state()
        self._load()

    def _initial_state(self) -> str:
        if not self._master_configured:
            return "locked" if self._file.exists() else "unconfigured"
        if Fernet is None:
            return "crypto_unavailable"
        return "ready"

    def _derive_key(self, secret: str) -> bytes:
        digest = hashlib.sha256(secret.encode()).digest()
        return base64.urlsafe_b64encode(digest)

    def _load(self) -> None:
        if not self._file.exists():
            return
        if not self._master_configured:
            self._storage_state = "locked"
            return
        if self._fernet is None:
            self._storage_state = "crypto_unavailable"
            return

        raw = self._file.read_bytes()
        try:
            plaintext = self._fernet.decrypt(raw)
            data = json.loads(plaintext.decode("utf-8"))
            self._secrets = data.get("secrets", {})
            self._storage_state = "ready"
            return
        except Exception:
            pass

        # Backward-compatible migration path for an old cleartext document.
        # It is intentionally available only when the operator supplied a key;
        # the next successful write re-encrypts the whole document.
        try:
            data = json.loads(raw.decode("utf-8"))
            self._secrets = data.get("secrets", {})
            self._storage_state = "legacy_cleartext"
        except Exception:
            self._secrets = {}
            self._storage_state = "locked"

    def _require_writable(self) -> None:
        if not self._master_configured:
            raise RuntimeError(
                "Secret storage requires SKELETON_MASTER_SECRET or an explicit master_secret"
            )
        if self._fernet is None:
            raise RuntimeError("cryptography.Fernet required to persist secrets")
        if self._storage_state == "locked" and self._file.exists():
            raise RuntimeError("Secret store is locked; verify the configured master secret")

    def _save(self) -> None:
        self._require_writable()
        self.root.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"secrets": self._secrets}, indent=2).encode("utf-8")
        self._file.write_bytes(self._fernet.encrypt(payload))
        self._storage_state = "ready"

    def _encrypt(self, plaintext: str) -> str:
        self._require_writable()
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        if self._fernet is None or self._storage_state == "locked":
            raise RuntimeError("Secret store is not available for decryption")
        return self._fernet.decrypt(ciphertext.encode()).decode()

    def set(self, name: str, value: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._require_writable()
        version = self._secrets.get(name, {}).get("version", 0) + 1
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
            "encrypted": self._fernet is not None and self._storage_state in {"ready", "legacy_cleartext"},
            "master_key_configured": self._master_configured,
            "storage_state": self._storage_state,
        }
