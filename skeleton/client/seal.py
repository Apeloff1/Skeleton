"""Client-side ``x-gf-seal`` minting.

Contract: Internal Systems seal contract, documented in
``docs/contracts/request_seal.md``, which is added by PR #4097 (not on this
branch yet).

The seal is a bearer-style expiring token, not a per-request signature. It is
minted with the server helper :func:`skeleton.api.hmac_seal.mint_seal` so the
wire form never diverges. The secret comes from ``seal_secret=`` or the
``GF_SEAL_SECRET`` env var; it and the token are never logged or put in reprs.
"""

from __future__ import annotations

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
        from skeleton.api.hmac_seal import mint_seal

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
