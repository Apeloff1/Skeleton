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

    v2 domain-bound + nonce (Jenkins seal finding; see docs/contracts/request_seal.md)::
        v2.{principal}.{attester}.{domain}.{unix_expiry}.{nonce}.{hex_hmac_sha256(canonical, key)}
        canonical = "gf-seal/v2\n{principal}\n{attester}\n{domain}\n{unix_expiry}\n{nonce}"

Empty/missing keyring+secret → fail closed (503).
Missing/malformed/expired/bad signature → 401 AuthError (opaque).
v2: domain mismatch / replayed nonce → 401 AuthError (opaque).
Legacy (3/4-part) seals: accepted except on ``GF_SEAL_LEGACY`` policy-denied domains
(default ``sensitive``: rejected on ``realtime``; ``allow`` / ``deny`` also valid).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
import time
from typing import Dict, FrozenSet, List, Optional, Protocol, Tuple

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


def _require_ttl_secs(ttl_secs: object) -> int:
    """Reject bools and non-ints; ``int(True)`` must not become a 1-second TTL."""
    if isinstance(ttl_secs, bool) or not isinstance(ttl_secs, int):
        raise ValueError("ttl_secs must be an integer")
    return ttl_secs


def mint_seal(
    attester: str,
    ttl_secs: int = DEFAULT_TTL_SECS,
    *,
    secret: Optional[str] = None,
    principal: Optional[str] = None,
    now: Optional[float] = None,
    domain: Optional[str] = None,
) -> Optional[str]:
    """Mint an ``x-gf-seal`` value.

    With ``domain`` → v2 domain-bound single-use seal (:func:`mint_seal_v2`).
    Without ``principal`` → #16 3-part wire.
    With ``principal`` → 4-part PrincipalAuth wire (signed with primary/ring key).
    Returns ``None`` if no secret/keyring available.
    """
    if not attester:
        return None
    if domain is not None:
        return mint_seal_v2(attester, domain, ttl_secs, secret=secret, principal=principal, now=now)
    ts = int(now if now is not None else time.time())
    expiry = ts + _require_ttl_secs(ttl_secs)

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


# ---------------------------------------------------------------------------
# v2: domain-bound seal + nonce replay protection
# ---------------------------------------------------------------------------

V2_PREFIX = "v2."
V2_CANONICAL_TAG = "gf-seal/v2"
#: Replay-cache retention beyond ``expiry`` (multi-node clock drift margin).
#: Acceptance itself stays ``now <= expiry`` (no skew allowance).
REPLAY_SKEW_SECS = 30
#: v2 seals expiring further out than this are refused (bounds cache lifetime).
MAX_V2_TTL_SECS = 3600
DEFAULT_REPLAY_CACHE_MAX = 100_000
_V2_FIELD_RE = re.compile(r"^[A-Za-z0-9_:-]{1,128}$")
_V2_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

_ENV_LEGACY = "GF_SEAL_LEGACY"
#: Domains where legacy (unbound, replayable) seals are refused by default.
SENSITIVE_DOMAINS: FrozenSet[str] = frozenset({"realtime"})
LEGACY_POLICIES = ("sensitive", "allow", "deny")


def v2_canonical(principal: str, attester: str, domain: str, expiry: int, nonce: str) -> bytes:
    """Canonical, version-prefixed MAC input (newline-separated; fields contain no newline)."""
    return f"{V2_CANONICAL_TAG}\n{principal}\n{attester}\n{domain}\n{expiry}\n{nonce}".encode("utf-8")


def _sign_v2(principal: str, attester: str, domain: str, expiry: int, nonce: str, key: bytes) -> str:
    return hmac.new(key, v2_canonical(principal, attester, domain, expiry, nonce), hashlib.sha256).hexdigest()


def new_nonce() -> str:
    """128-bit url-safe random nonce (32 hex chars)."""
    return secrets.token_hex(16)


def legacy_policy() -> str:
    raw = (os.environ.get(_ENV_LEGACY) or "sensitive").strip().lower()
    # Unknown values fail closed to the strictest setting.
    return raw if raw in LEGACY_POLICIES else "deny"


def legacy_allowed(domain: Optional[str], policy: Optional[str] = None) -> bool:
    """Whether an unbound 3/4-part seal may be accepted on ``domain``."""
    pol = policy or legacy_policy()
    if pol == "allow":
        return True
    if pol == "deny":
        return False
    return domain not in SENSITIVE_DOMAINS


class ReplayCache(Protocol):
    """Port: atomically record a nonce; False if it was already seen (replay).

    Implementations may be shared (e.g. Redis ``SET key 1 NX EXAT expires_at``)
    so every replica sees the same nonce set. Must fail closed (return False or
    raise) when it cannot record.
    """

    def check_and_store(self, key: str, expires_at: int, now: int) -> bool: ...


class ReplayCacheFull(Exception):
    """Raised when a bounded cache cannot record a nonce (fail closed)."""


