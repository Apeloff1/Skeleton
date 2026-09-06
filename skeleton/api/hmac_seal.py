"""HMAC request seal for forge mutate routes (gameforge-rs seal.rs + Gate PrincipalAuth).

Wire header ``x-gf-seal`` (backward-compatible)::

    #16 / seal.rs (3-part)::
        {attester}.{unix_expiry}.{hex_hmac_sha256(attester|expiry, secret)}

    PrincipalAuth deepen (4-part)::
        {principal}.{attester}.{unix_expiry}.{hex_hmac_sha256(principal.attester.expiry, key)}

Secrets:
  - ``GF_SEAL_SECRET`` — primary utf-8 secret (#16 compat; also used to mint)
  - ``GF_SEAL_KEYRING`` — optional rotatable ring ``kid=secret[,kid=secret…]``
    Verify tries primary then every ring key (constant-time per candidate).
    Mint signs with primary (``GF_SEAL_SECRET``), else the first ring entry.

Empty/missing keyring+secret → fail closed (503).
Missing/malformed/expired/bad signature → 401 AuthError (opaque).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Dict, List, Optional, Tuple

from fastapi import Header, HTTPException

from skeleton.api.middleware import AuthError

_OPAQUE = "invalid seal"
_ENV = "GF_SEAL_SECRET"
_ENV_KEYRING = "GF_SEAL_KEYRING"
DEFAULT_TTL_SECS = 300


def _parse_keyring(raw: Optional[str]) -> Dict[str, bytes]:
    """Parse ``kid=secret,kid2=secret2`` into a keyring. Empty entries skipped."""
    out: Dict[str, bytes] = {}
    if not raw:
        return out
    for part in raw.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        kid, _, secret = part.partition("=")
        kid = kid.strip()
        secret = secret.strip()
        if kid and secret:
            out[kid] = secret.encode("utf-8")
    return out


def load_keyring(
    *,
    secret: Optional[str] = None,
    keyring: Optional[str] = None,
) -> Dict[str, bytes]:
    """Build verify keyring: optional primary ``default`` + ``GF_SEAL_KEYRING``."""
    ring = _parse_keyring(keyring if keyring is not None else os.environ.get(_ENV_KEYRING))
    primary = secret if secret is not None else os.environ.get(_ENV)
    if primary:
        # Primary wins as mint key; keep under stable id.
        ring = {"default": primary.encode("utf-8"), **{k: v for k, v in ring.items() if k != "default"}}
    return ring


def _resolve_secret(secret: Optional[str] = None) -> Optional[str]:
    """#16 helper: primary secret string only (no ring)."""
    if secret is not None:
        return secret or None
    value = os.environ.get(_ENV)
    return value or None


def _sign_legacy(attester: str, expiry: int, secret: str) -> str:
    msg = f"{attester}|{expiry}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def _sign_principal(principal: str, attester: str, expiry: int, key: bytes) -> str:
    payload = f"{principal}.{attester}.{expiry}".encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _ct_hex_eq(a: str, b: str) -> bool:
    if len(a) != len(b):
        return False
    try:
        return hmac.compare_digest(a, b)
    except (TypeError, ValueError):
        return False


def mint_seal(
    attester: str,
    ttl_secs: int = DEFAULT_TTL_SECS,
    *,
    secret: Optional[str] = None,
    principal: Optional[str] = None,
    now: Optional[float] = None,
) -> Optional[str]:
    """Mint an ``x-gf-seal`` value.

    Without ``principal`` → #16 3-part wire.
    With ``principal`` → 4-part PrincipalAuth wire (signed with primary/ring key).
    Returns ``None`` if no secret/keyring available.
    """
    if not attester:
        return None
    ts = int(now if now is not None else time.time())
    expiry = ts + int(ttl_secs)

    if principal:
        ring = load_keyring(secret=secret)
        if not ring:
            return None
        # Prefer explicit primary / default for mint.
        key = ring.get("default") or next(iter(ring.values()))
        sig = _sign_principal(principal, attester, expiry, key)
        return f"{principal}.{attester}.{expiry}.{sig}"

    resolved = _resolve_secret(secret)
    if not resolved:
        # Fall back to first ring key as utf-8 if only keyring configured.
        ring = load_keyring(secret="")
        if not ring:
            return None
        key = ring.get("default") or next(iter(ring.values()))
        resolved = key.decode("utf-8")
    sig = _sign_legacy(attester, expiry, resolved)
    return f"{attester}.{expiry}.{sig}"


