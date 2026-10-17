"""Client-side ``x-gf-seal`` minting.

Contract: Internal Systems seal contract, documented in
``docs/contracts/request_seal.md``, which is added by PR #4097 (not on this
branch yet).

The seal is a bearer-style expiring token, not a per-request signature. The
SDK must not import ``skeleton.api`` (architecture boundary: client code may not
depend upward on the server API layer, which also pulls in FastAPI), so the
minting below is a stdlib-only mirror of :func:`skeleton.api.hmac_seal.mint_seal`.
``tests/test_skeleton_client_seal_parity.py`` asserts byte-for-byte parity with
the server helper and round-trips through the real ``verify_seal`` so the wire
form never diverges. The secret comes from ``seal_secret=``, ``GF_SEAL_SECRET``
or (fallback) the first ``GF_SEAL_KEYRING`` entry; it and the token are never
logged or put in reprs.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading
import time
import uuid
from typing import Callable, Dict, Optional

from skeleton.client.errors import SkeletonSealConfigError

SEAL_HEADER = "x-gf-seal"
REQUEST_ID_HEADER = "x-request-id"
DEFAULT_TTL_SECS = 300
REMINT_MARGIN_SECS = 30
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_ENV_SECRET = "GF_SEAL_SECRET"
_ENV_KEYRING = "GF_SEAL_KEYRING"


def _parse_keyring(raw: Optional[str]) -> Dict[str, bytes]:
    """Mirror of the server keyring parser: ``kid=secret[,kid=secret...]``."""
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


def _load_keyring(secret: Optional[str]) -> Dict[str, bytes]:
    ring = _parse_keyring(os.environ.get(_ENV_KEYRING))
    primary = secret if secret is not None else os.environ.get(_ENV_SECRET)
    if primary:
        ring = {"default": primary.encode("utf-8"), **{k: v for k, v in ring.items() if k != "default"}}
    return ring


def mint_seal(
    attester: str,
    ttl_secs: int,
    *,
    secret: Optional[str] = None,
    principal: Optional[str] = None,
    now: Optional[float] = None,
) -> Optional[str]:
    """Stdlib mirror of ``skeleton.api.hmac_seal.mint_seal`` (same wire, same key choice).

    Without ``principal``: ``{attester}.{expiry}.{hex_hmac_sha256(attester|expiry)}``.
    With ``principal``: ``{principal}.{attester}.{expiry}.{hex_hmac_sha256(principal.attester.expiry)}``.
    Returns ``None`` when no secret or keyring is available.
    """
    if not attester:
        return None
    if isinstance(ttl_secs, bool) or not isinstance(ttl_secs, int):
        raise ValueError("ttl_secs must be an integer")
    expiry = int(now if now is not None else time.time()) + ttl_secs

    if principal:
        ring = _load_keyring(secret)
        if not ring:
            return None
        key = ring.get("default") or next(iter(ring.values()))
        payload = f"{principal}.{attester}.{expiry}".encode("utf-8")
        return f"{principal}.{attester}.{expiry}.{hmac.new(key, payload, hashlib.sha256).hexdigest()}"

    if secret is not None:
        resolved = secret or None
    else:
        resolved = os.environ.get(_ENV_SECRET) or None
    if not resolved:
        ring = _load_keyring("")
        if not ring:
            return None
        resolved = (ring.get("default") or next(iter(ring.values()))).decode("utf-8")
    msg = f"{attester}|{expiry}".encode("utf-8")
    return f"{attester}.{expiry}.{hmac.new(resolved.encode('utf-8'), msg, hashlib.sha256).hexdigest()}"


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def valid_request_id(value: str) -> bool:
    return isinstance(value, str) and bool(_REQUEST_ID_RE.fullmatch(value))


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
        self._secret = seal_secret  # None -> server helper reads GF_SEAL_SECRET
        self._ttl = ttl_secs
        self._clock = clock
        self._lock = threading.Lock()
        self._token: str | None = None
        self._expiry = 0.0

    def __repr__(self) -> str:  # never expose secret/token
        return f"RequestSealer(attester={self._attester!r}, principal={self._principal!r}, ttl_secs={self._ttl})"

    def _mint(self, now: float) -> str:
        token = mint_seal(
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
