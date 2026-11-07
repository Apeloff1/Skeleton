"""Client-side ``x-gf-seal`` minting.

Contract: Internal Systems seal contract, documented in
``docs/contracts/request_seal.md``, which is added by PR #4097 (not on this
branch yet).

The seal is a bearer-style expiring token, not a per-request signature. The
wire form mirrors the server helper ``skeleton.api.hmac_seal.mint_seal``
byte-for-byte, but is minted locally with ``hmac``/``hashlib`` so this client
package never imports upward into ``skeleton.api`` (architecture boundary).
Round-trip tests against the server ``verify_seal`` keep the two in lockstep.
The secret comes from ``seal_secret=`` or the ``GF_SEAL_SECRET`` env var
(falling back to the first ``GF_SEAL_KEYRING`` entry, as the server does); it
and the token are never logged or put in reprs.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading
import time
import uuid
from typing import Callable

from skeleton.client.errors import SkeletonSealConfigError

SEAL_HEADER = "x-gf-seal"
REQUEST_ID_HEADER = "x-request-id"
DEFAULT_TTL_SECS = 300
REMINT_MARGIN_SECS = 30
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_SECRET_ENV = "GF_SEAL_SECRET"
_KEYRING_ENV = "GF_SEAL_KEYRING"


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def valid_request_id(value: str) -> bool:
    return isinstance(value, str) and bool(_REQUEST_ID_RE.fullmatch(value))


def _parse_keyring(raw: str | None) -> dict[str, bytes]:
    """Parse ``kid=secret[,kid=secret...]`` exactly like the server keyring."""
    out: dict[str, bytes] = {}
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


def _load_keyring(secret: str | None) -> dict[str, bytes]:
    ring = _parse_keyring(os.environ.get(_KEYRING_ENV))
    primary = secret if secret is not None else os.environ.get(_SECRET_ENV)
    if primary:
        ring = {"default": primary.encode("utf-8"), **{k: v for k, v in ring.items() if k != "default"}}
    return ring


def _mint_key(secret: str | None) -> bytes | None:
    """Pick the mint key the server would: primary secret, else first ring key."""
    ring = _load_keyring(secret)
    if not ring:
        return None
    return ring.get("default") or next(iter(ring.values()))


def mint_seal_token(
    attester: str,
    ttl_secs: int = DEFAULT_TTL_SECS,
    *,
    secret: str | None = None,
    principal: str | None = None,
    now: float | None = None,
) -> str | None:
    """Mint an ``x-gf-seal`` value; ``None`` when no secret/keyring is available.

    Without ``principal``: ``{attester}.{expiry}.{hex_hmac_sha256(attester|expiry)}``.
    With ``principal``: ``{principal}.{attester}.{expiry}.{hex_hmac_sha256(principal.attester.expiry)}``.
    """
    if not attester:
        return None
    if isinstance(ttl_secs, bool) or not isinstance(ttl_secs, int):
        raise ValueError("ttl_secs must be an integer")
    expiry = int(now if now is not None else time.time()) + ttl_secs

    if principal:
        key = _mint_key(secret)
        if key is None:
            return None
        payload = f"{principal}.{attester}.{expiry}".encode("utf-8")
        sig = hmac.new(key, payload, hashlib.sha256).hexdigest()
        return f"{principal}.{attester}.{expiry}.{sig}"

    if secret is not None:
        resolved: str | None = secret or None
    else:
        resolved = os.environ.get(_SECRET_ENV) or None
    if resolved:
        key = resolved.encode("utf-8")
    else:
        key = _mint_key("")
        if key is None:
            return None
    msg = f"{attester}|{expiry}".encode("utf-8")
    sig = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return f"{attester}.{expiry}.{sig}"


class RequestSealer:
    """Caches one minted seal and re-mints ~30s before its absolute expiry."""

    __slots__ = ("_attester", "_principal", "_secret", "_ttl", "_clock", "_lock", "_token", "_expiry")

    def __init__(
        self,
        attester: str,
        *,
        principal: str | None = None,
        seal_secret: str | None = None,
        ttl_secs: int = DEFAULT_TTL_SECS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not attester or "." in attester:
            raise SkeletonSealConfigError("attester must be non-empty and contain no '.'")
        if principal is not None and (not principal or "." in principal):
            raise SkeletonSealConfigError("principal must be non-empty and contain no '.'")
        if isinstance(ttl_secs, bool) or not isinstance(ttl_secs, int) or ttl_secs <= REMINT_MARGIN_SECS:
            raise SkeletonSealConfigError(f"ttl_secs must be an int > {REMINT_MARGIN_SECS}")
        self._attester = attester
        self._principal = principal
        self._secret = seal_secret  # None -> read GF_SEAL_SECRET / GF_SEAL_KEYRING at mint time
        self._ttl = ttl_secs
        self._clock = clock
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expiry = 0.0

    def __repr__(self) -> str:  # never expose secret/token
        return f"RequestSealer(attester={self._attester!r}, principal={self._principal!r}, ttl_secs={self._ttl})"

    def _mint(self, now: float) -> str:
        token = mint_seal_token(
            self._attester, self._ttl, secret=self._secret, principal=self._principal, now=now
        )
        if not token:
            raise SkeletonSealConfigError(
                "no seal secret available: pass seal_secret= or set GF_SEAL_SECRET"
            )
        return token

    def token(self) -> str:
        with self._lock:
            now = self._clock()
            if self._token is None or now >= self._expiry - REMINT_MARGIN_SECS:
                self._token = self._mint(now)
                self._expiry = int(now) + self._ttl
            return self._token

    def invalidate(self) -> None:
        with self._lock:
            self._token = None
            self._expiry = 0.0

    def headers(self) -> dict[str, str]:
        return {SEAL_HEADER: self.token()}