def verify_seal(
    raw_header: Optional[str],
    *,
    secret: Optional[str] = None,
    keyring: Optional[str] = None,
    now: Optional[float] = None,
) -> str:
    """Verify seal header; return attester. Raises AuthError on any auth failure."""
    ring = load_keyring(secret=secret, keyring=keyring)
    # #16 path: secret-only callers still work when keyring env empty.
    if not ring:
        resolved = _resolve_secret(secret)
        if not resolved:
            raise AuthError(_OPAQUE)
        ring = {"default": resolved.encode("utf-8")}

    if not raw_header or not isinstance(raw_header, str):
        raise AuthError(_OPAQUE)

    ts = int(now if now is not None else time.time())

    def _legacy_ok() -> Optional[str]:
        parts = raw_header.rsplit(".", 2)
        if len(parts) != 3:
            return None
        attester, expiry_s, sig = parts
        if not attester or not expiry_s or not sig:
            return None
        try:
            expiry = int(expiry_s)
        except ValueError:
            return None
        if len(sig) != 64 or any(c not in "0123456789abcdef" for c in sig):
            return None
        if ts > expiry:
            raise AuthError(_OPAQUE)
        for key in ring.values():
            try:
                secret_s = key.decode("utf-8")
            except UnicodeDecodeError:
                continue
            expected = _sign_legacy(attester, expiry, secret_s)
            if _ct_hex_eq(expected, sig):
                return attester
        return None

    def _principal_ok() -> Optional[str]:
        # Gate PrincipalAuth: principal + attester must not contain '.'.
        parts = raw_header.rsplit(".", 3)
        if len(parts) != 4:
            return None
        principal, attester, expiry_s, sig = parts
        if not principal or not attester or "." in principal or "." in attester:
            return None
        try:
            expiry = int(expiry_s)
        except ValueError:
            return None
        if len(sig) != 64 or any(c not in "0123456789abcdef" for c in sig):
            return None
        if ts > expiry:
            raise AuthError(_OPAQUE)
        for key in ring.values():
            expected = _sign_principal(principal, attester, expiry, key)
            if _ct_hex_eq(expected, sig):
                return attester
        return None

    # Try legacy #16 first so dotted attesters keep working, then principal wire.
    attester = _legacy_ok()
    if attester is not None:
        return attester
    attester = _principal_ok()
    if attester is not None:
        return attester
    raise AuthError(_OPAQUE)


def require_seal(
    x_gf_seal: Optional[str] = Header(default=None, alias="x-gf-seal"),
) -> str:
    """FastAPI dependency: gate mutate routes on a valid ``x-gf-seal``."""
    if not load_keyring():
        raise HTTPException(status_code=503, detail="seal unavailable")
    return verify_seal(x_gf_seal)


class HMACSeal:
    """Thin helper kept for ``skeleton.api`` exports / legacy callers."""

    def __init__(self, secret: Optional[bytes] = None):
        if secret is None:
            primary = os.getenv(_ENV, "").encode() or None
            self._secret = primary or os.urandom(32)
        else:
            self._secret = secret

    def sign(self, method: str, path: str, body: bytes, timestamp: Optional[int] = None) -> str:
        ts = str(timestamp or int(time.time()))
        message = f"{method}:{path}:{ts}:{body.hex()}".encode()
        sig = hmac.new(self._secret, message, hashlib.sha256).hexdigest()
        return f"v1={sig}:{ts}"

    def verify(self, method: str, path: str, body: bytes, seal: str) -> bool:
        try:
            version, rest = seal.split("=", 1)
            if version != "v1":
                return False
            _sig, ts = rest.rsplit(":", 1)
            expected = self.sign(method, path, body, int(ts))
            return hmac.compare_digest(seal, expected)
        except (ValueError, TypeError):
            return False

    def stats(self) -> dict:
        return {"algorithm": "HMAC-SHA256", "version": "v1", "forge_seal": "attester|principal"}
