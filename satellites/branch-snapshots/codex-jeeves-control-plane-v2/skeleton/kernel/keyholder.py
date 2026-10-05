"""keyholder — process signing identity (gameforge-rs keyholder.rs port).

One keypair per process, minted at first use or loaded from
``GF_KEYHOLDER_SEED`` (hex, 32 bytes). The public identity is derived;
the seed never leaves this module — callers get signatures, not keys.

Placeholder crypto (sha256) matching the RS interface; swap to real
ed25519 later without touching callers.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from typing import Optional

_ENV = "GF_KEYHOLDER_SEED"
_lock = threading.Lock()
_instance: Optional["Keyholder"] = None


def _sha256(*parts: bytes) -> bytes:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
    return h.digest()


class Keyholder:
    """Process-local signing identity."""

    def __init__(self, seed: bytes) -> None:
        if len(seed) != 32:
            raise ValueError("keyholder seed must be 32 bytes")
        self._seed = seed
        # public = sha256(seed) truncated — placeholder until real ed25519.
        self._public = _sha256(seed)[:16].hex()

    @classmethod
    def mint(cls, seed: bytes) -> "Keyholder":
        return cls(seed)

    @classmethod
    def from_env(cls, env: Optional[str] = None) -> "Keyholder":
        raw = env if env is not None else os.environ.get(_ENV)
        if raw:
            try:
                decoded = bytes.fromhex(raw.strip())
            except ValueError as exc:
                raise ValueError("GF_KEYHOLDER_SEED must be hex") from exc
            if len(decoded) != 32:
                raise ValueError("GF_KEYHOLDER_SEED must decode to 32 bytes")
            return cls.mint(decoded)
        # Ephemeral: mix time + pid then sha256 → 32 bytes.
        now = time.time_ns().to_bytes(8, "little", signed=False)
        pid = os.getpid().to_bytes(4, "little", signed=False)
        pad = b"\x00" * 20
        material = (now + pid + pad)[:32]
        return cls.mint(_sha256(material))

    @property
    def public_hex(self) -> str:
        return self._public

    def sign(self, msg: bytes) -> str:
        """Deterministic placeholder: sha256(seed || msg)."""
        return _sha256(self._seed, msg).hex()

    def verify(self, msg: bytes, signature: str) -> bool:
        return self.sign(msg) == signature


def get_keyholder() -> Keyholder:
    """Process singleton — mirrors RS ``Keyholder::get`` / OnceLock."""
    global _instance
    if _instance is not None:
        return _instance
    with _lock:
        if _instance is None:
            _instance = Keyholder.from_env()
        return _instance


def reset_keyholder_for_tests() -> None:
    """Clear the singleton (tests only)."""
    global _instance
    with _lock:
        _instance = None