class InMemoryReplayCache:
    """Process-local bounded replay cache (default). Thread-safe.

    Entries live until ``expires_at`` (seal expiry + ``REPLAY_SKEW_SECS``).
    When full after purging expired entries, refuses (fail closed) rather than
    evicting live nonces (evicting would reopen a replay window).
    """

    def __init__(self, max_entries: int = DEFAULT_REPLAY_CACHE_MAX) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries <= 0:
            raise ValueError("max_entries must be a positive integer")
        self._max = max_entries
        self._seen: Dict[str, int] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._seen)

    def _purge(self, now: int) -> None:
        dead = [k for k, exp in self._seen.items() if exp < now]
        for k in dead:
            del self._seen[k]

    def check_and_store(self, key: str, expires_at: int, now: int) -> bool:
        with self._lock:
            exp = self._seen.get(key)
            if exp is not None and exp >= now:
                return False
            if len(self._seen) >= self._max:
                self._purge(now)
                if len(self._seen) >= self._max:
                    raise ReplayCacheFull("replay cache full")
            self._seen[key] = expires_at
            return True


def mint_seal_v2(
    attester: str,
    domain: str,
    ttl_secs: int = DEFAULT_TTL_SECS,
    *,
    secret: Optional[str] = None,
    principal: Optional[str] = None,
    now: Optional[float] = None,
    nonce: Optional[str] = None,
) -> Optional[str]:
    """Mint a single-use, domain-bound v2 seal. ``principal`` defaults to ``attester``."""
    principal = principal or attester
    ttl = _require_ttl_secs(ttl_secs)
    if ttl <= 0 or ttl > MAX_V2_TTL_SECS:
        raise ValueError(f"ttl_secs must be in 1..{MAX_V2_TTL_SECS} for v2 seals")
    nonce = nonce or new_nonce()
    for value in (principal, attester, domain):
        if not isinstance(value, str) or not _V2_FIELD_RE.fullmatch(value):
            raise ValueError("principal/attester/domain must match [A-Za-z0-9_:-]{1,128}")
    if not _V2_NONCE_RE.fullmatch(nonce):
        raise ValueError("nonce must match [A-Za-z0-9_-]{16,128}")
    ring = load_keyring(secret=secret)
    if not ring:
        return None
    key = ring.get("default") or next(iter(ring.values()))
    expiry = int(now if now is not None else time.time()) + ttl
    mac = _sign_v2(principal, attester, domain, expiry, nonce, key)
    return f"{V2_PREFIX}{principal}.{attester}.{domain}.{expiry}.{nonce}.{mac}"


def _verify_v2(
    raw_header: str,
    ring: Dict[str, bytes],
    *,
    ts: int,
    expected_domain: Optional[str],
    replay_cache: Optional[ReplayCache],
) -> str:
    parts = raw_header[len(V2_PREFIX):].split(".")
    if len(parts) != 6:
        raise AuthError(_OPAQUE)
    principal, attester, domain, expiry_s, nonce, mac = parts
    if not all(_V2_FIELD_RE.fullmatch(v) for v in (principal, attester, domain)):
        raise AuthError(_OPAQUE)
    if not _V2_NONCE_RE.fullmatch(nonce) or not _HEX64_RE.fullmatch(mac):
        raise AuthError(_OPAQUE)
    if not expiry_s.isdigit() or len(expiry_s) > 12:
        raise AuthError(_OPAQUE)
    expiry = int(expiry_s)
    if ts > expiry or expiry > ts + MAX_V2_TTL_SECS + REPLAY_SKEW_SECS:
        raise AuthError(_OPAQUE)
    ok = False
    for key in ring.values():
        if _ct_hex_eq(_sign_v2(principal, attester, domain, expiry, nonce, key), mac):
            ok = True
    if not ok:
        raise AuthError(_OPAQUE)
    # Domain binding: only after MAC so a forged domain never reaches here.
    if expected_domain is not None and not hmac.compare_digest(domain, expected_domain):
        raise AuthError(_OPAQUE)
    if replay_cache is not None:
        try:
            fresh = replay_cache.check_and_store(
                f"{principal}.{attester}.{nonce}", expiry + REPLAY_SKEW_SECS, ts
            )
        except Exception:
            raise AuthError(_OPAQUE)
        if not fresh:
            raise AuthError(_OPAQUE)
    return attester


def verify_seal(
    raw_header: Optional[str],
    *,
    secret: Optional[str] = None,
    keyring: Optional[str] = None,
    now: Optional[float] = None,
    domain: Optional[str] = None,
    replay_cache: Optional[ReplayCache] = None,
    legacy: Optional[str] = None,
    enforce_domain: bool = False,
) -> str:
    """Verify seal header; return attester. Raises AuthError on any auth failure.

    ``enforce_domain=True`` (RequestSealMiddleware): v2 seals must name ``domain``
    (``None`` → nothing matches), nonces are consumed in ``replay_cache``, and
    legacy seals are subject to ``GF_SEAL_LEGACY`` (``legacy=`` overrides).
    Default ``False`` keeps the pre-v2 helper semantics for direct callers.
    """
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

    if raw_header.startswith(V2_PREFIX):
        if enforce_domain and not domain:
            raise AuthError(_OPAQUE)  # unchartered path: a v2 seal binds nothing here
        return _verify_v2(
            raw_header,
            ring,
            ts=ts,
            expected_domain=domain if enforce_domain else (domain or None),
            replay_cache=replay_cache,
        )
    if enforce_domain and not legacy_allowed(domain, legacy):
        raise AuthError(_OPAQUE)

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
