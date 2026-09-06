"""HMAC request seal for forge mutate routes (gameforge-rs seal.rs wire format).

Wire header ``x-gf-seal``::

    {attester}.{unix_expiry}.{hex_hmac_sha256(attester|expiry, secret)}

Secret from ``GF_SEAL_SECRET``. Empty/missing → fail closed (503).
Missing/malformed/expired/bad signature → 401 AuthError (opaque).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Optional

from fastapi import Header, HTTPException

from skeleton.api.middleware import AuthError

_OPAQUE = "invalid seal"
_ENV = "GF_SEAL_SECRET"
DEFAULT_TTL_SECS = 300


def _resolve_secret(secret: Optional[str] = None) -> Optional[str]:
    if secret is not None:
        return secret or None
    value = os.environ.get(_ENV)
    return value or None


def _sign(attester: str, expiry: int, secret: str) -> str:
    msg = f"{attester}|{expiry}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def mint_seal(
    attester: str,
    ttl_secs: int = DEFAULT_TTL_SECS,
    *,
    secret: Optional[str] = None,
    now: Optional[float] = None,
) -> Optional[str]:
    """Mint an ``x-gf-seal`` value. Returns ``None`` if secret is unset/empty."""
    resolved = _resolve_secret(secret)
    if not resolved:
        return None
    if not attester:
        return None
    ts = int(now if now is not None else time.time())
    expiry = ts + int(ttl_secs)
    sig = _sign(attester, expiry, resolved)
    return f"{attester}.{expiry}.{sig}"


def verify_seal(
    raw_header: Optional[str],
    *,
    secret: Optional[str] = None,
    now: Optional[float] = None,
) -> str:
    """Verify seal header; return attester. Raises AuthError on any auth failure."""
    resolved = _resolve_secret(secret)
    if not resolved:
        # Caller (require_seal) should 503 before this; still fail closed.
        raise AuthError(_OPAQUE)
    if not raw_header or not isinstance(raw_header, str):
        raise AuthError(_OPAQUE)
    parts = raw_header.rsplit(".", 2)
    if len(parts) != 3:
        raise AuthError(_OPAQUE)
    attester, expiry_s, sig = parts
    if not attester or not expiry_s or not sig:
        raise AuthError(_OPAQUE)
    try:
        expiry = int(expiry_s)
    except ValueError as exc:
        raise AuthError(_OPAQUE) from exc
    if len(sig) != 64 or any(c not in "0123456789abcdef" for c in sig):
        raise AuthError(_OPAQUE)
    ts = int(now if now is not None else time.time())
    if ts > expiry:
        raise AuthError(_OPAQUE)
    expected = _sign(attester, expiry, resolved)
    if not hmac.compare_digest(expected, sig):
        raise AuthError(_OPAQUE)
    return attester


def require_seal(
    x_gf_seal: Optional[str] = Header(default=None, alias="x-gf-seal"),
) -> str:
    """FastAPI dependency: gate mutate routes on a valid ``x-gf-seal``."""
    if not _resolve_secret():
        raise HTTPException(status_code=503, detail="seal unavailable")
    return verify_seal(x_gf_seal)
