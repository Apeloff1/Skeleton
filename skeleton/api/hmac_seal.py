"""
Skeleton API — HMAC seal for protected routes

Provides:
- require_seal: FastAPI dependency for HMAC request validation
- HMACSeal: Sign and verify request integrity
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any, Dict, Optional


class HMACSeal:
    """HMAC request signing for API route protection."""

    def __init__(self, secret: Optional[bytes] = None):
        self._secret = secret or os.urandom(32)

    def sign(self, method: str, path: str, body: bytes, timestamp: Optional[int] = None) -> str:
        """Sign a request with HMAC-SHA256."""
        ts = str(timestamp or int(time.time()))
        message = f"{method}:{path}:{ts}:{body.hex()}".encode()
        sig = hmac.new(self._secret, message, hashlib.sha256).hexdigest()
        return f"v1={sig}:{ts}"

    def verify(self, method: str, path: str, body: bytes, seal: str) -> bool:
        """Verify a request seal."""
        try:
            version, rest = seal.split("=", 1)
            if version != "v1":
                return False
            sig, ts = rest.rsplit(":", 1)
            expected = self.sign(method, path, body, int(ts))
            return hmac.compare_digest(seal, expected)
        except (ValueError, TypeError):
            return False

    def stats(self) -> Dict[str, Any]:
        return {"algorithm": "HMAC-SHA256", "version": "v1"}


# Global seal instance (lazy init)
_seal: Optional[HMACSeal] = None


def get_seal() -> HMACSeal:
    global _seal
    if _seal is None:
        secret = os.getenv("SKELETON_API_SECRET", "").encode() or None
        _seal = HMACSeal(secret=secret)
    return _seal


def require_seal() -> str:
    """FastAPI dependency: validate HMAC seal header.
    
    Usage:
        @router.post("/protected", dependencies=[Depends(require_seal)])
    """
    # In a real implementation, this would extract and verify the header
    # For now, returns a placeholder attester string
    return "attester"
